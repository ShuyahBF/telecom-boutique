"""Validation (ouverture au public) d'une boutique en attente — logique PARTAGÉE.

Utilisée par :
  - la validation manuelle du super-administrateur (POST /plateforme/boutiques/{id}/valider) ;
  - la validation automatique après lecture de la pièce d'identité par l'IA
    (lot C, kyc_ia.py, par = « IA (Liluvine) »).

Effets : validee = True, validee_le, validee_par, puis le parrainage éventuel est
validé (bonus au parrain, idempotent). Une boutique déjà validée n'est pas modifiée
(sa date et son auteur de validation d'origine sont conservés).
"""
from __future__ import annotations

from typing import Optional

from db import SANS_ID, db
from utils import now_iso


async def valider_boutique(boutique_id: str, par: str) -> Optional[dict]:
    """Valide la boutique et renvoie sa fiche à jour ; None si elle n'existe pas.
    `par` : e-mail de l'administrateur, ou « IA (Liluvine) » pour la validation automatique."""
    boutique = await db.boutiques.find_one({"id": boutique_id}, {"_id": 0, "id": 1, "validee": 1})
    if not boutique:
        return None
    if boutique.get("validee") is not True:
        # Condition « pas encore validée » dans le filtre : deux validations simultanées
        # (super-admin + IA) n'écrasent pas la première date / le premier auteur
        await db.boutiques.update_one({"id": boutique_id, "validee": {"$ne": True}}, {"$set": {
            "validee": True, "validee_le": now_iso(), "validee_par": par or ""}})
    # Boutique parrainée : son ouverture valide le parrainage (bonus au parrain, une seule fois)
    import parrainage
    await parrainage.valider_filleul(boutique_id, par=par or "")
    return await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
