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
from utils import motif_recherche, new_id, now_iso, slugifier

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


async def _creer_fiche(marque: str, nom: str, codes: list[str], annee, referentiel_cle: Optional[str],
                       avec_assistant: bool) -> dict:
    """Crée (brouillon) la fiche détaillée du catalogue public, ou relie celle qui
    existe déjà sous l'un des codes modèle ; l'assistant peut la compléter."""
    codes = [c.strip().upper() for c in codes if c and c.strip()]
    existante = await db.catalogue_modeles.find_one({"reference": {"$in": codes}}, SANS_ID) if codes else None
    if existante:
        if referentiel_cle:
            await referentiel.lier_fiche(referentiel_cle, existante["id"])
        return {"fiche": existante, "proposition": None, "existante": True}
    reference = (codes[0] if codes else (referentiel_cle or new_id()[:8])).upper()[:60]
    fiche = {"id": new_id(), "type_produit": "TEL", "marque": marque, "nom": nom, "reference": reference,
             "annee_sortie": annee, "description": "", "caracteristiques": [], "photo_url": None,
             "modeles_compatibles": [], "sources": [], "statut": "BROUILLON", "publie": False,
             "modifie_apres_publication": False, "version_publiee": 0, "date_publication": None,
             "referentiel_cle": referentiel_cle, "created_at": now_iso(), "updated_at": now_iso()}
    proposition: Optional[dict] = None
    if avec_assistant:
        try:
            proposition = await cp.rechercher_fiche(marque, nom, f"Codes modèle : {', '.join(codes[:10])}" if codes else "")
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        if proposition.get("trouve"):
            fiche.update({"description": proposition.get("description", ""),
                          "caracteristiques": proposition.get("caracteristiques", []),
                          "annee_sortie": proposition.get("annee_sortie") or annee,
                          "sources": proposition.get("sources", [])})
    await db.catalogue_modeles.insert_one(dict(fiche))
    if referentiel_cle:
        await referentiel.lier_fiche(referentiel_cle, fiche["id"])
    return {"fiche": fiche, "proposition": proposition, "existante": False}


# ---------------------------------------------------------------------------
# Modèles VENDUS dans les boutiques : par où commencer le catalogue public
# ---------------------------------------------------------------------------
@admin.get("/demande")
async def modeles_vendus(_: dict = Depends(get_super_admin)):
    """Téléphones créés par les boutiques elles-mêmes, regroupés par modèle et
    classés par nombre de boutiques qui les vendent. Seule l'IDENTITÉ du modèle
    est utilisée (marque, nom, code) : jamais les prix ni les documents privés."""
    produits = await db.produits.find(
        {"catalogue_id": None, "type_produit": "TEL", "actif": {"$ne": False}},
        {"_id": 0, "boutique_id": 1, "nom": 1, "marque": 1, "referentiel_cle": 1, "fiche_publique_id": 1,
         "fiche_technique.fabricant": 1, "fiche_technique.modele": 1}).to_list(None)
    groupes: dict[str, dict] = {}
    for p in produits:
        ft = p.get("fiche_technique") or {}
        marque = (ft.get("fabricant") or p.get("marque") or "").strip()
        modele = (ft.get("modele") or "").strip()
        cle = p.get("referentiel_cle") or slugifier(f"{marque}-{modele or p['nom']}")
        g = groupes.setdefault(cle, {"cle": cle, "referentiel_cle": p.get("referentiel_cle"), "marque": marque,
                                     "noms": {}, "codes": set(), "boutiques": set(), "deja_publie": False})
        g["noms"][p["nom"]] = g["noms"].get(p["nom"], 0) + 1
        if modele:
            g["codes"].add(modele.upper())
        g["boutiques"].add(p["boutique_id"])
        g["deja_publie"] = g["deja_publie"] or bool(p.get("fiche_publique_id"))
    # État de la fiche publique (via le référentiel ou un code modèle identique)
    resultat = []
    for g in groupes.values():
        fiche = None
        if g["referentiel_cle"]:
            app = await db.referentiel_appareils.find_one({"cle": g["referentiel_cle"]}, {"_id": 0, "catalogue_id": 1, "nom": 1, "marque": 1})
            if app:
                g["marque"] = app["marque"]
                g["noms"] = {app["nom"]: 10**6}  # nom officiel prioritaire
                if app.get("catalogue_id"):
                    fiche = await db.catalogue_modeles.find_one({"id": app["catalogue_id"]}, {"_id": 0, "id": 1, "publie": 1, "statut": 1})
        if not fiche and g["codes"]:
            fiche = await db.catalogue_modeles.find_one({"reference": {"$in": sorted(g["codes"])}}, {"_id": 0, "id": 1, "publie": 1, "statut": 1})
        resultat.append({"cle": g["cle"], "referentiel_cle": g["referentiel_cle"], "marque": g["marque"],
                         "nom": max(g["noms"], key=g["noms"].get), "codes_modele": sorted(g["codes"]),
                         "nb_boutiques": len(g["boutiques"]), "fiche": fiche})
    resultat.sort(key=lambda r: (r["fiche"] is not None and bool(r["fiche"].get("publie")), -r["nb_boutiques"], r["marque"].lower()))
    return resultat


class FicheDepuisDemande(BaseModel):
    marque: str
    nom: str
    codes_modele: list[str] = []
    referentiel_cle: Optional[str] = None
    avec_assistant: bool = False


@admin.post("/demande/fiche")
async def creer_fiche_demande(payload: FicheDepuisDemande, _: dict = Depends(get_super_admin)):
    """Fiche détaillée pour un modèle vendu dans les boutiques."""
    codes = list(payload.codes_modele)
    annee = None
    if payload.referentiel_cle:
        app = await db.referentiel_appareils.find_one({"cle": payload.referentiel_cle}, SANS_ID)
        if app:
            codes = list(dict.fromkeys(codes + app.get("codes_modele", [])))
            annee = app.get("annee_sortie")
    return await _creer_fiche(payload.marque, payload.nom, codes, annee, payload.referentiel_cle, payload.avec_assistant)


# Déclarée en DERNIER : « /{cle}/fiche » capterait sinon « /demande/fiche »
@admin.post("/{cle}/fiche")
async def creer_fiche(cle: str, payload: CreationFiche, _: dict = Depends(get_super_admin)):
    """Fiche détaillée pour un appareil du référentiel mondial."""
    appareil = await db.referentiel_appareils.find_one({"cle": cle}, SANS_ID)
    if not appareil:
        raise HTTPException(404, "Appareil inconnu du référentiel")
    if appareil.get("catalogue_id") and await db.catalogue_modeles.find_one({"id": appareil["catalogue_id"]}):
        raise HTTPException(409, "Cet appareil a déjà sa fiche dans le catalogue public")
    return await _creer_fiche(appareil["marque"], appareil["nom"], appareil.get("codes_modele", []),
                              appareil.get("annee_sortie"), cle, payload.avec_assistant)
