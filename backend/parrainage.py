"""Parrainage entre boutiques adLyn.

Principe :
  1. Une boutique (le PARRAIN) partage son lien d'invitation
     « <site>/ouvrir-ma-boutique?parrain=<ID boutique> ».
  2. La personne invitée ACCEPTE l'invitation (case à cocher obligatoire) et
     demande l'ouverture de sa boutique : la boutique FILLEULE est créée EN
     ATTENTE DE VALIDATION (comme par le webhook) et le parrainage est noté
     « EN_ATTENTE ».
  3. Quand l'administrateur VALIDE la boutique filleule (elle est alors ouverte
     au public), le parrainage devient « VALIDE » et le parrain reçoit un bonus
     de PARRAINAGE_BONUS_FCFA (500 F par défaut).
  4. Les bonus s'accumulent dans un solde, déductible de la redevance
     d'abonnement du parrain : paiement en ligne d'un montant réduit, ou
     renouvellement entièrement payé par les bonus.

Le solde est un JOURNAL de mouvements (collection « bonus_mouvements »), jamais
un compteur modifié à la main :
  - GAIN        (+) : parrainage validé ;
  - UTILISATION (-) : bonus déduit d'un abonnement. Pendant un paiement en ligne,
    le montant est RÉSERVÉ (statut EN_ATTENTE) ; il est confirmé (VALIDE) quand
    PawaPay confirme le paiement, et libéré (ANNULE) en cas d'échec.
Solde disponible = gains validés - utilisations validées ou en attente.
"""
from __future__ import annotations

from typing import Optional

from config import get_settings
from db import SANS_ID, db
from utils import new_id, now_iso


def bonus_unitaire() -> int:
    return int(get_settings().parrainage_bonus_fcfa)


# ---------------------------------------------------------------------------
# Solde
# ---------------------------------------------------------------------------
async def solde(boutique_id: str) -> dict:
    """Bonus gagnés, utilisés, réservés et disponibles d'une boutique."""
    gagnes = utilises = reserves = 0
    async for m in db.bonus_mouvements.find({"boutique_id": boutique_id}, SANS_ID):
        if m["type"] == "GAIN" and m["statut"] == "VALIDE":
            gagnes += m["montant"]
        elif m["type"] == "UTILISATION" and m["statut"] == "VALIDE":
            utilises += m["montant"]
        elif m["type"] == "UTILISATION" and m["statut"] == "EN_ATTENTE":
            reserves += m["montant"]
    return {"gagnes": gagnes, "utilises": utilises, "reserves": reserves,
            "disponible": max(gagnes - utilises - reserves, 0)}


async def mouvements(boutique_id: str) -> list[dict]:
    return await db.bonus_mouvements.find(
        {"boutique_id": boutique_id, "statut": {"$ne": "ANNULE"}}, SANS_ID).sort("created_at", -1).to_list(200)


async def deduction_possible(boutique_id: str, prix: int) -> int:
    """Montant de bonus déductible d'un abonnement de ce prix (jamais plus que le prix)."""
    return min((await solde(boutique_id))["disponible"], max(int(prix), 0))


async def reserver(boutique_id: str, montant: int, *, reference: str, libelle: str) -> Optional[dict]:
    """Réserve (EN_ATTENTE) une utilisation de bonus pendant un paiement en ligne.
    Revérifie le solde : refuse (None) si les bonus ont été utilisés entre-temps."""
    if montant <= 0:
        return None
    if (await solde(boutique_id))["disponible"] < montant:
        return None
    mvt = {"id": new_id(), "boutique_id": boutique_id, "type": "UTILISATION", "statut": "EN_ATTENTE",
           "montant": int(montant), "reference": reference, "libelle": libelle, "created_at": now_iso()}
    await db.bonus_mouvements.insert_one(mvt.copy())
    return mvt


async def confirmer(reference: str) -> None:
    """Paiement confirmé : la réservation devient une utilisation définitive."""
    await db.bonus_mouvements.update_many({"reference": reference, "type": "UTILISATION", "statut": "EN_ATTENTE"},
                                          {"$set": {"statut": "VALIDE", "valide_le": now_iso()}})


async def liberer(reference: str) -> None:
    """Paiement échoué ou abandonné : les bonus réservés redeviennent disponibles."""
    await db.bonus_mouvements.update_many({"reference": reference, "type": "UTILISATION", "statut": "EN_ATTENTE"},
                                          {"$set": {"statut": "ANNULE", "annule_le": now_iso()}})


