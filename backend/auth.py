"""Authentification du personnel et résolution de la boutique (tenant).

Rôles :
  - super_admin : administrateur de la PLATEFORME (vous) ; crée les boutiques.
  - gerant      : administrateur d'UNE boutique (paramètres, équipe, tout).
  - vendeur     : ventes, stock, clients, commandes, messagerie.
  - technicien  : maintenance (SAV), consultation du catalogue.

RÈGLE MULTI-TENANT : la boutique d'un membre du personnel est lue dans SA
fiche en base (résolue côté serveur depuis le jeton), jamais depuis un
paramètre envoyé par le navigateur. Seul le super-administrateur peut
choisir la boutique sur laquelle il agit (en-tête X-Boutique-Id).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from config import get_settings
from db import SANS_ID, TenantDB, db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

ROLES_BOUTIQUE = ("gerant", "vendeur", "technicien")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: str) -> str:
    s = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_expires_minutes)
    return jwt.encode({"sub": user_id, "exp": expires_at}, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> Optional[str]:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")


def user_public(user: dict) -> dict:
    """Fiche utilisateur renvoyée au navigateur (jamais le hachage du mot de passe)."""
    return {k: v for k, v in user.items() if k not in ("password_hash", "_id")}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non authentifié")
    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalide ou expirée")
    user = await db.users.find_one({"id": user_id}, SANS_ID)
    if not user or not user.get("actif", True):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable ou désactivé")
    return user


async def get_super_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'administrateur de la plateforme")
    return user


class Contexte:
    """Ce dont une route métier a besoin : l'utilisateur, SA boutique et
    l'accès cloisonné aux données de cette boutique (tdb)."""

    def __init__(self, user: dict, boutique: dict):
        self.user = user
        self.boutique = boutique
        self.tdb = TenantDB(boutique["id"])

    @property
    def role(self) -> str:
        return self.user.get("role", "")

    @property
    def auteur(self) -> dict:
        """Signature enregistrée sur les opérations (mouvements, documents...)."""
        return {"user_id": self.user["id"], "user_nom": self.user.get("nom", "")}


async def get_contexte(
    user: dict = Depends(get_current_user),
    x_boutique_id: Optional[str] = Header(default=None),
) -> Contexte:
    if user.get("role") == "super_admin":
        # Le super-administrateur choisit explicitement la boutique à consulter
        if not x_boutique_id:
            raise HTTPException(400, "Choisissez une boutique (en-tête X-Boutique-Id)")
        boutique_id = x_boutique_id
    else:
        boutique_id = user.get("boutique_id")
    boutique = await db.boutiques.find_one({"id": boutique_id}, SANS_ID) if boutique_id else None
    if not boutique:
        raise HTTPException(403, "Aucune boutique associée à ce compte")
    if not boutique.get("actif", True) and user.get("role") != "super_admin":
        raise HTTPException(403, "Cette boutique est suspendue. Contactez l'administrateur de la plateforme.")
    return Contexte(user, boutique)


def exiger_roles(*roles: str):
    """Dépendance : limite une route à certains rôles (le super-admin passe toujours)."""

    async def _verif(ctx: Contexte = Depends(get_contexte)) -> Contexte:
        if ctx.role != "super_admin" and ctx.role not in roles:
            raise HTTPException(403, "Action non autorisée pour votre rôle")
        return ctx

    return _verif


# Raccourcis lisibles pour les routes
tout_le_personnel = exiger_roles("gerant", "vendeur", "technicien")
ventes = exiger_roles("gerant", "vendeur")
atelier = exiger_roles("gerant", "vendeur", "technicien")
gerant = exiger_roles("gerant")
