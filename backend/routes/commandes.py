"""Commandes passées sur le portail public (côté personnel de la boutique)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import Contexte, ventes
from messagerie import lien_suivi, notifier_en_fond
from routes.documents import creer_document, enrichir
from utils import now_iso

router = APIRouter(prefix="/commandes", tags=["Commandes en ligne"])

STATUTS_COMMANDE = {
    "RECUE": "Reçue", "CONFIRMEE": "Confirmée", "PREPARATION": "En préparation",
    "PRETE": "Prête (retrait / expédition)", "LIVREE": "Livrée", "ANNULEE": "Annulée",
}
ETAPES_COMMANDE = ["RECUE", "CONFIRMEE", "PREPARATION", "PRETE", "LIVREE"]


def avec_libelles(cmd: dict) -> dict:
    return {**cmd, "statut_libelle": STATUTS_COMMANDE.get(cmd.get("statut"), cmd.get("statut")),
            "etape": ETAPES_COMMANDE.index(cmd["statut"]) + 1 if cmd.get("statut") in ETAPES_COMMANDE else 0}


@router.get("/statuts")
async def statuts(_: Contexte = Depends(ventes)):
    return STATUTS_COMMANDE


@router.get("")
async def lister(statut: str = "", ctx: Contexte = Depends(ventes)):
    filtre = {"statut": statut} if statut else {}
    return [avec_libelles(c) for c in await ctx.tdb.commandes.find(filtre).sort("date", -1).to_list(500)]


@router.get("/{commande_id}")
async def lire(commande_id: str, ctx: Contexte = Depends(ventes)):
    cmd = await ctx.tdb.commandes.find_one({"id": commande_id})
    if not cmd:
        raise HTTPException(404, "Commande introuvable")
    return avec_libelles(cmd)


class ChangementStatut(BaseModel):
    statut: Literal["RECUE", "CONFIRMEE", "PREPARATION", "PRETE", "LIVREE", "ANNULEE"]
    note_interne: str = Field("", max_length=1000)


@router.post("/{commande_id}/statut")
async def changer_statut(commande_id: str, payload: ChangementStatut, ctx: Contexte = Depends(ventes)):
    avant = await ctx.tdb.commandes.find_one({"id": commande_id})
    if not avant:
        raise HTTPException(404, "Commande introuvable")
    maj: dict = {"statut": payload.statut, "date_maj": now_iso()}
    if payload.note_interne:
        maj["note_interne"] = payload.note_interne
    cmd = await ctx.tdb.commandes.find_one_and_update(
        {"id": commande_id},
        {"$set": maj, "$push": {"historique": {"date": now_iso(), "statut": payload.statut, "par": ctx.user.get("nom", "")}}})
    if avant["statut"] != payload.statut and cmd["client"].get("email"):
        cmd_l = avec_libelles(cmd)
        notifier_en_fond(ctx.boutique, "CMD_STATUT", cmd["client"]["email"],
                         {"commande": cmd_l, "client": cmd["client"]}, lien_suivi(ctx.boutique, "commande", cmd))
    return avec_libelles(cmd)


@router.post("/{commande_id}/facture")
async def generer_facture(commande_id: str, ctx: Contexte = Depends(ventes)):
    """Crée la facture (brouillon) de la commande ; un paiement Mobile Money
    déjà reçu y est reporté comme règlement."""
    cmd = await ctx.tdb.commandes.find_one({"id": commande_id})
    if not cmd:
        raise HTTPException(404, "Commande introuvable")
    if cmd.get("facture_id"):
        existante = await ctx.tdb.documents.find_one({"id": cmd["facture_id"]})
        if existante and existante["statut"] != "ANNULE":
            raise HTTPException(409, "Cette commande a déjà une facture")
    client = await ctx.tdb.clients.find_one({"id": cmd["client_id"]}) or {"id": cmd["client_id"], **cmd["client"]}
    lignes = [{"produit_id": l["produit_id"], "designation": l["nom"], "quantite": l["quantite"],
               "prix_unitaire": l["prix_unitaire"]} for l in cmd["lignes"]]
    facture = await creer_document(ctx, "FAC", client, lignes, f"Commande en ligne {cmd['numero']}",
                                   origine={"commande_origine": {"id": cmd["id"], "numero": cmd["numero"]}},
                                   prix_ttc=True)  # le client a payé le prix affiché, TTC
    paiement = cmd.get("paiement") or {}
    if paiement.get("statut") == "PAYEE":
        reglement = {"id": f"mm-{paiement.get('deposit_id')}", "montant": paiement.get("montant_paye", cmd["total"]),
                     "mode": "MM", "date": (paiement.get("date") or now_iso())[:10],
                     "reference": paiement.get("deposit_id", ""), "saisi_par": "PawaPay", "created_at": now_iso()}
        facture = await ctx.tdb.documents.find_one_and_update({"id": facture["id"]}, {"$push": {"reglements": reglement}})
    await ctx.tdb.commandes.update_one({"id": commande_id}, {"$set": {"facture_id": facture["id"]}})
    return enrichir(facture, ctx.boutique)
