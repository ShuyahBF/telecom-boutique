"""Référentiel mondial des appareils : import (super-admin) et recherche
(tout le personnel des boutiques)."""
from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import catalogue_public as cp
import referentiel
from auth import Contexte, get_current_user, get_super_admin, tout_le_personnel
from db import SANS_ID, db
from utils import motif_recherche, new_id, now_iso

admin = APIRouter(prefix="/plateforme/referentiel", tags=["Référentiel mondial (super-admin)"])
consultation = APIRouter(prefix="/referentiel", tags=["Référentiel mondial"])


async def rechercher(q: str, marque: str, page: int, par_page: int, sans_fiche: bool = False) -> dict:
    filtre: dict = {}
    if q.strip():
        motif = motif_recherche(q)
        filtre["$or"] = [{"nom": {"$regex": motif, "$options": "i"}}, {"marque": {"$regex": motif, "$options": "i"}},
                         {"codes_modele": {"$regex": motif, "$options": "i"}}]
    if marque:
        filtre["marque"] = marque
    if sans_fiche:
        filtre["catalogue_id"] = None
    total = await db.referentiel_appareils.count_documents(filtre)
    par_page = min(max(par_page, 1), 100)
    page = max(page, 1)
    appareils = await db.referentiel_appareils.find(filtre, SANS_ID).sort([("marque", 1), ("nom", 1)]) \
        .skip((page - 1) * par_page).limit(par_page).to_list(par_page)
    # Fiche détaillée disponible seulement si elle a été PUBLIÉE dans le catalogue public
    ids = [a["catalogue_id"] for a in appareils if a.get("catalogue_id")]
    publies = {m["id"] async for m in db.catalogue_publie.find({"id": {"$in": ids}}, {"_id": 0, "id": 1})}
    for a in appareils:
        a["fiche_publiee"] = a.get("catalogue_id") in publies
        a["codes_modele"] = a.get("codes_modele", [])[:8]
        a.pop("noms_code", None)
    return {"total": total, "page": page, "pages": max(math.ceil(total / par_page), 1), "appareils": appareils}


@consultation.get("")
async def rechercher_boutique(q: str = "", marque: str = "", page: int = 1, _: Contexte = Depends(tout_le_personnel)):
    return await rechercher(q, marque, page, 30)


@consultation.get("/marques")
async def marques(_: dict = Depends(get_current_user)):  # personnel des boutiques ET super-admin
    return sorted(await db.referentiel_appareils.distinct("marque"), key=str.lower)


@admin.get("")
async def rechercher_admin(q: str = "", marque: str = "", page: int = 1, sans_fiche: bool = False,
                           _: dict = Depends(get_super_admin)):
    resultat = await rechercher(q, marque, page, 50, sans_fiche)
    resultat["dernier_import"] = await referentiel.dernier_import()
    return resultat


@admin.post("/importer")
async def importer(_: dict = Depends(get_super_admin)):
    """Télécharge la liste officielle Google Play (+ iPhone) et met le référentiel à jour."""
    try:
        return await referentiel.importer()
    except Exception as exc:  # noqa: BLE001 — réseau, format...
        raise HTTPException(502, f"Import impossible : {str(exc)[:200]}") from exc


class CreationFiche(BaseModel):
    avec_assistant: bool = False  # lancer aussi la recherche des caractéristiques


@admin.post("/{cle}/fiche")
async def creer_fiche(cle: str, payload: CreationFiche, _: dict = Depends(get_super_admin)):
    """Crée (en brouillon) la fiche détaillée du catalogue public pour cet appareil,
    pré-remplie avec son identité, et éventuellement complétée par l'assistant."""
    appareil = await db.referentiel_appareils.find_one({"cle": cle}, SANS_ID)
    if not appareil:
        raise HTTPException(404, "Appareil inconnu du référentiel")
    if appareil.get("catalogue_id") and await db.catalogue_modeles.find_one({"id": appareil["catalogue_id"]}):
        raise HTTPException(409, "Cet appareil a déjà sa fiche dans le catalogue public")
    # Une fiche existe déjà sous l'un de ses codes modèle : on la relie au lieu d'en créer une autre
    codes = [c.upper() for c in appareil.get("codes_modele", [])]
    existante = await db.catalogue_modeles.find_one({"reference": {"$in": codes}}, SANS_ID) if codes else None
    if existante:
        await referentiel.lier_fiche(cle, existante["id"])
        return {"fiche": existante, "proposition": None, "existante": True}
    reference = (appareil["codes_modele"][0] if appareil.get("codes_modele") else cle).upper()[:60]
    if await db.catalogue_modeles.find_one({"reference": reference}):
        reference = f"{reference}-{new_id()[:4].upper()}"
    fiche = {"id": new_id(), "type_produit": "TEL", "marque": appareil["marque"], "nom": appareil["nom"],
             "reference": reference, "annee_sortie": appareil.get("annee_sortie"), "description": "",
             "caracteristiques": [], "photo_url": None, "modeles_compatibles": [], "sources": [],
             "statut": "BROUILLON", "publie": False, "modifie_apres_publication": False, "version_publiee": 0,
             "date_publication": None, "referentiel_cle": cle, "created_at": now_iso(), "updated_at": now_iso()}
    proposition: Optional[dict] = None
    if payload.avec_assistant:
        try:
            proposition = await cp.rechercher_fiche(appareil["marque"], appareil["nom"],
                                                    f"Codes modèle : {', '.join(appareil.get('codes_modele', [])[:10])}")
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        if proposition.get("trouve"):
            fiche.update({"description": proposition.get("description", ""),
                          "caracteristiques": proposition.get("caracteristiques", []),
                          "annee_sortie": proposition.get("annee_sortie") or fiche["annee_sortie"],
                          "sources": proposition.get("sources", [])})
    await db.catalogue_modeles.insert_one(dict(fiche))
    await referentiel.lier_fiche(cle, fiche["id"])
    return {"fiche": fiche, "proposition": proposition}
