"""Clients et fournisseurs de la boutique."""
from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from auth import Contexte, atelier, ventes
from utils import new_id, normaliser_telephone, now_iso

router = APIRouter(tags=["Clients & fournisseurs"])


def _recherche(q: str, champs: list[str]) -> dict:
    if not q.strip():
        return {}
    motif = re.escape(q.strip())
    return {"$or": [{c: {"$regex": motif, "$options": "i"}} for c in champs]}


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
class ClientSaisie(BaseModel):
    type_client: Literal["PART", "ENTR"] = "PART"
    nom: str = Field(..., min_length=1, max_length=150)
    telephone: str = Field(..., min_length=6, max_length=30)
    email: Optional[EmailStr] = None
    adresse: str = Field("", max_length=500)
    ifu: str = Field("", max_length=50)
    notes: str = Field("", max_length=2000)


def _client_doc(payload: ClientSaisie) -> dict:
    d = payload.model_dump()
    d["telephone"] = normaliser_telephone(d["telephone"])
    d["email"] = d.get("email") or ""
    d["nom"] = d["nom"].strip()
    return d


@router.get("/clients")
async def lister_clients(q: str = "", ctx: Contexte = Depends(atelier)):
    filtre = _recherche(q, ["nom", "telephone", "email"])
    return await ctx.tdb.clients.find(filtre).sort("nom", 1).to_list(1000)


@router.get("/clients/{client_id}")
async def lire_client(client_id: str, ctx: Contexte = Depends(atelier)):
    client = await ctx.tdb.clients.find_one({"id": client_id})
    if not client:
        raise HTTPException(404, "Client introuvable")
    # Historique du client : documents, commandes, réparations
    client["documents"] = await ctx.tdb.documents.find(
        {"client_id": client_id}, {"_id": 0, "id": 1, "type_document": 1, "numero": 1, "date": 1,
                                   "total_ttc": 1, "statut": 1}).sort("date", -1).to_list(100)
    client["dossiers"] = await ctx.tdb.dossiers.find(
        {"client_id": client_id}, {"_id": 0, "id": 1, "numero": 1, "marque": 1, "modele": 1,
                                   "statut": 1, "date_depot": 1}).sort("date_depot", -1).to_list(100)
    return client


@router.post("/clients", status_code=201)
async def creer_client(payload: ClientSaisie, ctx: Contexte = Depends(atelier)):
    doc = {"id": new_id(), **_client_doc(payload), "created_at": now_iso()}
    await ctx.tdb.clients.insert_one(doc)
    return doc


@router.put("/clients/{client_id}")
async def modifier_client(client_id: str, payload: ClientSaisie, ctx: Contexte = Depends(atelier)):
    doc = await ctx.tdb.clients.find_one_and_update({"id": client_id}, {"$set": _client_doc(payload)})
    if not doc:
        raise HTTPException(404, "Client introuvable")
    return doc


async def trouver_ou_creer_client(ctx_tdb, nom: str, telephone: str, email: str = "") -> dict:
    """Retrouve un client par son téléphone ou le crée (portail, comptoir)."""
    telephone = normaliser_telephone(telephone)
    client = await ctx_tdb.clients.find_one({"telephone": telephone})
    if client is None:
        client = {"id": new_id(), "type_client": "PART", "nom": nom.strip(), "telephone": telephone,
                  "email": email or "", "adresse": "", "ifu": "", "notes": "", "created_at": now_iso()}
        await ctx_tdb.clients.insert_one(client)
    elif email and not client.get("email"):
        # On complète la fiche sans jamais écraser une donnée existante
        await ctx_tdb.clients.update_one({"id": client["id"]}, {"$set": {"email": email}})
        client["email"] = email
    return client


def instantane_client(client: dict) -> dict:
    """Copie figée des coordonnées du client, conservée sur les documents
    (une facture ne doit pas changer si la fiche client est modifiée ensuite)."""
    return {k: client.get(k, "") for k in ("nom", "telephone", "email", "adresse", "ifu")}


# ---------------------------------------------------------------------------
# Fournisseurs
# ---------------------------------------------------------------------------
class FournisseurSaisie(BaseModel):
    nom: str = Field(..., min_length=1, max_length=150)
    contact: str = Field("", max_length=100)
    telephone: str = Field("", max_length=30)
    email: Optional[EmailStr] = None
    adresse: str = Field("", max_length=500)
    pays: str = Field("", max_length=60)
    notes: str = Field("", max_length=2000)
    actif: bool = True


@router.get("/fournisseurs")
async def lister_fournisseurs(q: str = "", ctx: Contexte = Depends(ventes)):
    return await ctx.tdb.fournisseurs.find(_recherche(q, ["nom", "contact", "telephone"])).sort("nom", 1).to_list(1000)


@router.post("/fournisseurs", status_code=201)
async def creer_fournisseur(payload: FournisseurSaisie, ctx: Contexte = Depends(ventes)):
    doc = {"id": new_id(), **payload.model_dump(), "email": payload.email or "",
           "telephone": normaliser_telephone(payload.telephone), "created_at": now_iso()}
    await ctx.tdb.fournisseurs.insert_one(doc)
    return doc


@router.put("/fournisseurs/{fournisseur_id}")
async def modifier_fournisseur(fournisseur_id: str, payload: FournisseurSaisie, ctx: Contexte = Depends(ventes)):
    maj = {**payload.model_dump(), "email": payload.email or "", "telephone": normaliser_telephone(payload.telephone)}
    doc = await ctx.tdb.fournisseurs.find_one_and_update({"id": fournisseur_id}, {"$set": maj})
    if not doc:
        raise HTTPException(404, "Fournisseur introuvable")
    return doc
