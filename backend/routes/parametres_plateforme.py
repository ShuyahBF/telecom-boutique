"""Paramètres de la plateforme réglables par le super-administrateur (sans redéployer) :
service d'envoi des e-mails de la plateforme (Resend, ZeptoMail, Brevo ou SMTP).

Routes :
  - GET/PUT /plateforme/parametres/email, POST /email/essai, GET /email/journal ;
  - GET/PUT /plateforme/parametres/smtp et POST /smtp/essai : anciennes routes,
    gardées compatibles (le PUT /smtp choisit le service « smtp »).
Aucune clé API ni mot de passe n'est jamais renvoyé : seulement a_cle / a_mot_de_passe."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, model_validator

import envois_plateforme as envois
from auth import get_super_admin
from db import SANS_ID, db
from utils import now_iso

router = APIRouter(prefix="/plateforme/parametres", tags=["Paramètres de la plateforme"])


# ---------------------------------------------------------------------------
# Lecture des réglages (sans aucun secret)
# ---------------------------------------------------------------------------
async def _etat_email() -> dict:
    """Réglages affichés dans l'écran : choix enregistré, service réellement utilisé, présence des secrets."""
    doc = await envois.lire_reglages_email()
    c = await envois.config_email()
    choix = envois.fournisseur_choisi(doc)
    cles = doc.get("cles_chiffrees") or {}
    # Présence d'une clé par fournisseur (écran ou variable de repli), jamais sa valeur
    a_cles = {f: bool(envois.dechiffrer(cles.get(f, ""))) for f in envois.FOURNISSEURS_API}
    cles_env = {f: bool(envois.cle_env(f)) for f in envois.FOURNISSEURS_API}
    smtp = envois._smtp_doc(doc) if doc.get("hote") else envois._smtp_env()
    pret, raison = envois.config_prete(c)
    return {
        # Choix de l'écran ("" = rien de réglé : variables de repli)
        "fournisseur": choix or "",
        # Service qui part réellement (écran ou variables d'environnement)
        "fournisseur_effectif": c.get("fournisseur") or "", "source": c.get("source") or "",
        "pret": pret, "raison": raison,
        "actif": bool(doc.get("actif", True)) if choix else bool(c.get("actif")),
        "expediteur": doc.get("expediteur") or (c.get("expediteur") if not choix else "") or "",
        "nom_expediteur": doc.get("nom_expediteur") or "adLyn",
        "zeptomail_hote": envois.hote_zeptomail(doc.get("zeptomail_hote")),
        "a_cle": a_cles.get(choix, False), "cles": a_cles, "cles_env": cles_env,
        "smtp": {"hote": smtp["hote"], "port": smtp["port"], "ssl": smtp["ssl"], "utilisateur": smtp["utilisateur"],
                 "a_mot_de_passe": bool(smtp["mot_de_passe"])},
    }


@router.get("/email")
async def lire_email(_: dict = Depends(get_super_admin)):
    return await _etat_email()


@router.get("/smtp")
async def lire_smtp(_: dict = Depends(get_super_admin)):
    """Ancienne route : réglages SMTP SANS le mot de passe, et état de Resend (jamais la clé)."""
    c = await envois.config_smtp()
    eff = await envois.config_email()
    return {**{k: c[k] for k in ("hote", "port", "utilisateur", "expediteur", "nom_expediteur", "ssl", "actif", "source")},
            "a_mot_de_passe": bool(c["mot_de_passe"]),
            "resend_actif": eff.get("fournisseur") == "resend" and bool(eff.get("cle")),
            "resend_expediteur": eff.get("expediteur", "") if eff.get("fournisseur") == "resend" else ""}


