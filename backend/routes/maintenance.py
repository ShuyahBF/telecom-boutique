"""Maintenance (SAV) : dossiers de réparation des appareils déposés.

Chaque dépôt reçoit un numéro unique (MNT-2026-00001) et un code de suivi
imprévisible, imprimés sur le bon de dépôt. Le client suit l'avancement sur
le portail avec le numéro + son téléphone (ou le code de suivi).
"""
from __future__ import annotations

import secrets
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import Contexte, permission
from messagerie import lien_suivi, notifier_client_en_fond
from routes.documents import creer_document, enrichir
from routes.tiers import instantane_client
from services import entree_stock, est_stockable, prochain_numero, sortie_stock
from utils import new_id, now_iso, today_iso, motif_recherche

router = APIRouter(prefix="/maintenance", tags=["Maintenance (SAV)"])
# Droits requis (voir la table PERMISSIONS dans auth.py)
maintenance_dep = permission("maintenance")

STATUTS_SAV = {
    "RECU": "Appareil reçu",
    "DIAGNOSTIC": "Diagnostic en cours",
    "DEVIS": "Devis en attente d'accord",
    "ATTENTE_PIECE": "En attente de pièce",
    "REPARATION": "Réparation en cours",
    "PRET": "Réparé — prêt à être retiré",
    "IRREPARABLE": "Irréparable — à retirer",
    "RESTITUE": "Restitué au client",
}
# Barre de progression du portail (5 étapes) ; certains statuts sont ramenés à une étape voisine
ETAPES_SAV = ["RECU", "DIAGNOSTIC", "REPARATION", "PRET", "RESTITUE"]
_EQUIVALENCES = {"DEVIS": "DIAGNOSTIC", "ATTENTE_PIECE": "REPARATION", "IRREPARABLE": "PRET"}
StatutSav = Literal["RECU", "DIAGNOSTIC", "DEVIS", "ATTENTE_PIECE", "REPARATION", "PRET", "IRREPARABLE", "RESTITUE"]


def avec_libelles(d: dict) -> dict:
    statut = _EQUIVALENCES.get(d.get("statut"), d.get("statut"))
    return {**d, "statut_libelle": STATUTS_SAV.get(d.get("statut"), d.get("statut")),
            "etape": ETAPES_SAV.index(statut) + 1 if statut in ETAPES_SAV else 0,
            "historique": [{**h, "statut_libelle": STATUTS_SAV.get(h["statut"], h["statut"])} for h in d.get("historique", [])]}


def code_suivi() -> str:
    # 6 caractères faciles à lire (sans 0/O ni 1/I)
    return "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))


class DossierSaisie(BaseModel):
    client_id: str
    marque: str = Field(..., min_length=1, max_length=60)
    modele: str = Field(..., min_length=1, max_length=100)
    imei: str = Field("", max_length=40)
    couleur: str = Field("", max_length=40)
    code_deverrouillage: str = Field("", max_length=40)  # confidentiel, jamais publié
    accessoires_deposes: str = Field("", max_length=255)
    etat_visuel: str = Field("", max_length=1000)
    panne_declaree: str = Field(..., min_length=1, max_length=2000)
    date_prevue: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    technicien_id: Optional[str] = None
    diagnostic: str = Field("", max_length=3000)
    travaux_effectues: str = Field("", max_length=3000)
    devis_montant: Optional[int] = Field(None, ge=0)
    devis_accepte: Optional[bool] = None
    acompte: int = Field(0, ge=0)
    sous_garantie: bool = False


async def _technicien(ctx: Contexte, technicien_id: Optional[str]) -> dict:
    if not technicien_id:
        return {"technicien_id": None, "technicien_nom": ""}
    from db import db
    tech = await db.users.find_one({"id": technicien_id, "boutique_id": ctx.boutique["id"]}, {"_id": 0, "id": 1, "nom": 1})
    if not tech:
        raise HTTPException(400, "Technicien inconnu")
    return {"technicien_id": tech["id"], "technicien_nom": tech["nom"]}


async def _lire(ctx: Contexte, dossier_id: str) -> dict:
    d = await ctx.tdb.dossiers.find_one({"id": dossier_id})
    if not d:
        raise HTTPException(404, "Dossier introuvable")
    return d


@router.get("/statuts")
async def statuts(_: Contexte = Depends(maintenance_dep)):
    return STATUTS_SAV


