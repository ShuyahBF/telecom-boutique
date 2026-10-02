"""Période de grâce des abonnements (super-administrateur) — logique : abonnement_grace.py.

  - GET  /plateforme/abonnements/boutiques/{id}/grace             : situation + journal
  - PUT  /plateforme/abonnements/boutiques/{id}/grace             : délai propre à la boutique (0 à 30 j, null = 3 j)
  - POST /plateforme/abonnements/boutiques/{id}/grace/renouveler  : « Renouveler la grâce (+3 j) », 3 fois au plus
Chaque modification est journalisée (collection abonnement_grace_journal).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import abonnement_grace as service
from auth import get_super_admin
from db import SANS_ID, db
from utils import new_id, now_iso

admin = APIRouter(prefix="/plateforme/abonnements", tags=["Abonnements (super-admin)"])


class DelaiGrace(BaseModel):
    jours: Optional[int] = None  # None = délai par défaut (3 jours)


async def _boutique(boutique_id: str) -> dict:
    b = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    return b


async def _journaliser(boutique: dict, action: str, adm: dict, **details) -> None:
    await db.abonnement_grace_journal.insert_one({
        "id": new_id(), "date": now_iso(), "action": action, "boutique_id": boutique["id"],
        "boutique_nom": boutique.get("nom", ""), "par": adm.get("email", ""), **details})


async def _reponse(boutique_id: str) -> dict:
    b = await _boutique(boutique_id)
    journal = await db.abonnement_grace_journal.find({"boutique_id": boutique_id}, SANS_ID) \
        .sort("date", -1).to_list(30)
    return {**service.resume(b), "grace_jours_boutique": b.get("grace_jours"), "defaut": service.GRACE_DEFAUT,
            "max": service.GRACE_MAX, "journal": journal}


@admin.get("/boutiques/{boutique_id}/grace")
async def lire(boutique_id: str, _: dict = Depends(get_super_admin)):
    return await _reponse(boutique_id)


@admin.put("/boutiques/{boutique_id}/grace")
async def regler(boutique_id: str, payload: DelaiGrace, adm: dict = Depends(get_super_admin)):
    b = await _boutique(boutique_id)
    jours = service.valider_jours(payload.jours)
    await db.boutiques.update_one({"id": b["id"]}, {"$set": {"grace_jours": jours}})
    await _journaliser(b, "DELAI_MODIFIE", adm, avant=b.get("grace_jours"), apres=jours)
    return await _reponse(boutique_id)


@admin.post("/boutiques/{boutique_id}/grace/renouveler")
async def renouveler(boutique_id: str, adm: dict = Depends(get_super_admin)):
    """+3 jours de grâce, au plus 3 fois pour la même échéance impayée."""
    b = await _boutique(boutique_id)
    etat = service.resume(b)
    if not etat["expire"]:
        raise HTTPException(400, "L'abonnement de cette boutique n'est pas expiré")
    echeance = service._echeance(b)  # noqa: SLF001
    nb = service.prolongations(b, echeance)
    if nb >= service.PROLONGATIONS_MAX:
        raise HTTPException(400, f"La grâce a déjà été renouvelée {service.PROLONGATIONS_MAX} fois pour cette échéance")
    # Mise à jour conditionnelle : deux clics simultanés ne comptent qu'une fois
    res = await db.boutiques.update_one(
        {"id": b["id"], "grace_prolongations": b.get("grace_prolongations")},
        {"$set": {"grace_prolongations": {"echeance": echeance, "nb": nb + 1, "date": now_iso(),
                                          "par": adm.get("email", "")}}})
    if not res.modified_count:
        raise HTTPException(409, "La grâce vient d'être modifiée : rechargez la page")
    await _journaliser(b, "GRACE_RENOUVELEE", adm, echeance=echeance, numero=nb + 1,
                       jours=service.PROLONGATION_JOURS)
    return await _reponse(boutique_id)
