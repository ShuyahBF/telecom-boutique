"""Parrainage entre boutiques : page publique d'invitation, tableau de bord du
parrain (DG) et suivi par le super-administrateur. Règles : voir parrainage.py."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

import envois_plateforme as envois
import parrainage as service
from auth import Contexte, get_super_admin, permission
from config import get_settings
from db import SANS_ID, db
from routes.plateforme import enregistrer_boutique, envoyer_identifiants, mot_de_passe_temporaire
from routes.webhooks import DemandeBoutique, _boutique_existante, _invraisemblance
from utils import new_id, normaliser_telephone

public = APIRouter(prefix="/public/parrainage", tags=["Parrainage (public)"])
boutique = APIRouter(prefix="/boutique/parrainage", tags=["Parrainage (DG)"])
admin = APIRouter(prefix="/plateforme/parrainages", tags=["Parrainage (super-admin)"])


async def _parrain(code: str) -> dict:
    """Boutique marraine : ouverte (validée, active) et réelle (pas de démo)."""
    b = await db.boutiques.find_one({"code_marchand": (code or "").strip().upper()}, SANS_ID)
    if not b or not b.get("validee", True) or b.get("actif") is False or b.get("test"):
        raise HTTPException(404, "Lien d'invitation invalide")
    return b


def _ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()


# ---------------------------------------------------------------------------
# Page publique « Ouvrir ma boutique » (lien partagé par le parrain)
# ---------------------------------------------------------------------------
@public.get("/{code}")
async def invitation(code: str):
    """Qui invite (affiché en tête de la page d'ouverture)."""
    b = await _parrain(code)
    return {"parrain": {"nom": b["nom"], "ville": b.get("ville", ""), "logo_url": b.get("logo_url"),
                        "code": b["code_marchand"]}}


class DemandeOuverture(BaseModel):
    nom: str = Field(..., min_length=3, max_length=120)
    pays: str = Field("Burkina Faso", min_length=2, max_length=60)
    ville: str = Field(..., min_length=2, max_length=80)
    telephone: str = Field("", max_length=30)
    dg_nom: str = Field(..., min_length=3, max_length=120)
    dg_email: EmailStr
    dg_telephone: str = Field(..., min_length=8, max_length=30)
    # L'invité accepte l'invitation (le parrainage) de la boutique marraine
    accepte_invitation: bool = False
    accepte_conditions: bool = False


@public.post("/{code}/demande", status_code=201)
async def demander_ouverture(code: str, data: DemandeOuverture, request: Request):
    s = get_settings()
    parrain = await _parrain(code)
    if not data.accepte_invitation:
        raise HTTPException(400, f"Acceptez l'invitation de {parrain['nom']} pour continuer")
    if not data.accepte_conditions:
        raise HTTPException(400, "Acceptez les conditions d'utilisation d'adLyn")

    # Garde-fous : demandes par adresse IP (heure) et par parrain (jour)
    ip = _ip(request)
    maintenant = datetime.now(timezone.utc)
    if await db.parrainages.count_documents({"ip": ip, "created_at": {"$gte": (maintenant - timedelta(hours=1)).isoformat()}}) \
            >= s.parrainage_max_demandes_ip_heure:
        raise HTTPException(429, "Trop de demandes depuis cette connexion : réessayez plus tard")
    if await db.parrainages.count_documents({"parrain_id": parrain["id"],
                                             "created_at": {"$gte": (maintenant - timedelta(days=1)).isoformat()}}) \
            >= s.parrainage_max_demandes_parrain_jour:
        raise HTTPException(429, "Ce lien a atteint sa limite de demandes pour aujourd'hui : réessayez demain")

    # Mêmes contrôles que les créations par webhook (nom, e-mail jetable, téléphone…)
    demande = DemandeBoutique(evenement_id=f"parrainage-{new_id()}", nom=data.nom, pays=data.pays, ville=data.ville,
                              telephone=data.telephone, dg_nom=data.dg_nom, dg_email=data.dg_email,
                              dg_telephone=data.dg_telephone)
    raison = _invraisemblance(demande)
    if raison:
        raise HTTPException(422, raison)
    if await _boutique_existante(demande):
        raise HTTPException(409, "Cette boutique ou ce DG est déjà inscrit sur adLyn")
    # On ne se parraine pas soi-même
    tel_dg = normaliser_telephone(data.dg_telephone)
    dg_parrain = await db.users.find_one({"boutique_id": parrain["id"], "role": "dg"}, SANS_ID) or {}
    if tel_dg and tel_dg in {normaliser_telephone(parrain.get("dg_telephone")), normaliser_telephone(parrain.get("telephone"))} \
            or data.dg_email.lower() == (dg_parrain.get("email") or "").lower():
        raise HTTPException(400, "Une boutique ne peut pas se parrainer elle-même")

    # Création : boutique EN ATTENTE DE VALIDATION + DG avec mot de passe provisoire
    mot_de_passe = mot_de_passe_temporaire()
    donnees = demande.model_dump(exclude={"evenement_id", "dg_email", "reference_externe"})
    donnees["dg_telephone"] = tel_dg
    filleul, dg, _ = await enregistrer_boutique(donnees, dg_email=data.dg_email, dg_mot_de_passe=mot_de_passe,
                                                validee=False, origine="parrainage", doit_changer_mot_de_passe=True)
    await service.enregistrer_invitation(parrain, filleul, ip=ip)
    envoi = await envoyer_identifiants(filleul, dg, mot_de_passe, data.dg_telephone)
    if s.rapport_email:
        await envois.envoyer_email(
            f"[adLyn] Nouvelle boutique parrainée à valider : {filleul['nom']}",
            "\n".join([f"Boutique : {filleul['nom']} ({filleul['ville']}, {filleul['pays']})",
                       f"Parrain : {parrain['nom']} ({parrain['code_marchand']})",
                       f"DG : {dg['nom']} — {dg['email']} — {tel_dg}", "",
                       f"À valider dans l'administration : {s.public_site_url}/plateforme"]),
            s.rapport_email)
    return {"resultat": "creee", "code_boutique": filleul["code_marchand"], "statut": "EN_ATTENTE_VALIDATION",
            "identifiants_envoyes": {"email": envoi["email"], "sms": envoi["sms"], "whatsapp": envoi.get("whatsapp")}}


# ---------------------------------------------------------------------------
# Tableau de bord du parrain (DG)
# ---------------------------------------------------------------------------
@boutique.get("")
async def mon_parrainage(ctx: Contexte = Depends(permission("parametres"))):
    b = ctx.boutique
    return {
        "lien": f"{get_settings().public_site_url}/ouvrir-ma-boutique?parrain={b['code_marchand']}",
        "code": b["code_marchand"], "bonus_unitaire": service.bonus_unitaire(),
        "solde": await service.solde(b["id"]), "filleuls": await service.filleuls(b["id"]),
        "mouvements": await service.mouvements(b["id"]),
        # Démo / boutique pas encore ouverte : le lien ne fonctionne pas encore
        "lien_actif": bool(b.get("validee", True) and b.get("actif") is not False and not b.get("test")),
    }


# ---------------------------------------------------------------------------
# Super-administrateur
# ---------------------------------------------------------------------------
@admin.get("")
async def tous_les_parrainages(statut: Optional[str] = None, _: dict = Depends(get_super_admin)):
    filtre = {"statut": statut} if statut else {}
    return await db.parrainages.find(filtre, {**SANS_ID, "ip": 0}).sort("created_at", -1).to_list(500)
