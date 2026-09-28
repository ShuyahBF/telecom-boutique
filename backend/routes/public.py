"""Portail PUBLIC (sans connexion) : annuaire des boutiques (carrousel,
recherche par nom ou code marchand, QR code), vitrine de chaque boutique,
commande, suivi de commande et de réparation, demandes de conseil.

Sécurité : seules des données publiques sont renvoyées (jamais le code de
déverrouillage d'un appareil, les notes internes, les prix d'achat...), et
chaque boutique est résolue par son adresse (slug) puis cloisonnée par TenantDB.
"""
from __future__ import annotations

import math
import re
import secrets
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from db import SANS_ID, TenantDB, db
from messagerie import lien_suivi, notifier_en_fond
from routes.commandes import avec_libelles as cmd_libelles
from routes.maintenance import avec_libelles as sav_libelles
from routes.paiements import creer_page_paiement, paiement_disponible
from routes.tiers import instantane_client, trouver_ou_creer_client
from services import est_stockable, prochain_numero
from utils import new_id, normaliser_telephone, now_iso

router = APIRouter(prefix="/public", tags=["Portail public"])

CHAMPS_BOUTIQUE_PUBLICS = ("id", "nom", "slug", "code_marchand", "slogan", "logo_url", "ville", "adresse",
                           "telephone", "email", "couleur", "devise", "mise_en_avant")
CHAMPS_PRODUIT_PUBLICS = ("id", "reference", "nom", "slug", "type_produit", "categorie_id", "categorie_nom", "marque",
                          "description", "caracteristiques", "image_url", "prix_vente", "garantie_mois", "created_at")


def _boutique_publique(b: dict) -> dict:
    publique = {k: b.get(k) for k in CHAMPS_BOUTIQUE_PUBLICS}
    publique["paiement_mobile_money"] = bool(b.get("paiement_mobile_money", True) and paiement_disponible())
    return publique


def _produit_public(p: dict) -> dict:
    publique = {k: p.get(k) for k in CHAMPS_PRODUIT_PUBLICS}
    # On indique seulement « disponible ou non », jamais la quantité exacte en stock
    publique["disponible"] = (not est_stockable(p)) or p.get("stock", 0) > 0
    publique["stock_max"] = None if not est_stockable(p) else max(p.get("stock", 0), 0)
    return publique


async def _boutique(slug: str) -> dict:
    """Boutique ACTIVE désignée par son adresse (slug) ou son code marchand."""
    b = await db.boutiques.find_one({"slug": slug, "actif": True}, SANS_ID)
    if not b:
        b = await db.boutiques.find_one({"code_marchand": slug.upper(), "actif": True}, SANS_ID)
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    return b


# ---------------------------------------------------------------------------
# Annuaire des boutiques
# ---------------------------------------------------------------------------
@router.get("/boutiques")
async def annuaire(q: str = ""):
    """Liste pour le carrousel ; q = nom (partiel) OU code marchand (exact)."""
    filtre: dict = {"actif": True}
    if q.strip():
        motif = re.escape(q.strip())
        filtre["$or"] = [{"nom": {"$regex": motif, "$options": "i"}},
                         {"ville": {"$regex": motif, "$options": "i"}},
                         {"code_marchand": q.strip().upper()}]
    boutiques = await db.boutiques.find(filtre, SANS_ID).sort([("mise_en_avant", -1), ("ordre", 1), ("nom", 1)]).to_list(500)
    return [_boutique_publique(b) for b in boutiques]


@router.get("/b/{slug}")
async def boutique(slug: str):
    b = await _boutique(slug)
    tdb = TenantDB(b["id"])
    categories = await tdb.categories.find({}, {"_id": 0, "id": 1, "nom": 1, "slug": 1}).sort([("ordre", 1), ("nom", 1)]).to_list(200)
    marques = sorted({p.get("marque") async for p in tdb.produits.find({"actif": True, "visible_portail": True}, {"_id": 0, "marque": 1}) if p.get("marque")})
    return {**_boutique_publique(b), "categories": categories, "marques": marques}


