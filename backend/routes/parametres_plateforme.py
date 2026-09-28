"""Paramètres de la plateforme réglables par le super-administrateur (sans redéployer) :
serveur d'envoi des e-mails de la plateforme (SMTP)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

import envois_plateforme as envois
from auth import get_super_admin
from db import db
from utils import now_iso

router = APIRouter(prefix="/plateforme/parametres", tags=["Paramètres de la plateforme"])


@router.get("/smtp")
async def lire_smtp(_: dict = Depends(get_super_admin)):
    """Réglages en vigueur, SANS le mot de passe (seulement s'il est renseigné)."""
    c = await envois.config_smtp()
    return {**{k: c[k] for k in ("hote", "port", "utilisateur", "expediteur", "nom_expediteur", "ssl", "actif", "source")},
            "a_mot_de_passe": bool(c["mot_de_passe"])}


class ReglagesSmtp(BaseModel):
    hote: str = Field(..., min_length=3, max_length=120)  # ex. mail.sawalismartsystems.com
    port: int = Field(587, ge=1, le=65535)  # 587 (STARTTLS) ou 465 (SSL)
    ssl: bool = False  # True pour le port 465
    utilisateur: str = Field("", max_length=160)  # souvent l'adresse elle-même
    mot_de_passe: Optional[str] = Field(None, max_length=200)  # vide = inchangé
    expediteur: EmailStr  # adresse d'envoi, ex. messenger@sawalismartsystems.com
    nom_expediteur: str = Field("adLyn", max_length=60)  # nom affiché chez le destinataire
    actif: bool = True


@router.put("/smtp")
async def enregistrer_smtp(payload: ReglagesSmtp, adm: dict = Depends(get_super_admin)):
    actuel = await db.parametres_plateforme.find_one({"_id": "smtp"}) or {}
    doc = {**payload.model_dump(exclude={"mot_de_passe"}), "expediteur": str(payload.expediteur),
           "modifie_le": now_iso(), "modifie_par": adm.get("email", "")}
    # Mot de passe chiffré en base ; un champ laissé vide garde l'ancien
    doc["mot_de_passe_chiffre"] = envois.chiffrer(payload.mot_de_passe) if payload.mot_de_passe \
        else actuel.get("mot_de_passe_chiffre", "")
    await db.parametres_plateforme.update_one({"_id": "smtp"}, {"$set": doc}, upsert=True)
    return await lire_smtp(adm)


class Essai(BaseModel):
    destinataire: EmailStr


@router.post("/smtp/essai")
async def essai_smtp(payload: Essai, _: dict = Depends(get_super_admin)):
    statut, erreur = await envois.envoyer_email(
        "[adLyn] E-mail d'essai", "Bonjour,\n\nCet e-mail confirme que le serveur d'envoi de la plateforme adLyn "
        "fonctionne.\n\nL'équipe adLyn", str(payload.destinataire))
    if statut != "ENVOYE":
        raise HTTPException(400, f"Envoi impossible : {erreur}")
    return {"ok": True}