async def liberer_reservations_abandonnees(age_max_heures: int) -> int:
    """Paiements en ligne jamais confirmés (page PawaPay abandonnée) : au-delà de
    `age_max_heures`, les bonus réservés redeviennent disponibles."""
    from datetime import datetime, timedelta, timezone

    limite = (datetime.now(timezone.utc) - timedelta(hours=age_max_heures)).isoformat()
    liberes = 0
    async for m in db.bonus_mouvements.find({"type": "UTILISATION", "statut": "EN_ATTENTE",
                                             "created_at": {"$lt": limite}}, SANS_ID):
        deposit_id = m["reference"].removeprefix("pawapay-")
        paiement = await db.paiements.find_one({"deposit_id": deposit_id}, {"_id": 0, "statut": 1})
        if not paiement or paiement.get("statut") != "paye":
            await liberer(m["reference"])
            liberes += 1
    return liberes


async def utiliser(boutique_id: str, montant: int, *, reference: str, libelle: str) -> Optional[dict]:
    """Utilisation immédiate (renouvellement payé entièrement par les bonus, ou saisie admin)."""
    mvt = await reserver(boutique_id, montant, reference=reference, libelle=libelle)
    if mvt:
        await confirmer(reference)
    return mvt


# ---------------------------------------------------------------------------
# Parrainages
# ---------------------------------------------------------------------------
async def enregistrer_invitation(parrain: dict, filleul: dict, *, ip: str = "") -> dict:
    """Invitation acceptée + demande d'ouverture : parrainage EN_ATTENTE."""
    parrainage = {
        "id": new_id(), "parrain_id": parrain["id"], "parrain_nom": parrain["nom"],
        "parrain_code": parrain.get("code_marchand", ""), "filleul_id": filleul["id"], "filleul_nom": filleul["nom"],
        "filleul_ville": filleul.get("ville", ""), "statut": "EN_ATTENTE", "bonus": bonus_unitaire(),
        "invitation_acceptee_le": now_iso(), "created_at": now_iso(), "ip": ip,
    }
    await db.parrainages.insert_one(parrainage.copy())
    await db.boutiques.update_one({"id": filleul["id"]}, {"$set": {"parrain_id": parrain["id"]}})
    return parrainage


async def valider_filleul(filleul_id: str, par: str = "") -> Optional[dict]:
    """Appelé quand l'administrateur valide (ouvre) une boutique : si elle a été
    parrainée, le parrainage devient VALIDE et le parrain reçoit son bonus.
    Idempotent : un parrainage n'est payé qu'une fois (clé unique du mouvement)."""
    parrainage = await db.parrainages.find_one({"filleul_id": filleul_id, "statut": "EN_ATTENTE"}, SANS_ID)
    if not parrainage:
        return None
    filleul = await db.boutiques.find_one({"id": filleul_id}, SANS_ID) or {}
    parrain = await db.boutiques.find_one({"id": parrainage["parrain_id"]}, SANS_ID)
    # Pas de bonus pour une boutique interne (démo) ni pour un parrain disparu
    if filleul.get("test") or not parrain:
        await db.parrainages.update_one({"id": parrainage["id"]}, {"$set": {
            "statut": "ANNULE", "motif": "Boutique de démonstration" if filleul.get("test") else "Parrain introuvable",
            "annule_le": now_iso()}})
        return None
    res = await db.parrainages.update_one({"id": parrainage["id"], "statut": "EN_ATTENTE"}, {"$set": {
        "statut": "VALIDE", "valide_le": now_iso(), "valide_par": par}})
    if not res.modified_count:
        return None  # déjà traité (validation en double)
    mvt = {"_id": f"gain-{parrainage['id']}", "id": new_id(), "boutique_id": parrain["id"], "type": "GAIN",
           "statut": "VALIDE", "montant": int(parrainage["bonus"]), "reference": parrainage["id"],
           "libelle": f"Parrainage de {parrainage['filleul_nom']}", "created_at": now_iso()}
    await db.bonus_mouvements.insert_one(mvt)
    return {**parrainage, "statut": "VALIDE"}


async def filleuls(parrain_id: str) -> list[dict]:
    docs = await db.parrainages.find({"parrain_id": parrain_id}, SANS_ID).sort("created_at", -1).to_list(500)
    return [{k: d.get(k) for k in ("id", "filleul_nom", "filleul_ville", "statut", "bonus", "invitation_acceptee_le",
                                   "valide_le", "motif")} for d in docs]