@router.get("/b/{slug}/produits")
async def produits(slug: str, q: str = "", categorie: str = "", marque: str = "", tri: str = "recent",
                   page: int = 1, par_page: int = 12):
    b = await _boutique(slug)
    filtre: dict = {"actif": True, "visible_portail": True}
    if q.strip():
        motif = re.escape(q.strip())
        filtre["$or"] = [{"nom": {"$regex": motif, "$options": "i"}}, {"marque": {"$regex": motif, "$options": "i"}},
                         {"description": {"$regex": motif, "$options": "i"}}]
    if categorie:
        filtre["categorie_id"] = categorie
    if marque:
        filtre["marque"] = marque
    ordre = {"prix_asc": [("prix_vente", 1)], "prix_desc": [("prix_vente", -1)], "nom": [("nom", 1)]}.get(tri, [("created_at", -1)])
    tdb = TenantDB(b["id"])
    total = await tdb.produits.count_documents(filtre)
    par_page = min(max(par_page, 1), 48)
    page = max(page, 1)
    liste = await tdb.produits.find(filtre).sort(ordre).skip((page - 1) * par_page).limit(par_page).to_list(par_page)
    return {"total": total, "page": page, "pages": max(math.ceil(total / par_page), 1),
            "produits": [_produit_public(p) for p in liste]}


@router.get("/b/{slug}/produits/{produit_slug}")
async def produit(slug: str, produit_slug: str):
    b = await _boutique(slug)
    tdb = TenantDB(b["id"])
    p = await tdb.produits.find_one({"slug": produit_slug, "actif": True, "visible_portail": True})
    if not p:
        raise HTTPException(404, "Produit introuvable")
    similaires = await tdb.produits.find({"categorie_id": p["categorie_id"], "actif": True, "visible_portail": True,
                                          "id": {"$ne": p["id"]}}).limit(4).to_list(4)
    return {**_produit_public(p), "similaires": [_produit_public(s) for s in similaires]}


# ---------------------------------------------------------------------------
# Commande
# ---------------------------------------------------------------------------
class LignePanier(BaseModel):
    produit_id: str
    quantite: int = Field(..., gt=0, le=100)


class CommandeSaisie(BaseModel):
    nom: str = Field(..., min_length=2, max_length=150)
    telephone: str = Field(..., min_length=8, max_length=30)
    email: Optional[EmailStr] = None
    mode_livraison: Literal["RETRAIT", "LIVRAISON"] = "RETRAIT"
    adresse_livraison: str = Field("", max_length=500)
    message_client: str = Field("", max_length=1000)
    mode_paiement: Literal["A_LA_LIVRAISON", "MOBILE_MONEY"] = "A_LA_LIVRAISON"
    numero_mobile_money: str = Field("", max_length=30)
    lignes: list[LignePanier] = Field(..., min_length=1, max_length=50)


