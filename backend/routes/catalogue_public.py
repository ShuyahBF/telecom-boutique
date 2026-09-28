"""Catalogue public commun : gestion par l'administrateur de la plateforme
(saisie, assistant de recherche, publication) et consultation par les boutiques."""
from __future__ import annotations

import re
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

import catalogue_public as cp
from auth import Contexte, get_super_admin, tout_le_personnel
from db import SANS_ID, db
from storage import TYPES_IMAGES, enregistrer_fichier_catalogue, lire_image
from utils import new_id, now_iso, motif_recherche

admin = APIRouter(prefix="/plateforme/catalogue", tags=["Catalogue public (super-admin)"])
consultation = APIRouter(prefix="/catalogue-public", tags=["Catalogue public (boutiques)"])


class ModeleSaisie(BaseModel):
    type_produit: Literal["TEL", "PIE", "ACC"] = "TEL"
    marque: str = Field(..., min_length=1, max_length=60)
    nom: str = Field(..., min_length=1, max_length=150)
    reference: str = Field(..., min_length=2, max_length=60)
    annee_sortie: Optional[int] = Field(None, ge=1990, le=2100)
    description: str = Field("", max_length=3000)
    caracteristiques: list[str] = Field(default_factory=list, max_length=80)
    photo_url: Optional[str] = Field(None, max_length=1000)
    # Pour une pièce ou un accessoire : téléphones compatibles (identifiants du catalogue)
    modeles_compatibles: list[str] = Field(default_factory=list, max_length=200)
    sources: list[str] = Field(default_factory=list, max_length=30)
    # BROUILLON = en cours de saisie ; PRET = sera publié ce soir
    statut: Literal["BROUILLON", "PRET"] = "BROUILLON"


def _nettoyer(payload: ModeleSaisie) -> dict:
    d = payload.model_dump()
    d["reference"] = payload.reference.strip().upper()
    d["caracteristiques"] = [c.strip() for c in payload.caracteristiques if c.strip()]
    d["sources"] = [u.strip() for u in payload.sources if u.strip()]
    if payload.type_produit == "TEL":
        d["modeles_compatibles"] = []
    return d


async def _verifier(d: dict, sauf_id: Optional[str] = None) -> None:
    autre = await db.catalogue_modeles.find_one({"reference": d["reference"]}, {"_id": 0, "id": 1})
    if autre and autre["id"] != sauf_id:
        raise HTTPException(409, "Cette référence existe déjà dans le catalogue public")
    if d["modeles_compatibles"]:
        n = await db.catalogue_modeles.count_documents({"id": {"$in": d["modeles_compatibles"]}, "type_produit": "TEL"})
        if n != len(set(d["modeles_compatibles"])):
            raise HTTPException(400, "Un des téléphones compatibles n'existe pas dans le catalogue")


# ---------------------------------------------------------------------------
# Administration (super-admin)
# ---------------------------------------------------------------------------
@admin.get("")
async def lister(q: str = "", type_produit: str = "", statut: str = "", _: dict = Depends(get_super_admin)):
    filtre: dict = {"supprime": {"$ne": True}}
    if q.strip():
        motif = motif_recherche(q)
        filtre["$or"] = [{k: {"$regex": motif, "$options": "i"}} for k in ("nom", "marque", "reference")]
    if type_produit:
        filtre["type_produit"] = type_produit
    if statut == "EN_ATTENTE":  # sera publié ce soir
        filtre["statut"] = "PRET"
        filtre["$and"] = [{"$or": [{"publie": {"$ne": True}}, {"modifie_apres_publication": True}]}]
    elif statut:
        filtre["statut"] = statut
    return await db.catalogue_modeles.find(filtre, SANS_ID).sort([("marque", 1), ("nom", 1)]).to_list(5000)


