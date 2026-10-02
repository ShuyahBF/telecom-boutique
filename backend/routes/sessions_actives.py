"""Sessions ouvertes de chaque compte (logique : sessions_actives.py).

  - chacun      : GET /auth/sessions (ses sessions ouvertes, celle-ci marquée « courante »),
                  POST /auth/sessions/{id}/fermer (fermer une autre session) ;
  - super-admin : GET/PUT /plateforme/parametres/sessions (nombre maximal par compte, 1 à 20),
                  GET /plateforme/boutiques/{id}/sessions (sessions de chaque compte de la boutique),
                  POST /plateforme/boutiques/{id}/sessions/{session_id}/fermer.
Chaque fermeture est notée dans le journal des identifiants.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

import identifiants
import inactivite
import sessions_actives as service
from auth import bearer_scheme, decode_access_token, get_current_user, get_super_admin
from config import get_settings
from db import SANS_ID, db

compte = APIRouter(prefix="/auth", tags=["Authentification"])
admin = APIRouter(prefix="/plateforme", tags=["Plateforme (super-admin)"])


class Limite(BaseModel):
    valeur: Optional[int] = None


def _sid_courant(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> str:
    jeton = credentials.credentials if credentials else request.cookies.get(get_settings().session_cookie_nom)
    contenu = decode_access_token(jeton) if jeton else None
    return inactivite.id_session(contenu) if contenu else ""


# ---------------------------------------------------------------------------
# Tout utilisateur connecté : ses propres sessions
# ---------------------------------------------------------------------------
@compte.get("/sessions")
async def mes_sessions(request: Request, user: dict = Depends(get_current_user),
                       credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)):
    return {"sessions": await service.lister(user, _sid_courant(request, credentials)),
            "limite": await service.limite()}


@compte.post("/sessions/{session_id}/fermer")
async def fermer_ma_session(session_id: str, request: Request, user: dict = Depends(get_current_user),
                            credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)):
    if session_id == service.id_public(_sid_courant(request, credentials)):
        raise HTTPException(400, "C'est la session de cet appareil : utilisez « Déconnexion »")
    doc = await service.fermer(user["id"], session_id, "UTILISATEUR")
    if not doc:
        raise HTTPException(404, "Session introuvable ou déjà fermée")
    await identifiants.journaliser("SESSION_FERMEE", cible=user, par=user, request=request,
                                   details={"appareil": doc.get("appareil", ""), "ip_session": doc.get("ip", "")})
    return {"ok": True, "message": f"Session fermée ({doc.get('appareil') or 'appareil inconnu'})."}


# ---------------------------------------------------------------------------
# Super-administrateur
# ---------------------------------------------------------------------------
@admin.get("/parametres/sessions")
async def lire_limite(_: dict = Depends(get_super_admin)):
    return {"valeur": await service.limite(cache=False), "min": service.LIMITE_MIN, "max": service.LIMITE_MAX}


@admin.put("/parametres/sessions")
async def regler_limite(payload: Limite, adm: dict = Depends(get_super_admin)):
    valeur = await service.regler_limite(payload.valeur, adm.get("email", ""))
    return {"valeur": valeur, "min": service.LIMITE_MIN, "max": service.LIMITE_MAX}


async def _boutique(boutique_id: str) -> dict:
    b = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    return b


@admin.get("/boutiques/{boutique_id}/sessions")
async def sessions_boutique(boutique_id: str, _: dict = Depends(get_super_admin)):
    """Sessions ouvertes de chaque compte de la boutique : {user_id: {nb, sessions}}."""
    await _boutique(boutique_id)
    comptes = await db.users.find({"boutique_id": boutique_id}, SANS_ID).to_list(500)
    resultat = {}
    for c in comptes:
        liste = await service.lister(c)
        resultat[c["id"]] = {"nb": len(liste), "sessions": liste}
    return {"comptes": resultat, "limite": await service.limite()}


@admin.post("/boutiques/{boutique_id}/sessions/{session_id}/fermer")
async def fermer_session_compte(boutique_id: str, session_id: str, request: Request,
                                administrateur: dict = Depends(get_super_admin)):
    b = await _boutique(boutique_id)
    doc = await db.sessions_activite.find_one({"id_public": session_id, "fermee": {"$ne": True}})
    membre = await db.users.find_one({"id": (doc or {}).get("user_id"), "boutique_id": b["id"]}, SANS_ID) if doc else None
    if not doc or not membre or membre.get("role") == "super_admin":
        raise HTTPException(404, "Session introuvable dans cette boutique")
    await service.fermer(membre["id"], session_id, "ADMIN")
    await identifiants.journaliser("SESSION_FERMEE_ADMIN", cible=membre, par=administrateur, request=request,
                                   details={"appareil": doc.get("appareil", ""), "ip_session": doc.get("ip", "")})
    return {"ok": True, "message": f"Session de {membre.get('nom', 'ce compte')} fermée ({doc.get('appareil') or 'appareil inconnu'})."}