@router.post("/b/{slug}/commandes", status_code=201)
async def commander(slug: str, payload: CommandeSaisie):
    b = await _boutique(slug)
    tdb = TenantDB(b["id"])
    telephone = normaliser_telephone(payload.telephone)
    if len(telephone.lstrip("+")) < 8:
        raise HTTPException(400, "Numéro de téléphone invalide")
    if payload.mode_livraison == "LIVRAISON" and not payload.adresse_livraison.strip():
        raise HTTPException(400, "Indiquez l'adresse de livraison")
    if payload.mode_paiement == "MOBILE_MONEY" and not _boutique_publique(b)["paiement_mobile_money"]:
        raise HTTPException(400, "Le paiement Mobile Money n'est pas disponible pour cette boutique")

    # Prix et disponibilité TOUJOURS relus en base (jamais repris du navigateur)
    ids = [l.produit_id for l in payload.lignes]
    catalogue = {p["id"]: p async for p in tdb.produits.find({"id": {"$in": ids}, "actif": True, "visible_portail": True})}
    lignes = []
    for l in payload.lignes:
        p = catalogue.get(l.produit_id)
        if not p:
            raise HTTPException(400, "Un article du panier n'est plus disponible")
        if est_stockable(p) and p.get("stock", 0) < l.quantite:
            raise HTTPException(409, f"Stock insuffisant pour « {p['nom']} » ({max(p.get('stock', 0), 0)} disponible(s))")
        lignes.append({"produit_id": p["id"], "nom": p["nom"], "reference": p["reference"], "quantite": l.quantite,
                       "prix_unitaire": p["prix_vente"], "montant": p["prix_vente"] * l.quantite})

    client = await trouver_ou_creer_client(tdb, payload.nom, telephone, payload.email or "")
    commande = {
        "id": new_id(), "numero": await prochain_numero(b["id"], "CMD"), "client_id": client["id"],
        "client": {**instantane_client(client), "nom": client["nom"], "email": payload.email or client.get("email", "")},
        "date": now_iso(), "date_maj": now_iso(), "statut": "RECUE", "mode_livraison": payload.mode_livraison,
        "adresse_livraison": payload.adresse_livraison.strip(), "message_client": payload.message_client.strip(),
        "note_interne": "", "lignes": lignes, "total": sum(l["montant"] for l in lignes), "facture_id": None,
        "paiement": {"mode": payload.mode_paiement, "statut": "NON_PAYEE", "deposit_id": None, "montant_paye": 0},
        "historique": [{"date": now_iso(), "statut": "RECUE", "par": "Client (portail)"}],
    }
    await tdb.commandes.insert_one(commande)

    lien = lien_suivi(b, "commande", commande)
    if commande["client"].get("email"):
        notifier_en_fond(b, "CMD_RECUE", commande["client"]["email"], {"commande": commande, "client": commande["client"]}, lien)
    notifier_en_fond(b, "EQUIPE_CMD", None, {"commande": commande, "client": commande["client"]}, lien)

    redirection = None
    if payload.mode_paiement == "MOBILE_MONEY":
        redirection = await creer_page_paiement(b, commande, payload.numero_mobile_money or telephone)
    return {"numero": commande["numero"], "total": commande["total"], "telephone": telephone,
            "redirect_url": redirection}


@router.get("/b/{slug}/commandes/suivi")
async def suivi_commande(slug: str, numero: str, telephone: str):
    """Le n° de commande ET le téléphone doivent correspondre (le n° seul est prévisible)."""
    b = await _boutique(slug)
    cmd = await TenantDB(b["id"]).commandes.find_one(
        {"numero": numero.strip().upper(), "client.telephone": normaliser_telephone(telephone)})
    if not cmd:
        raise HTTPException(404, "Aucune commande ne correspond à ce numéro et ce téléphone")
    c = cmd_libelles(cmd)
    return {k: c.get(k) for k in ("numero", "date", "date_maj", "statut", "statut_libelle", "etape", "mode_livraison",
                                  "lignes", "total", "historique")} | {"paiement": {
        "mode": c["paiement"]["mode"], "statut": c["paiement"]["statut"]}}


# ---------------------------------------------------------------------------
# Suivi de réparation
# ---------------------------------------------------------------------------
@router.get("/b/{slug}/maintenance/suivi")
async def suivi_reparation(slug: str, numero: str, secret: str):
    """secret = téléphone du client OU code de suivi du bon de dépôt."""
    b = await _boutique(slug)
    d = await TenantDB(b["id"]).dossiers.find_one({
        "numero": numero.strip().upper(),
        "$or": [{"client.telephone": normaliser_telephone(secret) or "-"}, {"code_suivi": secret.strip().upper()}],
    })
    if not d:
        raise HTTPException(404, "Aucun dossier ne correspond à ces informations")
    d = sav_libelles(d)
    publics = ("numero", "marque", "modele", "statut", "statut_libelle", "etape", "date_depot", "date_prevue",
               "date_restitution", "diagnostic", "devis_montant", "devis_accepte", "sous_garantie")
    return {**{k: d.get(k) for k in publics},
            "historique": [{k: h.get(k) for k in ("date", "statut", "statut_libelle", "commentaire")} for h in d["historique"]]}