@router.get("")
async def lister(statut: str = "", en_cours: bool = False, q: str = "", ctx: Contexte = Depends(maintenance_dep)):
    filtre: dict = {}
    if statut:
        filtre["statut"] = statut
    elif en_cours:
        filtre["statut"] = {"$ne": "RESTITUE"}
    if q.strip():
        import re
        motif = motif_recherche(q)
        filtre["$or"] = [{k: {"$regex": motif, "$options": "i"}}
                         for k in ("numero", "imei", "modele", "marque", "client.nom", "client.telephone")]
    return [avec_libelles(d) for d in await ctx.tdb.dossiers.find(filtre).sort("date_depot", -1).to_list(500)]


@router.get("/{dossier_id}")
async def lire(dossier_id: str, ctx: Contexte = Depends(maintenance_dep)):
    return avec_libelles(await _lire(ctx, dossier_id))


@router.post("", status_code=201)
async def deposer(payload: DossierSaisie, ctx: Contexte = Depends(maintenance_dep)):
    client = await ctx.tdb.clients.find_one({"id": payload.client_id})
    if not client:
        raise HTTPException(400, "Client inconnu")
    dossier = {
        **payload.model_dump(exclude={"technicien_id"}), **await _technicien(ctx, payload.technicien_id),
        "id": new_id(), "numero": await prochain_numero(ctx.boutique["id"], "MNT"), "code_suivi": code_suivi(),
        "client": instantane_client(client), "statut": "RECU", "date_depot": now_iso(),
        "date_restitution": None, "facture_id": None, "pieces": [],
        "historique": [{"date": now_iso(), "statut": "RECU", "commentaire": "", "par": ctx.user.get("nom", "")}],
    }
    await ctx.tdb.dossiers.insert_one(dossier)
    notifier_client_en_fond(ctx.boutique, "MAINT_DEPOT", {**client, **dossier["client"]},
                            {"dossier": avec_libelles(dossier), "client": dossier["client"]},
                            lien_suivi(ctx.boutique, "dossier", dossier))
    return avec_libelles(dossier)


@router.put("/{dossier_id}")
async def modifier(dossier_id: str, payload: DossierSaisie, ctx: Contexte = Depends(maintenance_dep)):
    client = await ctx.tdb.clients.find_one({"id": payload.client_id})
    if not client:
        raise HTTPException(400, "Client inconnu")
    maj = {**payload.model_dump(exclude={"technicien_id"}), **await _technicien(ctx, payload.technicien_id),
           "client": instantane_client(client)}
    d = await ctx.tdb.dossiers.find_one_and_update({"id": dossier_id}, {"$set": maj})
    if not d:
        raise HTTPException(404, "Dossier introuvable")
    return avec_libelles(d)


class ChangementStatut(BaseModel):
    statut: StatutSav
    commentaire: str = Field("", max_length=255)  # visible par le client sur le portail


@router.post("/{dossier_id}/statut")
async def changer_statut(dossier_id: str, payload: ChangementStatut, ctx: Contexte = Depends(maintenance_dep)):
    avant = await _lire(ctx, dossier_id)
    maj: dict = {"statut": payload.statut}
    if payload.statut == "RESTITUE" and not avant.get("date_restitution"):
        maj["date_restitution"] = now_iso()
    d = await ctx.tdb.dossiers.find_one_and_update(
        {"id": dossier_id},
        {"$set": maj, "$push": {"historique": {"date": now_iso(), "statut": payload.statut,
                                               "commentaire": payload.commentaire, "par": ctx.user.get("nom", "")}}})
    if avant["statut"] != payload.statut:
        notifier_client_en_fond(ctx.boutique, "MAINT_STATUT", d["client"],
                                {"dossier": avec_libelles(d), "client": d["client"]}, lien_suivi(ctx.boutique, "dossier", d))
    return avec_libelles(d)


class PieceSaisie(BaseModel):
    produit_id: str
    quantite: int = Field(1, gt=0)


