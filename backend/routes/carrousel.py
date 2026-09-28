"""Écran « Carrousel WhatsApp » de la boutique : état du service, destinataires
(clients ayant accepté les offres WhatsApp), envoi d'une campagne et historique.
La logique d'envoi est dans carrousel_whatsapp.py."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

import carrousel_whatsapp as service
from auth import Contexte, permission
from db import TenantDB
from routes.public import EN_VENTE
from utils import new_id, now_iso

router = APIRouter(prefix="/boutique/carrousel", tags=["Carrousel WhatsApp (boutique)"])
messagerie = permission("messagerie")

# Clients joignables : consentement donné ET numéro de téléphone renseigné
CONSENTANTS = {"accepte_whatsapp": True, "telephone": {"$nin": [None, ""]}}


@router.get("")
async def etat(ctx: Contexte = Depends(messagerie)):
    """État du service + nombre de messages envoyés ce mois (base de la future facturation)."""
    mois = now_iso()[:7]
    campagnes = await ctx.tdb.campagnes_whatsapp.find({"date": {"$regex": f"^{mois}"}}).to_list(None)
    return {
        "configure": service.carrousel_configure(),
        "cartes_min": service.CARTES_MIN, "cartes_max": service.CARTES_MAX,
        "destinataires_max": service.DESTINATAIRES_MAX,
        "nb_consentants": await ctx.tdb.clients.count_documents(CONSENTANTS),
        "mois_envoyes": sum(c.get("envoyes", 0) for c in campagnes),
    }


@router.get("/produits")
async def produits(ctx: Contexte = Depends(messagerie)):
    """Produits proposables : en vente sur la vitrine, avec une photo accessible en ligne
    (WhatsApp va chercher l'image à son adresse publique)."""
    liste = await ctx.tdb.produits.find({**EN_VENTE, "image_url": {"$regex": "^https://"}}).sort("nom", 1).to_list(500)
    return [{"id": p["id"], "nom": p["nom"], "marque": p.get("marque", ""), "prix_vente": p.get("prix_vente"),
             "image_url": p["image_url"], "slug": p["slug"]} for p in liste]


@router.get("/destinataires")
async def destinataires(ctx: Contexte = Depends(messagerie)):
    """Clients ayant accepté de recevoir les offres de la boutique par WhatsApp."""
    liste = await ctx.tdb.clients.find(CONSENTANTS).sort("nom", 1).to_list(2000)
    return [{"id": c["id"], "nom": c["nom"], "telephone": c["telephone"],
             "accepte_whatsapp_le": c.get("accepte_whatsapp_le")} for c in liste]


class Campagne(BaseModel):
    produit_ids: list[str] = Field(..., min_length=service.CARTES_MIN, max_length=service.CARTES_MAX)
    message: str = Field(..., min_length=3, max_length=500)
    client_ids: list[str] = Field(..., min_length=1, max_length=service.DESTINATAIRES_MAX)


async def _executer(boutique: dict, campagne_id: str, message: str, cartes: list[dict], clients: list[dict]) -> None:
    """Envoi en arrière-plan, destinataire par destinataire ; résultat enregistré au fil de l'eau."""
    tdb = TenantDB(boutique["id"])
    resultats, envoyes, echecs = [], 0, 0
    async with httpx.AsyncClient(timeout=20) as client_http:
        for c in clients:
            statut, erreur = await service.envoyer_a(client_http, c["telephone"], boutique, message, cartes)
            envoyes += statut == "ENVOYE"
            echecs += statut == "ECHEC"
            resultats.append({"client_id": c["id"], "nom": c["nom"], "telephone": c["telephone"],
                              "statut": statut, "erreur": erreur})
    await tdb.campagnes_whatsapp.update_one({"id": campagne_id}, {"$set": {
        "statut": "TERMINEE", "envoyes": envoyes, "echecs": echecs, "resultats": resultats, "fin": now_iso()}})


@router.post("/envoyer", status_code=202)
async def envoyer(payload: Campagne, taches: BackgroundTasks, ctx: Contexte = Depends(messagerie)):
    if not service.carrousel_configure():
        raise HTTPException(503, "Le carrousel WhatsApp n'est pas encore activé sur la plateforme adLyn")
    ids_produits = list(dict.fromkeys(payload.produit_ids))  # ordre choisi conservé, doublons retirés
    if len(ids_produits) < service.CARTES_MIN:
        raise HTTPException(400, f"Choisissez au moins {service.CARTES_MIN} produits différents")
    trouves = {p["id"]: p async for p in ctx.tdb.produits.find(
        {"id": {"$in": ids_produits}, **EN_VENTE, "image_url": {"$regex": "^https://"}})}
    if len(trouves) != len(ids_produits):
        raise HTTPException(400, "Un produit choisi n'est plus en vente ou n'a pas de photo")
    cartes = [service.carte(trouves[i], ctx.boutique) for i in ids_produits]
    # Seuls les clients ayant donné leur accord sont retenus (jamais sur la seule foi du navigateur)
    clients = await ctx.tdb.clients.find({"id": {"$in": list(dict.fromkeys(payload.client_ids))}, **CONSENTANTS}).to_list(None)
    if not clients:
        raise HTTPException(400, "Aucun destinataire n'a accepté de recevoir vos offres par WhatsApp")
    campagne = {
        "id": new_id(), "date": now_iso(), "auteur": ctx.user.get("nom", ""), "message": payload.message.strip(),
        "modele": service.nom_modele(len(cartes)), "cartes": cartes, "nb_destinataires": len(clients),
        "statut": "EN_COURS", "envoyes": 0, "echecs": 0, "resultats": [],
    }
    await ctx.tdb.campagnes_whatsapp.insert_one(dict(campagne))
    taches.add_task(_executer, ctx.boutique, campagne["id"], campagne["message"], cartes, clients)
    return {"id": campagne["id"], "nb_destinataires": len(clients), "ignores": len(payload.client_ids) - len(clients)}


@router.get("/campagnes")
async def campagnes(ctx: Contexte = Depends(messagerie)):
    """Historique des envois (les plus récents d'abord)."""
    return await ctx.tdb.campagnes_whatsapp.find().sort("date", -1).to_list(100)