@admin.get("/publication")
async def etat_publication(_: dict = Depends(get_super_admin)):
    en_attente = await db.catalogue_modeles.count_documents(
        {"statut": "PRET", "supprime": {"$ne": True}, "$or": [{"publie": {"$ne": True}}, {"modifie_apres_publication": True}]})
    historique = await db.catalogue_publications.find({}, SANS_ID).sort("date", -1).to_list(20)
    return {"prochaine_publication": cp.prochaine_publication().isoformat(), "en_attente": en_attente,
            "historique": historique}


@admin.post("/publier")
async def publier_maintenant(_: dict = Depends(get_super_admin)):
    """Publication immédiate, sans attendre 23h."""
    return await cp.publier("manuel")


class DemandeRecherche(BaseModel):
    marque: str = Field(..., min_length=1, max_length=60)
    modele: str = Field(..., min_length=1, max_length=150)
    precisions: str = Field("", max_length=500)


@admin.post("/recherche")
async def rechercher(payload: DemandeRecherche, _: dict = Depends(get_super_admin)):
    """Propose une fiche technique trouvée sur les sites des fabricants (à relire avant d'enregistrer)."""
    try:
        return await cp.rechercher_fiche(payload.marque, payload.modele, payload.precisions)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@admin.get("/{modele_id}")
async def lire(modele_id: str, _: dict = Depends(get_super_admin)):
    m = await db.catalogue_modeles.find_one({"id": modele_id}, SANS_ID)
    if not m:
        raise HTTPException(404, "Fiche introuvable")
    # Pièces et accessoires qui déclarent ce téléphone comme compatible
    m["pieces"] = await db.catalogue_modeles.find(
        {"modeles_compatibles": modele_id, "supprime": {"$ne": True}},
        {"_id": 0, "id": 1, "nom": 1, "marque": 1, "reference": 1, "type_produit": 1, "statut": 1}).to_list(500)
    return m


@admin.post("", status_code=201)
async def creer(payload: ModeleSaisie, _: dict = Depends(get_super_admin)):
    d = _nettoyer(payload)
    await _verifier(d)
    modele = {"id": new_id(), **d, "publie": False, "modifie_apres_publication": False, "version_publiee": 0,
              "date_publication": None, "created_at": now_iso(), "updated_at": now_iso()}
    await db.catalogue_modeles.insert_one(modele.copy())
    return modele


@admin.put("/{modele_id}")
async def modifier(modele_id: str, payload: ModeleSaisie, _: dict = Depends(get_super_admin)):
    actuel = await db.catalogue_modeles.find_one({"id": modele_id}, SANS_ID)
    if not actuel:
        raise HTTPException(404, "Fiche introuvable")
    d = _nettoyer(payload)
    await _verifier(d, sauf_id=modele_id)
    # Une fiche déjà publiée et modifiée sera republiée ce soir
    d.update({"modifie_apres_publication": bool(actuel.get("publie")), "updated_at": now_iso()})
    await db.catalogue_modeles.update_one({"id": modele_id}, {"$set": d})
    return await db.catalogue_modeles.find_one({"id": modele_id}, SANS_ID)


@admin.delete("/{modele_id}")
async def supprimer(modele_id: str, _: dict = Depends(get_super_admin)):
    """Seule une fiche jamais publiée peut être supprimée (les boutiques ont déjà les autres)."""
    res = await db.catalogue_modeles.delete_one({"id": modele_id, "publie": {"$ne": True}})
    if not res.deleted_count:
        raise HTTPException(409, "Fiche introuvable ou déjà publiée dans les boutiques")
    # L'appareil du référentiel mondial n'a plus de fiche
    await db.referentiel_appareils.update_many({"catalogue_id": modele_id}, {"$set": {"catalogue_id": None}})
    return {"ok": True}


@admin.post("/{modele_id}/photo")
async def envoyer_photo(modele_id: str, fichier: UploadFile = File(...), _: dict = Depends(get_super_admin)):
    contenu, type_mime = await lire_image(fichier)
    return await _poser_photo(modele_id, await enregistrer_fichier_catalogue(contenu, type_mime))


class PhotoUrl(BaseModel):
    url: str = Field(..., max_length=1000, pattern=r"^https://")


