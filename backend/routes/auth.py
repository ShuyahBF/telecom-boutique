"""Connexion du personnel (gérants, vendeurs, techniciens, super-admin)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from auth import create_access_token, get_current_user, hash_password, user_public, verify_password
from db import SANS_ID, db

router = APIRouter(prefix="/auth", tags=["Authentification"])


class Connexion(BaseModel):
    email: EmailStr
    password: str


async def _reponse_session(user: dict) -> dict:
    """Jeton + fiche utilisateur + boutique rattachée (si ce n'est pas le super-admin)."""
    boutique = None
    if user.get("boutique_id"):
        boutique = await db.boutiques.find_one({"id": user["boutique_id"]}, SANS_ID)
    return {
        "access_token": create_access_token(user["id"]),
        "user": user_public(user),
        "boutique": _sans_secrets(boutique),
    }


def _sans_secrets(boutique: dict | None) -> dict | None:
    """Ne jamais renvoyer le mot de passe SMTP ni les clés des pièces KYC au navigateur."""
    if not boutique:
        return None
    from kyc import kyc_public

    b = dict(boutique)
    b["kyc"] = kyc_public(b.get("kyc"))
    if b.get("messagerie"):
        m = dict(b["messagerie"])
        m["a_mot_de_passe"] = bool(m.pop("smtp_mot_de_passe", None))
        b["messagerie"] = m
    return b


@router.post("/login")
async def login(payload: Connexion):
    user = await db.users.find_one({"email": payload.email.lower()}, SANS_ID)
    # Même message dans les deux cas : on ne révèle pas si l'e-mail existe
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(401, "E-mail ou mot de passe incorrect")
    if not user.get("actif", True):
        raise HTTPException(403, "Ce compte est désactivé")
    return await _reponse_session(user)


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    session = await _reponse_session(user)
    session.pop("access_token")
    return session


class ChangementMotDePasse(BaseModel):
    ancien: str
    nouveau: str = Field(..., min_length=8)


@router.post("/mot-de-passe")
async def changer_mot_de_passe(payload: ChangementMotDePasse, user: dict = Depends(get_current_user)):
    complet = await db.users.find_one({"id": user["id"]}, SANS_ID)
    if not verify_password(payload.ancien, complet["password_hash"]):
        raise HTTPException(400, "Ancien mot de passe incorrect")
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(payload.nouveau)}})
    return {"ok": True}
