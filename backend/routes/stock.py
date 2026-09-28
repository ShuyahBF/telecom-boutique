"""Stock : journal des mouvements (entrées / sorties) et bons de réception
fournisseur sur plusieurs lignes."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import Contexte, permission
from services import MOTIFS, entree_stock, est_stockable, prochain_numero, sortie_stock
from utils import new_id, now_iso, today_iso

router = APIRouter(tags=["Stock"])
# Droits requis (voir la table PERMISSIONS dans auth.py)
stock_dep = permission("stock")


@router.get("/stock/motifs")
async def motifs(_: Contexte = Depends(stock_dep)):
    return MOTIFS


@router.get("/stock/mouvements")
async def lister_mouvements(produit_id: str = "", ctx: Contexte = Depends(stock_dep)):
    filtre = {"produit_id": produit_id} if produit_id else {}
    return await ctx.tdb.mouvements.find(filtre).sort("date", -1).to_list(500)


class MouvementManuel(BaseModel):
    produit_id: str
    sens: Literal["E", "S"]
    quantite: int = Field(..., gt=0)
    motif: Literal["CASSE", "INVENT", "RETOUR", "AUTRE"] = "AUTRE"
    commentaire: str = Field("", max_length=255)


@router.post("/stock/mouvements", status_code=201)
async def mouvement_manuel(payload: MouvementManuel, ctx: Contexte = Depends(stock_dep)):
    """Correction manuelle (casse, inventaire...). Pour annuler une erreur,
    on saisit un mouvement inverse : le journal n'est jamais effacé."""
    produit = await ctx.tdb.produits.find_one({"id": payload.produit_id})
    if not produit:
        raise HTTPException(404, "Produit introuvable")
    if not est_stockable(produit):
        raise HTTPException(400, "Un service ne se stocke pas")
    fonction = entree_stock if payload.sens == "E" else sortie_stock
    return await fonction(ctx.tdb, produit, payload.quantite, payload.motif, "", payload.commentaire, ctx.auteur)


# ---------------------------------------------------------------------------
# Bons d'entrée (réceptions fournisseur)
# ---------------------------------------------------------------------------
class LigneBon(BaseModel):
    produit_id: str
    quantite: int = Field(..., gt=0)
    prix_achat: int = Field(0, ge=0)


class BonSaisie(BaseModel):
    fournisseur_id: str
    date: str = Field(default_factory=today_iso, pattern=r"^\d{4}-\d{2}-\d{2}$")
    reference_fournisseur: str = Field("", max_length=60)
    commentaire: str = Field("", max_length=1000)
    lignes: list[LigneBon] = Field(..., min_length=1, max_length=200)


async def _preparer_bon(ctx: Contexte, payload: BonSaisie) -> dict:
    fournisseur = await ctx.tdb.fournisseurs.find_one({"id": payload.fournisseur_id})
    if not fournisseur:
        raise HTTPException(400, "Fournisseur inconnu")
    ids = [l.produit_id for l in payload.lignes]
    produits = {p["id"]: p async for p in ctx.tdb.produits.find({"id": {"$in": ids}})}
    lignes = []
    for l in payload.lignes:
        p = produits.get(l.produit_id)
        if not p or not est_stockable(p):
            raise HTTPException(400, "Produit inconnu ou non stockable dans le bon")
        lignes.append({"produit_id": p["id"], "produit_nom": p["nom"], "reference": p["reference"],
                       "quantite": l.quantite, "prix_achat": l.prix_achat, "montant": l.quantite * l.prix_achat})
    return {"fournisseur_id": fournisseur["id"], "fournisseur_nom": fournisseur["nom"], "date": payload.date,
            "reference_fournisseur": payload.reference_fournisseur, "commentaire": payload.commentaire,
            "lignes": lignes, "montant_total": sum(l["montant"] for l in lignes)}


@router.get("/stock/bons")
async def lister_bons(ctx: Contexte = Depends(stock_dep)):
    return await ctx.tdb.bons_entree.find({}).sort([("date", -1), ("numero", -1)]).to_list(500)


@router.get("/stock/bons/{bon_id}")
async def lire_bon(bon_id: str, ctx: Contexte = Depends(stock_dep)):
    bon = await ctx.tdb.bons_entree.find_one({"id": bon_id})
    if not bon:
        raise HTTPException(404, "Bon introuvable")
    return bon


@router.post("/stock/bons", status_code=201)
async def creer_bon(payload: BonSaisie, ctx: Contexte = Depends(stock_dep)):
    bon = {"id": new_id(), "numero": await prochain_numero(ctx.boutique["id"], "BE"),
           **await _preparer_bon(ctx, payload), "valide": False, "date_validation": None,
           "created_at": now_iso(), **ctx.auteur}
    await ctx.tdb.bons_entree.insert_one(bon)
    return bon


@router.put("/stock/bons/{bon_id}")
async def modifier_bon(bon_id: str, payload: BonSaisie, ctx: Contexte = Depends(stock_dep)):
    bon = await ctx.tdb.bons_entree.find_one_and_update(
        {"id": bon_id, "valide": False}, {"$set": await _preparer_bon(ctx, payload)})
    if not bon:
        raise HTTPException(409, "Bon introuvable ou déjà validé")
    return bon


@router.post("/stock/bons/{bon_id}/valider")
async def valider_bon(bon_id: str, ctx: Contexte = Depends(stock_dep)):
    """Fait entrer en stock toutes les lignes, UNE seule fois : le passage
    valide=False -> True est atomique (un double-clic ne double pas le stock)."""
    bon = await ctx.tdb.bons_entree.find_one_and_update(
        {"id": bon_id, "valide": False}, {"$set": {"valide": True, "date_validation": now_iso()}})
    if not bon:
        raise HTTPException(409, "Bon introuvable ou déjà validé")
    for l in bon["lignes"]:
        produit = await ctx.tdb.produits.find_one({"id": l["produit_id"]})
        if not produit:
            continue
        await entree_stock(ctx.tdb, produit, l["quantite"], "ACHAT", bon["numero"],
                           f"Fournisseur : {bon['fournisseur_nom']}", ctx.auteur)
        if l.get("prix_achat"):
            # On mémorise le dernier prix d'achat sur la fiche produit
            await ctx.tdb.produits.update_one({"id": produit["id"]}, {"$set": {"prix_achat": l["prix_achat"]}})
    return bon


@router.delete("/stock/bons/{bon_id}")
async def supprimer_bon(bon_id: str, ctx: Contexte = Depends(stock_dep)):
    res = await ctx.tdb.bons_entree.delete_one({"id": bon_id, "valide": False})
    if not res.deleted_count:
        raise HTTPException(409, "Seul un bon non validé peut être supprimé")
    return {"ok": True}