@admin.post("/{modele_id}/photo-depuis-url")
async def importer_photo(modele_id: str, payload: PhotoUrl, _: dict = Depends(get_super_admin)):
    """Télécharge la photo proposée (ex. par l'assistant) et la range dans NOTRE stockage :
    une image hébergée chez un tiers peut disparaître ou changer d'adresse."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(payload.url)
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Téléchargement de la photo impossible") from exc
    type_mime = r.headers.get("content-type", "").split(";")[0].strip()
    if r.status_code != 200 or type_mime not in TYPES_IMAGES:
        raise HTTPException(400, "Cette adresse ne renvoie pas une image JPEG, PNG ou WebP")
    if len(r.content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image trop lourde (maximum 5 Mo)")
    return await _poser_photo(modele_id, await enregistrer_fichier_catalogue(r.content, type_mime))


async def _poser_photo(modele_id: str, url: str) -> dict:
    actuel = await db.catalogue_modeles.find_one({"id": modele_id}, SANS_ID)
    if not actuel:
        raise HTTPException(404, "Fiche introuvable")
    await db.catalogue_modeles.update_one({"id": modele_id}, {"$set": {
        "photo_url": url, "modifie_apres_publication": bool(actuel.get("publie")), "updated_at": now_iso()}})
    return await db.catalogue_modeles.find_one({"id": modele_id}, SANS_ID)


# ---------------------------------------------------------------------------
# Consultation par le personnel des boutiques (recherche d'informations)
# ---------------------------------------------------------------------------
@consultation.get("")
async def rechercher_public(q: str = "", type_produit: str = "", marque: str = "",
                            ctx: Contexte = Depends(tout_le_personnel)):
    filtre: dict = {}
    if q.strip():
        motif = motif_recherche(q)
        filtre["$or"] = [{k: {"$regex": motif, "$options": "i"}} for k in ("nom", "marque", "reference")]
    if type_produit:
        filtre["type_produit"] = type_produit
    if marque:
        filtre["marque"] = marque
    modeles = await db.catalogue_publie.find(filtre, SANS_ID).sort([("marque", 1), ("nom", 1)]).to_list(500)
    # Lien vers la fiche correspondante dans le catalogue de la boutique
    chez_moi = {p["catalogue_id"]: p["id"] async for p in ctx.tdb.produits.find(
        {"catalogue_id": {"$in": [m["id"] for m in modeles]}}, {"_id": 0, "id": 1, "catalogue_id": 1})}
    marques = sorted({m["marque"] async for m in db.catalogue_publie.find({}, {"_id": 0, "marque": 1}) if m.get("marque")})
    return {"marques": marques, "modeles": [{**m, "produit_id": chez_moi.get(m["id"])} for m in modeles]}


@consultation.get("/{modele_id}")
async def fiche_publique(modele_id: str, ctx: Contexte = Depends(tout_le_personnel)):
    m = await db.catalogue_publie.find_one({"id": modele_id}, SANS_ID)
    if not m:
        raise HTTPException(404, "Fiche introuvable")
    # Pour un téléphone : les pièces détachées et accessoires compatibles
    pieces = await db.catalogue_publie.find({"modeles_compatibles": modele_id}, SANS_ID).sort("nom", 1).to_list(500)
    compatibles = await db.catalogue_publie.find({"id": {"$in": m.get("modeles_compatibles") or []}},
                                                 {"_id": 0, "id": 1, "marque": 1, "nom": 1}).to_list(500)
    ids = [modele_id] + [p["id"] for p in pieces]
    chez_moi = {p["catalogue_id"]: p async for p in ctx.tdb.produits.find(
        {"catalogue_id": {"$in": ids}}, {"_id": 0, "id": 1, "catalogue_id": 1, "prix_vente": 1, "stock": 1})}
    return {**m, "produit": chez_moi.get(modele_id), "compatibles": compatibles,
            "pieces": [{**p, "produit": chez_moi.get(p["id"])} for p in pieces]}