# ---------------------------------------------------------------------------
# Demandes de conseil (fil de discussion privé, accessible par lien secret)
# ---------------------------------------------------------------------------
class ConseilSaisie(BaseModel):
    nom: str = Field(..., min_length=2, max_length=150)
    telephone: str = Field(..., min_length=8, max_length=30)
    email: Optional[EmailStr] = None
    sujet: str = Field(..., min_length=2, max_length=200)
    produit_id: Optional[str] = None
    texte: str = Field(..., min_length=2, max_length=5000)


def _conversation_publique(c: dict) -> dict:
    return {"jeton": c["jeton"], "sujet": c["sujet"], "statut": c["statut"], "date_creation": c["date_creation"],
            "produit": c.get("produit"), "nom": c["nom"],
            "messages": [{k: m.get(k) for k in ("auteur_type", "auteur_nom", "texte", "date")} for m in c["messages"]]}


@router.post("/b/{slug}/conseils", status_code=201)
async def demander_conseil(slug: str, payload: ConseilSaisie):
    b = await _boutique(slug)
    tdb = TenantDB(b["id"])
    produit_info = None
    if payload.produit_id:
        p = await tdb.produits.find_one({"id": payload.produit_id, "visible_portail": True})
        if p:
            produit_info = {"id": p["id"], "nom": p["nom"], "slug": p["slug"]}
    telephone = normaliser_telephone(payload.telephone)
    client = await tdb.clients.find_one({"telephone": telephone})
    message = {"id": new_id(), "auteur_type": "CLIENT", "auteur_nom": payload.nom.strip(), "texte": payload.texte.strip(),
               "date": now_iso(), "lu": False}
    conv = {"id": new_id(), "jeton": secrets.token_urlsafe(24), "client_id": client["id"] if client else None,
            "nom": payload.nom.strip(), "telephone": telephone, "email": payload.email or "",
            "sujet": payload.sujet.strip(), "produit": produit_info, "statut": "ATTENTE",
            "date_creation": now_iso(), "date_maj": now_iso(), "messages": [message]}
    await tdb.conversations.insert_one(conv)
    notifier_en_fond(b, "EQUIPE_CONSEIL", None, {"conversation": conv, "message": message})
    return {"jeton": conv["jeton"]}


async def _conversation(slug: str, jeton: str) -> tuple[dict, dict]:
    b = await _boutique(slug)
    conv = await TenantDB(b["id"]).conversations.find_one({"jeton": jeton})
    if not conv:
        raise HTTPException(404, "Conversation introuvable")
    return b, conv


@router.get("/b/{slug}/conseils/{jeton}")
async def lire_conversation(slug: str, jeton: str):
    _, conv = await _conversation(slug, jeton)
    return _conversation_publique(conv)


class MessageClient(BaseModel):
    texte: str = Field(..., min_length=1, max_length=5000)


@router.post("/b/{slug}/conseils/{jeton}")
async def repondre_conversation(slug: str, jeton: str, payload: MessageClient):
    b, conv = await _conversation(slug, jeton)
    if conv["statut"] == "CLOS":
        raise HTTPException(409, "Cette conversation est close")
    message = {"id": new_id(), "auteur_type": "CLIENT", "auteur_nom": conv["nom"], "texte": payload.texte.strip(),
               "date": now_iso(), "lu": False}
    conv = await TenantDB(b["id"]).conversations.find_one_and_update(
        {"jeton": jeton}, {"$push": {"messages": message}, "$set": {"statut": "ATTENTE", "date_maj": now_iso()}})
    notifier_en_fond(b, "EQUIPE_CONSEIL", None, {"conversation": conv, "message": message})
    return _conversation_publique(conv)