# ---------------------------------------------------------------------------
# Enregistrement
# ---------------------------------------------------------------------------
class ReglagesEmail(BaseModel):
    fournisseur: Literal["resend", "zeptomail", "brevo", "smtp", "desactive"]
    actif: bool = True
    expediteur: Optional[EmailStr] = None  # adresse sur un domaine validé chez le fournisseur
    nom_expediteur: str = Field("adLyn", max_length=60)
    cle_api: Optional[str] = Field(None, max_length=500)  # vide = clé conservée
    zeptomail_hote: Literal["api.zeptomail.com", "api.zeptomail.eu", "api.zeptomail.in"] = "api.zeptomail.com"
    # SMTP (champs historiques)
    hote: str = Field("", max_length=120)
    port: int = Field(587, ge=1, le=65535)
    ssl: bool = False
    utilisateur: str = Field("", max_length=160)
    mot_de_passe: Optional[str] = Field(None, max_length=200)  # vide = inchangé

    @model_validator(mode="after")
    def _coherence(self):
        # Champs obligatoires selon le service choisi
        if self.fournisseur != "desactive" and not self.expediteur:
            raise ValueError("Adresse d'expéditeur obligatoire")
        if self.fournisseur == "smtp" and len(self.hote.strip()) < 3:
            raise ValueError("Serveur SMTP obligatoire")
        return self


async def _enregistrer(payload: ReglagesEmail, adm: dict) -> None:
    """Écrit le réglage (secrets chiffrés ; champ secret vide = valeur conservée) et le journalise."""
    actuel = await envois.lire_reglages_email()
    doc = {"fournisseur": payload.fournisseur, "actif": payload.actif,
           "expediteur": str(payload.expediteur or actuel.get("expediteur") or ""),
           "nom_expediteur": envois.nettoyer_nom(payload.nom_expediteur), "zeptomail_hote": payload.zeptomail_hote,
           "modifie_le": now_iso(), "modifie_par": adm.get("email", "")}
    # Clé API : une par fournisseur, pour pouvoir passer de l'un à l'autre sans tout ressaisir
    cles = dict(actuel.get("cles_chiffrees") or {})
    if payload.cle_api and payload.cle_api.strip() and payload.fournisseur in envois.FOURNISSEURS_API:
        cles[payload.fournisseur] = envois.chiffrer(payload.cle_api.strip())
    doc["cles_chiffrees"] = cles
    # SMTP : seulement si ce service est choisi (les anciens réglages restent sinon en base)
    if payload.fournisseur == "smtp":
        doc.update({"hote": payload.hote.strip(), "port": payload.port, "ssl": payload.ssl,
                    "utilisateur": payload.utilisateur.strip()})
        doc["mot_de_passe_chiffre"] = envois.chiffrer(payload.mot_de_passe) if payload.mot_de_passe \
            else actuel.get("mot_de_passe_chiffre", "")
    await db.parametres_plateforme.update_one({"_id": envois.DOC_EMAIL}, {"$set": doc}, upsert=True)
    await envois.journaliser_reglage(adm, payload.fournisseur)


@router.put("/email")
async def enregistrer_email(payload: ReglagesEmail, adm: dict = Depends(get_super_admin)):
    await _enregistrer(payload, adm)
    return await _etat_email()


class ReglagesSmtp(BaseModel):
    """Ancienne route PUT /smtp : choisit le service « smtp » avec ces réglages."""
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
    await _enregistrer(ReglagesEmail(fournisseur="smtp", **payload.model_dump()), adm)
    return await lire_smtp(adm)


# ---------------------------------------------------------------------------
# E-mail d'essai (réglages ENREGISTRÉS) et journal des modifications
# ---------------------------------------------------------------------------
class Essai(BaseModel):
    destinataire: EmailStr


async def _essai(destinataire: str) -> dict:
    statut, erreur = await envois.envoyer_email(
        "[adLyn] E-mail d'essai", "Bonjour,\n\nCet e-mail confirme que le service d'envoi de la plateforme adLyn "
        "fonctionne.\n\nL'équipe adLyn", destinataire)
    if statut != "ENVOYE":
        # Message du fournisseur affiché tel quel (jamais la clé)
        raise HTTPException(400, f"Envoi impossible : {erreur}")
    return {"ok": True}


@router.post("/email/essai")
async def essai_email(payload: Essai, _: dict = Depends(get_super_admin)):
    return await _essai(str(payload.destinataire))


@router.post("/smtp/essai")
async def essai_smtp(payload: Essai, _: dict = Depends(get_super_admin)):
    return await _essai(str(payload.destinataire))


@router.get("/email/journal")
async def journal_email(_: dict = Depends(get_super_admin)):
    """Dernières modifications du service d'envoi de la plateforme : qui, quand, quel fournisseur."""
    return await db.journal_reglages_email.find({"cible": "plateforme"}, SANS_ID).sort("date", -1).to_list(20)
