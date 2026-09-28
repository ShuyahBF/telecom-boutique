"""Règles d'accès (IP / appareils) et journal des connexions d'une boutique (DG)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import acces
from auth import Contexte, permission
from db import SANS_ID, db
from utils import new_id, now_iso

router = APIRouter(prefix="/boutique/acces", tags=["Accès (IP / appareils)"])
parametres = permission("parametres")  # DG (et super-admin)


def _ma_connexion(request: Request) -> dict:
    return {"ip": acces.ip_client(request), "appareil_id": acces.appareil_id(request),
            "appareil": acces.description_appareil(request.headers.get("user-agent", ""))}


async def _enregistrer(ctx: Contexte, request: Request, liste: list[dict]) -> list[dict]:
    """Enregistre les règles, sauf si elles bloqueraient la connexion en cours
    du DG (on ne peut pas s'enfermer dehors par erreur)."""
    if ctx.role != "super_admin":
        autorise, raison = acces.verdict(liste, acces.ip_client(request), acces.appareil_id(request))
        if not autorise:
            raise HTTPException(400, f"Cette règle vous bloquerait vous-même ({raison.lower()}). "
                                     "Autorisez d'abord votre adresse ou votre appareil actuel.")
    await db.boutiques.update_one({"id": ctx.boutique["id"]}, {"$set": {"acces.regles": liste}})
    return liste


@router.get("")
async def lire(request: Request, ctx: Contexte = Depends(parametres)):
    return {"regles": acces.regles(ctx.boutique), "ma_connexion": _ma_connexion(request)}


class Regle(BaseModel):
    type: Literal["IP", "APPAREIL"]
    valeur: str = Field(..., min_length=1, max_length=45)
    action: Literal["AUTORISER", "INTERDIRE"]
    libelle: str = Field("", max_length=80)  # ex. « Caisse principale », « Wifi de la boutique »


@router.post("/regles", status_code=201)
async def ajouter(payload: Regle, request: Request, ctx: Contexte = Depends(parametres)):
    try:
        valeur = acces.valider_regle(payload.type, payload.valeur)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    liste = acces.regles(ctx.boutique)
    if any(r["type"] == payload.type and r["valeur"] == valeur for r in liste):
        raise HTTPException(409, "Une règle existe déjà pour cette valeur : supprimez-la d'abord")
    regle = {"id": new_id(), "type": payload.type, "valeur": valeur, "action": payload.action,
             "libelle": payload.libelle.strip(), "cree_le": now_iso(), "cree_par": ctx.user.get("nom", "")}
    await _enregistrer(ctx, request, [*liste, regle])
    return regle


@router.delete("/regles/{regle_id}")
async def supprimer(regle_id: str, request: Request, ctx: Contexte = Depends(parametres)):
    liste = acces.regles(ctx.boutique)
    reste = [r for r in liste if r["id"] != regle_id]
    if len(reste) == len(liste):
        raise HTTPException(404, "Règle introuvable")
    await _enregistrer(ctx, request, reste)
    return {"ok": True}


@router.get("/journal")
async def journal(resultat: str = "", q: str = "", ctx: Contexte = Depends(parametres)):
    """Dernières tentatives de connexion au back-office de la boutique."""
    filtre: dict = {"boutique_id": ctx.boutique["id"]}
    if resultat:
        filtre["resultat"] = resultat
    lignes = await db.connexions_journal.find(filtre, SANS_ID).sort("date", -1).to_list(500)
    if q.strip():
        t = q.strip().lower()
        lignes = [x for x in lignes if t in f"{x['ip']} {x.get('email', '')} {x.get('nom', '')} {x.get('appareil_id', '')}".lower()]
    return {"lignes": lignes, "resultats": acces.RESULTATS}


class DepuisJournal(BaseModel):
    type: Literal["IP", "APPAREIL"]
    action: Literal["AUTORISER", "INTERDIRE"]


@router.post("/journal/{ligne_id}/regle", status_code=201)
async def regle_depuis_journal(ligne_id: str, payload: DepuisJournal, request: Request,
                               ctx: Contexte = Depends(parametres)):
    """Autorise ou interdit, pour l'avenir, l'adresse IP ou l'appareil d'une ligne du journal."""
    ligne = await db.connexions_journal.find_one({"id": ligne_id, "boutique_id": ctx.boutique["id"]}, SANS_ID)
    if not ligne:
        raise HTTPException(404, "Ligne introuvable")
    valeur = ligne["ip"] if payload.type == "IP" else ligne.get("appareil_id")
    if not valeur:
        raise HTTPException(400, "Cet appareil n'a pas encore d'identifiant")
    liste = [r for r in acces.regles(ctx.boutique) if not (r["type"] == payload.type and r["valeur"] == valeur)]
    regle = {"id": new_id(), "type": payload.type, "valeur": valeur, "action": payload.action,
             "libelle": f"{ligne.get('nom') or ligne.get('email') or ''} — {ligne.get('appareil', '')}".strip(" —")[:80],
             "cree_le": now_iso(), "cree_par": ctx.user.get("nom", "")}
    await _enregistrer(ctx, request, [*liste, regle])
    return regle
