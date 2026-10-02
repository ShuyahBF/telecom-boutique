"""Connexion du personnel (DG, commerciaux, secrétaires, comptables, techniciens, super-admin).

Identifiants du personnel d'une boutique : ID BOUTIQUE (code de 6 caractères,
ex. « K7M2QD ») + e-mail OU numéro de téléphone + mot de passe personnel. L'ID boutique évite toute
confusion entre boutiques (et une faute de frappe sur un nom de boutique).
Le super-administrateur se connecte sans ID boutique (avec son e-mail).
Mot de passe oublié et changement d'identifiant : voir routes/identifiants.py.

Après la connexion, la session est gardée 30 jours dans un cookie HttpOnly
(le site se reconnecte tout seul à son ouverture). Le mot de passe n'est
jamais stocké dans le navigateur.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

import acces
import maintenance_plateforme
from pydantic import BaseModel, Field

from auth import (create_access_token, effacer_cookie_session, get_current_user, hash_password,
                  poser_cookie_session, user_public, verify_password)
from db import SANS_ID, db
from identifiants import lire_identifiant
from utils import now_iso

router = APIRouter(prefix="/auth", tags=["Authentification"])

# Anti force brute : au-delà de 10 échecs en 15 minutes pour un même compte, pause
MAX_ECHECS, FENETRE_ECHECS = 10, timedelta(minutes=15)


class Connexion(BaseModel):
    # ID boutique (code marchand de 6 caractères) ; vide pour le super-administrateur
    code_boutique: Optional[str] = Field(None, max_length=20)
    # E-mail OU numéro de téléphone (un seul champ sur la page de connexion)
    identifiant: Optional[str] = Field(None, max_length=200)
    # Ancien nom du champ (outils et anciennes versions du site) : toujours accepté
    email: Optional[str] = Field(None, max_length=200)
    password: str = Field(..., max_length=200)


async def _reponse_session(user: dict) -> dict:
    """Jeton + fiche utilisateur + boutique rattachée (si ce n'est pas le super-admin)."""
    boutique = None
    if user.get("boutique_id"):
        boutique = await db.boutiques.find_one({"id": user["boutique_id"]}, SANS_ID)
    return {
        "access_token": create_access_token(user["id"], int(user.get("version_session", 0))),
        "user": user_public(user),
        "boutique": _sans_secrets(boutique),
    }


def _sans_secrets(boutique: dict | None, super_admin: bool = False) -> dict | None:
    """Ne jamais renvoyer le mot de passe SMTP ni les clés des pièces KYC au navigateur.
    Le drapeau interne « test » (boutique de démonstration) n'est renvoyé qu'aux écrans
    du super-administrateur (super_admin=True) : le personnel de la boutique ne le voit pas."""
    if not boutique:
        return None
    from kyc import kyc_public

    b = dict(boutique)
    if not super_admin:
        b.pop("test", None)
    b["kyc"] = kyc_public(b.get("kyc"))
    # État réel des options de la barre latérale (menu affiché par le site)
    import options_sidebar
    b["options_actives"] = options_sidebar.options_effectives(boutique)
    if b.get("messagerie"):
        m = dict(b["messagerie"])
        m["a_mot_de_passe"] = bool(m.pop("smtp_mot_de_passe", None))
        b["messagerie"] = m
    return b


@router.post("/login")
async def login(payload: Connexion, request: Request, response: Response):
    saisie = (payload.identifiant or payload.email or "").strip()
    type_identifiant, valeur = lire_identifiant(saisie)
    # Identifiant tel que noté dans le journal (même s'il est mal tapé)
    email = valeur or saisie.lower()[:200]
    code = re.sub(r"[^A-Za-z0-9]", "", payload.code_boutique or "").upper()
    cle_echecs = f"{code}|{email}"
    if code:  # personnel d'une boutique : pas de connexion pendant la maintenance de la plateforme
        await maintenance_plateforme.refuser_si_maintenance()
    depuis = (datetime.now(timezone.utc) - FENETRE_ECHECS).isoformat()
    if await db.echecs_connexion.count_documents({"cle": cle_echecs, "date": {"$gte": depuis}}) >= MAX_ECHECS:
        raise HTTPException(429, "Trop de tentatives. Réessayez dans 15 minutes.")

    # Boutique désignée par l'ID tapé (sert aussi à tracer les tentatives dans SON journal)
    boutique = await db.boutiques.find_one({"code_marchand": code}, SANS_ID) if code else None
    user = await db.users.find_one({type_identifiant: valeur}, SANS_ID) if valeur else None
    erreur = None
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        erreur = "Identifiants incorrects"
    elif user.get("role") != "super_admin":
        # Personnel d'une boutique : l'ID boutique doit être celui de SA boutique
        if not code:
            erreur = "Indiquez l'ID de votre boutique (6 caractères)"
        elif not boutique or boutique["id"] != user.get("boutique_id"):
            erreur = "Identifiants incorrects"
    if erreur:
        # Même message quel que soit le champ erroné : on ne révèle rien (compte, boutique)
        await db.echecs_connexion.insert_one({"cle": cle_echecs, "date": now_iso(),
                                              "expire_le": datetime.now(timezone.utc) + FENETRE_ECHECS})
        if boutique:
            await acces.journaliser(boutique["id"], request, "ECHEC", email=email, raison=erreur)
        raise HTTPException(401, erreur)
    if not user.get("actif", True):
        raise HTTPException(403, "Ce compte est désactivé")

    if user.get("role") != "super_admin":
        await maintenance_plateforme.refuser_si_maintenance()
        # Adresse IP / appareil : règles d'accès de la boutique (listes blanche et noire)
        appareil = acces.poser_cookie_appareil(request, response)
        autorise, raison = acces.verdict(acces.regles(boutique), acces.ip_client(request), appareil)
        await acces.journaliser(boutique["id"], request, "SUCCES" if autorise else "BLOQUE", user=user,
                                raison=raison, appareil=appareil)
        if not autorise:
            refus = JSONResponse({"detail": f"Connexion refusée : {raison.lower()}. Contactez le DG de votre boutique."},
                                 status_code=403)
            for cookie in response.headers.getlist("set-cookie"):  # garde l'identifiant de l'appareil
                refus.headers.append("set-cookie", cookie)
            return refus
    await db.echecs_connexion.delete_many({"cle": cle_echecs})
    session = await _reponse_session(user)
    poser_cookie_session(response, session["access_token"])
    return session


@router.post("/logout")
async def logout(response: Response):
    """Déconnexion : le navigateur oublie le cookie de session."""
    effacer_cookie_session(response)
    return {"ok": True}


@router.get("/me")
async def me(request: Request, user: dict = Depends(get_current_user)):
    session = await _reponse_session(user)
    # Appareil ou adresse interdits depuis l'ouverture de la session : on n'ouvre pas le site
    if session["boutique"] and user.get("role") != "super_admin":
        b = await db.boutiques.find_one({"id": user["boutique_id"]}, {"_id": 0, "acces": 1})
        autorise, raison = acces.controler(b or {}, request)
        if not autorise:
            raise HTTPException(403, f"Accès refusé : {raison.lower()}")
    session.pop("access_token")
    return session


class ChangementMotDePasse(BaseModel):
    ancien: str
    nouveau: str = Field(..., min_length=8)


@router.post("/mot-de-passe")
async def changer_mot_de_passe(payload: ChangementMotDePasse, response: Response,
                               user: dict = Depends(get_current_user)):
    complet = await db.users.find_one({"id": user["id"]}, SANS_ID)
    if not verify_password(payload.ancien, complet["password_hash"]):
        raise HTTPException(400, "Ancien mot de passe incorrect")
    if payload.ancien == payload.nouveau:
        raise HTTPException(400, "Choisissez un mot de passe différent de l'actuel")
    # Nouvelle version de session : les autres appareils connectés sont déconnectés
    version = int(complet.get("version_session", 0)) + 1
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "password_hash": hash_password(payload.nouveau), "doit_changer_mot_de_passe": False,
        "version_session": version}})
    # ... mais pas cet appareil : on lui redonne une session valide
    jeton = create_access_token(user["id"], version)
    poser_cookie_session(response, jeton)
    return {"ok": True, "access_token": jeton}
