"""Routes d'administration de la « Transmission WA » (réservées au super-administrateur) :
  - GET  /api/admin/transmission-wa/etat : canaux configurés (jamais de secret) ;
  - POST /api/admin/transmission-wa/test : envoie un message de test au numéro donné,
    en appliquant l'ordre de priorité boutique -> plateforme -> Liluvine."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import transmission_wa as service
from auth import get_super_admin
from db import SANS_ID, db

router = APIRouter(prefix="/admin/transmission-wa", tags=["Transmission WA (super-admin)"],
                   dependencies=[Depends(get_super_admin)])

MESSAGE_TEST = "Test de transmission WhatsApp depuis adLyn"


class TestIn(BaseModel):
    numero: str = Field(..., min_length=8, max_length=30)  # numéro international, ex. +22670000000
    boutique_id: Optional[str] = Field(None, max_length=64)  # facultatif : teste le canal de cette boutique


# ---- État des canaux (booléens seulement : aucune clé n'est renvoyée) ----
@router.get("/etat")
async def etat():
    return service.etat()


# ---- Envoi d'un message de test ----
@router.post("/test")
async def tester(data: TestIn):
    boutique = None
    if data.boutique_id:
        boutique = await db.boutiques.find_one({"id": data.boutique_id}, SANS_ID)
        if not boutique:
            raise HTTPException(404, "Boutique introuvable")
    resultat = await service.envoyer_whatsapp(data.numero, MESSAGE_TEST, boutique=boutique, modele="")
    # Résultat sans secret : canal utilisé, identifiant du message, erreur éventuelle
    return {k: resultat.get(k) for k in ("ok", "canal", "message_id", "erreur")}