@router.post("/{dossier_id}/pieces")
async def ajouter_piece(dossier_id: str, payload: PieceSaisie, ctx: Contexte = Depends(maintenance_dep)):
    """Pièce consommée pendant la réparation : SORT du stock immédiatement."""
    d = await _lire(ctx, dossier_id)
    produit = await ctx.tdb.produits.find_one({"id": payload.produit_id})
    if not produit:
        raise HTTPException(404, "Produit introuvable")
    mouvement_id = None
    if est_stockable(produit):
        mvt = await sortie_stock(ctx.tdb, produit, payload.quantite, "MAINT", d["numero"], "", ctx.auteur)
        mouvement_id = mvt["id"]
    piece = {"id": new_id(), "produit_id": produit["id"], "nom": produit["nom"], "reference": produit["reference"],
             "quantite": payload.quantite, "prix_vente": produit["prix_vente"], "stockable": est_stockable(produit),
             "mouvement_id": mouvement_id, "date": now_iso()}
    d = await ctx.tdb.dossiers.find_one_and_update({"id": dossier_id}, {"$push": {"pieces": piece}})
    return avec_libelles(d)


@router.delete("/{dossier_id}/pieces/{piece_id}")
async def retirer_piece(dossier_id: str, piece_id: str, ctx: Contexte = Depends(maintenance_dep)):
    """Retirer une pièce du dossier = la remettre en stock."""
    d = await _lire(ctx, dossier_id)
    piece = next((p for p in d.get("pieces", []) if p["id"] == piece_id), None)
    if not piece:
        raise HTTPException(404, "Pièce introuvable")
    res = await ctx.tdb.dossiers.update_one({"id": dossier_id, "pieces.id": piece_id}, {"$pull": {"pieces": {"id": piece_id}}})
    if res.modified_count and piece.get("stockable"):
        produit = await ctx.tdb.produits.find_one({"id": piece["produit_id"]})
        if produit:
            await entree_stock(ctx.tdb, produit, piece["quantite"], "RETOUR", d["numero"], "Pièce retirée du dossier", ctx.auteur)
    return avec_libelles(await _lire(ctx, dossier_id))


@router.post("/{dossier_id}/facture")
async def generer_facture(dossier_id: str, ctx: Contexte = Depends(maintenance_dep)):
    """Facture de réparation (brouillon) : main d'œuvre (montant du devis) +
    pièces utilisées. Les pièces étant DÉJÀ sorties du stock par le dossier,
    elles sont facturées en lignes libres (sans produit) pour ne pas être
    déstockées une deuxième fois à la validation."""
    if not ctx.peut("facturation"):
        raise HTTPException(403, "La facturation est réservée au DG, aux commerciaux et au comptable")
    d = await _lire(ctx, dossier_id)
    if d.get("facture_id"):
        existante = await ctx.tdb.documents.find_one({"id": d["facture_id"]})
        if existante and existante["statut"] != "ANNULE":
            raise HTTPException(409, "Ce dossier a déjà une facture")
    lignes = []
    if d.get("devis_montant"):
        lignes.append({"designation": f"Main d'œuvre — {d.get('travaux_effectues') or 'réparation'}"[:255],
                       "quantite": 1, "prix_unitaire": d["devis_montant"]})
    for p in d.get("pieces", []):
        lignes.append({"designation": f"Pièce : {p['nom']}", "quantite": p["quantite"], "prix_unitaire": p["prix_vente"]})
    if not lignes:
        raise HTTPException(400, "Renseignez le montant du devis ou ajoutez des pièces avant de facturer")
    client = await ctx.tdb.clients.find_one({"id": d["client_id"]}) or {"id": d["client_id"], **d["client"]}
    facture = await creer_document(ctx, "FAC", client, lignes,
                                   f"Réparation {d['marque']} {d['modele']} — dossier {d['numero']}",
                                   origine={"dossier_origine": {"id": d["id"], "numero": d["numero"]}})
    if d.get("acompte"):
        acompte = {"id": new_id(), "montant": d["acompte"], "mode": "ESP", "date": today_iso(),
                   "reference": f"Acompte dossier {d['numero']}", "saisi_par": ctx.user.get("nom", ""), "created_at": now_iso()}
        facture = await ctx.tdb.documents.find_one_and_update({"id": facture["id"]}, {"$push": {"reglements": acompte}})
        from journal_paiements import journaliser
        await journaliser(ctx.boutique["id"], f"reglement-{acompte['id']}", canal="CAISSE", mode="ESP",
                          montant=d["acompte"], statut="SUCCES", objet=f"Acompte réparation {d['numero']}",
                          client_nom=d["client"]["nom"], saisi_par=ctx.user.get("nom", ""),
                          devise=ctx.boutique.get("devise", "FCFA"), liens={"document_id": facture["id"]})
    await ctx.tdb.dossiers.update_one({"id": dossier_id}, {"$set": {"facture_id": facture["id"]}})
    return enrichir(facture, ctx.boutique)
