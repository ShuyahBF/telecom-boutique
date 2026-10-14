"""Lot 52 — GET /api/sawali/contacts : le personnel des boutiques, lu (signé) par SAWALI. Voir export_contacts_sawali.py."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

import export_contacts_sawali as E
from db import db

router = APIRouter(prefix="/sawali", tags=["SAWALI"])


@router.get("/contacts")
async def contacts(request: Request, limite: int = E.LIMITE_DEFAUT, page: int = 1):
    """Une page de contacts pour SAWALI. 503 si la clé n'est pas saisie, 401 si la signature est absente, périmée ou fausse."""
    cle = E.cle_partagee()
    if not cle:
        raise HTTPException(status_code=503, detail="Export des contacts désactivé : saisir SAWALI_CONTACTS_HMAC sur le serveur")
    en = request.headers
    if not E.signature_valide(cle, en.get("X-Timestamp", ""), en.get("X-Signature", ""), request.url.path, request.url.query):
        raise HTTPException(status_code=401, detail="Signature invalide ou périmée")
    return await E.page_de_contacts(db, page, limite)
