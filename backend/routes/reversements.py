"""Reversements aux boutiques de l'argent encaissé par PawaPay.

Le compte PawaPay est celui de la PLATEFORME : les paiements Mobile Money des
clients d'une boutique y arrivent, puis la plateforme les lui reverse.
  - Le super-administrateur voit, pour chaque boutique : encaissé, déjà
    reversé, reste à reverser ; il enregistre chaque reversement (paiements
    couverts, frais éventuels retenus, mode, référence) et peut l'annuler.
  - Chaque boutique suit UNIQUEMENT ses propres paiements et reversements
    (le filtre boutique_id vient de son compte, jamais du navigateur).
Seuls les paiements de COMMANDES réussis sont concernés (pas les abonnements
ni les factures SMS, qui sont de l'argent dû à la plateforme).
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from abonnements import aujourd_hui
from auth import Contexte, get_super_admin, permission
from db import SANS_ID, db
from utils import new_id, now_iso

boutique = APIRouter(prefix="/reversements", tags=["Reversements (boutique)"])
admin = APIRouter(prefix="/plateforme/reversements", tags=["Reversements (super-admin)"])
historique_dep = permission("paiements.historique")

# Paiements PawaPay réussis d'une commande (les anciens paiements n'ont pas de champ « type »)
ENCAISSES = {"statut": "paye", "type": {"$in": [None, "commande"]}}
MODES = {"MOBILE_MONEY": "Mobile Money", "VIREMENT": "Virement", "ESPECES": "Espèces", "CHEQUE": "Chèque"}
CHAMPS_PAIEMENT = {"_id": 0, "id": 1, "deposit_id": 1, "commande_numero": 1, "client_nom": 1, "montant": 1,
                   "created_at": 1, "updated_at": 1, "reversement_id": 1, "boutique_id": 1}


async def _situation(boutique_id: str) -> dict:
    """Encaissé, reversé (net), frais retenus, reste à reverser pour une boutique."""
    payes = await db.paiements.find({**ENCAISSES, "boutique_id": boutique_id}, {"_id": 0, "montant": 1, "reversement_id": 1}).to_list(None)
    reversements = await db.reversements.find({"boutique_id": boutique_id, "statut": "VALIDE"}, {"_id": 0}).to_list(None)
    en_attente = [p for p in payes if not p.get("reversement_id")]
    return {
        "encaisse": sum(int(p["montant"]) for p in payes),
        "reverse": sum(r["montant_net"] for r in reversements),
        "frais": sum(r["frais"] for r in reversements),
        "a_reverser": sum(int(p["montant"]) for p in en_attente),
        "nb_en_attente": len(en_attente),
        "dernier_reversement": max((r["date"] for r in reversements), default=None),
    }


# ---------------------------------------------------------------------------
# Boutique : SES paiements et SES reversements uniquement
# ---------------------------------------------------------------------------
@boutique.get("")
async def mes_reversements(ctx: Contexte = Depends(historique_dep)):
    bid = ctx.boutique["id"]
    paiements = await db.paiements.find({**ENCAISSES, "boutique_id": bid}, CHAMPS_PAIEMENT).sort("created_at", -1).to_list(2000)
    reversements = await db.reversements.find({"boutique_id": bid}, SANS_ID).sort("created_at", -1).to_list(500)
    numeros = {r["id"]: r["numero"] for r in reversements if r["statut"] == "VALIDE"}
    for p in paiements:
        p["reversement_numero"] = numeros.get(p.get("reversement_id"))
    return {"situation": await _situation(bid), "paiements": paiements, "reversements": reversements, "modes": MODES}


# ---------------------------------------------------------------------------
# Super-administrateur
# ---------------------------------------------------------------------------
@admin.get("/boutiques")
async def boutiques(_: dict = Depends(get_super_admin)):
    lignes = []
    async for b in db.boutiques.find({}, {"_id": 0, "id": 1, "nom": 1, "code_marchand": 1}).sort("nom", 1):
        lignes.append({**b, **await _situation(b["id"])})
    total = {k: sum(x[k] for x in lignes) for k in ("encaisse", "reverse", "frais", "a_reverser")}
    return {"boutiques": lignes, "total": total, "modes": MODES}


@admin.get("/boutiques/{boutique_id}/a-reverser")
async def a_reverser(boutique_id: str, _: dict = Depends(get_super_admin)):
    """Paiements encaissés pas encore reversés (proposés pour le prochain reversement)."""
    return await db.paiements.find({**ENCAISSES, "boutique_id": boutique_id, "reversement_id": None},
                                   CHAMPS_PAIEMENT).sort("created_at", 1).to_list(2000)


class NouveauReversement(BaseModel):
    boutique_id: str
    paiement_ids: list[str] = Field(..., min_length=1, max_length=2000)
    frais: int = Field(0, ge=0)  # frais retenus (ex. frais PawaPay, commission)
    mode: Literal["MOBILE_MONEY", "VIREMENT", "ESPECES", "CHEQUE"] = "MOBILE_MONEY"
    reference: str = Field("", max_length=120)
    date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str = Field("", max_length=500)


@admin.post("", status_code=201)
async def creer(payload: NouveauReversement, adm: dict = Depends(get_super_admin)):
    b = await db.boutiques.find_one({"id": payload.boutique_id}, SANS_ID)
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    ids = list(dict.fromkeys(payload.paiement_ids))
    reversement_id = new_id()
    # Réservation ATOMIQUE des paiements : un paiement ne peut être reversé qu'une fois
    res = await db.paiements.update_many(
        {**ENCAISSES, "boutique_id": b["id"], "id": {"$in": ids}, "reversement_id": None},
        {"$set": {"reversement_id": reversement_id}})
    if res.modified_count != len(ids):
        await db.paiements.update_many({"reversement_id": reversement_id}, {"$set": {"reversement_id": None}})
        raise HTTPException(409, "Certains paiements sont introuvables ou déjà reversés : rechargez la liste")
    payes = await db.paiements.find({"reversement_id": reversement_id}, CHAMPS_PAIEMENT).to_list(None)
    brut = sum(int(p["montant"]) for p in payes)
    if payload.frais > brut:
        await db.paiements.update_many({"reversement_id": reversement_id}, {"$set": {"reversement_id": None}})
        raise HTTPException(400, "Les frais dépassent le montant reversé")
    jour = payload.date or aujourd_hui().isoformat()
    reversement = {
        "id": reversement_id, "numero": f"REV-{jour[:7]}-{b.get('code_marchand', '')}-{new_id()[:4].upper()}",
        "boutique_id": b["id"], "boutique_nom": b["nom"], "code_marchand": b.get("code_marchand", ""),
        "paiement_ids": [p["id"] for p in payes], "nb_paiements": len(payes), "montant_brut": brut,
        "frais": payload.frais, "montant_net": brut - payload.frais, "mode": payload.mode,
        "reference": payload.reference.strip(), "note": payload.note.strip(), "date": jour,
        "statut": "VALIDE", "cree_par": adm.get("email", ""), "created_at": now_iso(),
    }
    await db.reversements.insert_one(reversement.copy())
    return reversement


@admin.get("")
async def lister(boutique_id: str = "", _: dict = Depends(get_super_admin)):
    filtre = {"boutique_id": boutique_id} if boutique_id else {}
    return await db.reversements.find(filtre, SANS_ID).sort("created_at", -1).to_list(1000)


@admin.post("/{reversement_id}/annuler")
async def annuler(reversement_id: str, adm: dict = Depends(get_super_admin)):
    """Annule un reversement saisi par erreur : ses paiements redeviennent « à reverser »."""
    r = await db.reversements.find_one_and_update(
        {"id": reversement_id, "statut": "VALIDE"},
        {"$set": {"statut": "ANNULE", "annule_le": now_iso(), "annule_par": adm.get("email", "")}})
    if not r:
        raise HTTPException(404, "Reversement introuvable ou déjà annulé")
    await db.paiements.update_many({"reversement_id": reversement_id}, {"$set": {"reversement_id": None}})
    return {"ok": True}
