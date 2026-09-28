"""Paramètres de SA boutique (réservé au DG) : fiche d'identité, logo,
messagerie (SMTP, textes des e-mails, journal) et équipe."""
from __future__ import annotations

from typing import Literal, Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr, Field

import kyc as service_kyc
from auth import ROLES_BOUTIQUE, Contexte, hash_password, permission, tout_le_personnel, user_public
from db import SANS_ID, db
from messagerie import MODELES_PAR_DEFAUT, envoyer_email, modeles_de
from routes.auth import _sans_secrets
from storage import enregistrer_image, lire_image, supprimer_image
from utils import new_id, normaliser_telephone, now_iso

router = APIRouter(prefix="/boutique", tags=["Ma boutique"])
# Droits requis (voir la table PERMISSIONS dans auth.py)
parametres = permission("parametres")


@router.get("")
async def ma_boutique(ctx: Contexte = Depends(tout_le_personnel)):
    return _sans_secrets(ctx.boutique)


class FicheBoutique(BaseModel):
    slogan: Optional[str] = Field(None, max_length=200)
    adresse: Optional[str] = Field(None, max_length=500)
    ville: Optional[str] = Field(None, max_length=80)
    telephone: Optional[str] = Field(None, max_length=30)
    email: Optional[Union[EmailStr, Literal[""]]] = None  # "" = effacer l'e-mail
    ifu: Optional[str] = Field(None, max_length=50)
    rccm: Optional[str] = Field(None, max_length=60)
    cnss: Optional[str] = Field(None, max_length=50)
    dg_nom: Optional[str] = Field(None, max_length=120)
    # Géolocalisation (affichée aux clients : itinéraire vers la boutique)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    devise: Optional[str] = Field(None, max_length=10)
    taux_tva_defaut: Optional[float] = Field(None, ge=0, le=100)
    prix_ttc: Optional[bool] = None  # prix du catalogue exprimés TTC (défaut) ou HT
    validite_proforma_jours: Optional[int] = Field(None, ge=1, le=365)
    conditions_facture: Optional[str] = Field(None, max_length=1000)
    couleur: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    paiement_mobile_money: Optional[bool] = None


@router.patch("")
async def modifier_fiche(payload: FicheBoutique, ctx: Contexte = Depends(parametres)):
    # Le nom et le code marchand sont gérés par l'administrateur de la plateforme
    maj = payload.model_dump(exclude_none=True)
    if "telephone" in maj:
        maj["telephone"] = normaliser_telephone(maj["telephone"])
    # Les informations légales modifiées doivent être revérifiées par l'administrateur
    legales = ("ifu", "rccm", "cnss", "dg_nom")
    if any(k in maj and maj[k] != ctx.boutique.get(k) for k in legales) and (ctx.boutique.get("kyc") or {}).get("documents"):
        maj["kyc.statut"] = "EN_ATTENTE"
    if maj:
        await db.boutiques.update_one({"id": ctx.boutique["id"]}, {"$set": maj})
    return _sans_secrets(await db.boutiques.find_one({"id": ctx.boutique["id"]}, SANS_ID))


@router.post("/logo")
async def envoyer_logo(fichier: UploadFile = File(...), ctx: Contexte = Depends(parametres)):
    contenu, type_mime = await lire_image(fichier)
    url = await enregistrer_image(ctx.boutique["id"], "logo", contenu, type_mime)
    await supprimer_image(ctx.boutique["id"], ctx.boutique.get("logo_url"))
    await db.boutiques.update_one({"id": ctx.boutique["id"]}, {"$set": {"logo_url": url}})
    return {"logo_url": url}


# ---------------------------------------------------------------------------
# Dossier KYC (justificatifs privés, envoyés par le DG)
# ---------------------------------------------------------------------------
@router.get("/kyc/types")
async def types_kyc(_: Contexte = Depends(parametres)):
    return {"types": service_kyc.TYPES_PIECES_KYC, "statuts": service_kyc.STATUTS_KYC}


@router.post("/kyc/documents")
async def envoyer_justificatif(fichier: UploadFile = File(...), type_piece: str = Form(...), ctx: Contexte = Depends(parametres)):
    return await service_kyc.ajouter_piece(ctx.boutique, fichier, type_piece, ctx.user.get("nom", ""))


@router.get("/kyc/documents/{piece_id}")
async def ouvrir_justificatif(piece_id: str, ctx: Contexte = Depends(parametres)):
    return await service_kyc.ouvrir_piece(ctx.boutique, piece_id)


@router.delete("/kyc/documents/{piece_id}")
async def retirer_justificatif(piece_id: str, ctx: Contexte = Depends(parametres)):
    if (ctx.boutique.get("kyc") or {}).get("statut") == "VERIFIE" and ctx.role != "super_admin":
        raise HTTPException(409, "Dossier vérifié : contactez l'administrateur pour retirer un justificatif")
    return await service_kyc.retirer_piece(ctx.boutique, piece_id)


# ---------------------------------------------------------------------------
# Messagerie
# ---------------------------------------------------------------------------
class ParametresMessagerie(BaseModel):
    email_actif: bool = False
    smtp_hote: str = Field("", max_length=150)
    smtp_port: int = Field(587, ge=1, le=65535)
    smtp_utilisateur: str = Field("", max_length=150)
    # Vide = mot de passe actuel conservé
    smtp_mot_de_passe: Optional[str] = Field(None, max_length=150)
    smtp_tls: bool = True
    smtp_ssl: bool = False
    expediteur_nom: str = Field("", max_length=100)
    expediteur_email: Optional[EmailStr] = None
    email_equipe: Optional[EmailStr] = None


@router.put("/messagerie")
async def regler_messagerie(payload: ParametresMessagerie, ctx: Contexte = Depends(parametres)):
    actuel = ctx.boutique.get("messagerie") or {}
    nouveau = payload.model_dump()
    if not nouveau.get("smtp_mot_de_passe"):
        nouveau["smtp_mot_de_passe"] = actuel.get("smtp_mot_de_passe", "")
    nouveau["expediteur_email"] = nouveau.get("expediteur_email") or ""
    nouveau["email_equipe"] = nouveau.get("email_equipe") or ""
    await db.boutiques.update_one({"id": ctx.boutique["id"]}, {"$set": {"messagerie": nouveau}})
    return _sans_secrets(await db.boutiques.find_one({"id": ctx.boutique["id"]}, SANS_ID))["messagerie"]


class EmailTest(BaseModel):
    destinataire: EmailStr


@router.post("/messagerie/test")
async def tester_messagerie(payload: EmailTest, ctx: Contexte = Depends(parametres)):
    journal = await envoyer_email(ctx.boutique, payload.destinataire, "Test de messagerie",
                                  "Les réglages de messagerie de votre boutique fonctionnent.", "TEST")
    return {"statut": journal["statut"], "erreur": journal["erreur"]}


@router.get("/messagerie/modeles")
async def lister_modeles(ctx: Contexte = Depends(parametres)):
    return await modeles_de(ctx.tdb)


class ModeleMaj(BaseModel):
    sujet: str = Field(..., min_length=1, max_length=200)
    corps: str = Field(..., min_length=1, max_length=5000)
    actif: bool = True


@router.put("/messagerie/modeles/{code}")
async def modifier_modele(code: str, payload: ModeleMaj, ctx: Contexte = Depends(parametres)):
    if code not in MODELES_PAR_DEFAUT:
        raise HTTPException(404, "Modèle inconnu")
    await modeles_de(ctx.tdb)  # s'assure qu'il existe
    return await ctx.tdb.modeles_messages.find_one_and_update({"code": code}, {"$set": payload.model_dump()})


@router.post("/messagerie/modeles/{code}/reinitialiser")
async def reinitialiser_modele(code: str, ctx: Contexte = Depends(parametres)):
    if code not in MODELES_PAR_DEFAUT:
        raise HTTPException(404, "Modèle inconnu")
    _, sujet, corps = MODELES_PAR_DEFAUT[code]
    await modeles_de(ctx.tdb)
    return await ctx.tdb.modeles_messages.find_one_and_update(
        {"code": code}, {"$set": {"sujet": sujet, "corps": corps, "actif": True}})


@router.get("/messagerie/journal")
async def journal_envois(ctx: Contexte = Depends(parametres)):
    return await ctx.tdb.journal_envois.find({}).sort("date", -1).to_list(200)


# ---------------------------------------------------------------------------
# Équipe de la boutique
# ---------------------------------------------------------------------------
class MembreCreation(BaseModel):
    nom: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    mot_de_passe: str = Field(..., min_length=8)
    role: Literal["dg", "commercial", "secretaire", "comptable", "technicien"] = "commercial"


class MembreMaj(BaseModel):
    nom: Optional[str] = Field(None, min_length=2, max_length=100)
    role: Optional[Literal["dg", "commercial", "secretaire", "comptable", "technicien"]] = None
    actif: Optional[bool] = None
    mot_de_passe: Optional[str] = Field(None, min_length=8)


@router.get("/equipe")
async def lister_equipe(ctx: Contexte = Depends(tout_le_personnel)):
    membres = await db.users.find({"boutique_id": ctx.boutique["id"]}, SANS_ID).sort("nom", 1).to_list(500)
    return [user_public(m) for m in membres]


@router.post("/equipe", status_code=201)
async def ajouter_membre(payload: MembreCreation, ctx: Contexte = Depends(parametres)):
    if await db.users.find_one({"email": payload.email.lower()}):
        raise HTTPException(409, "Un compte existe déjà avec cet e-mail")
    membre = {
        "id": new_id(), "email": payload.email.lower(), "nom": payload.nom.strip(),
        "password_hash": hash_password(payload.mot_de_passe), "role": payload.role,
        "boutique_id": ctx.boutique["id"], "actif": True, "created_at": now_iso(),
    }
    await db.users.insert_one(membre.copy())
    return user_public(membre)


@router.patch("/equipe/{user_id}")
async def modifier_membre(user_id: str, payload: MembreMaj, ctx: Contexte = Depends(parametres)):
    # Filtre boutique_id : un gérant ne peut modifier QUE les comptes de sa boutique
    membre = await db.users.find_one({"id": user_id, "boutique_id": ctx.boutique["id"]}, SANS_ID)
    if not membre:
        raise HTTPException(404, "Membre introuvable")
    if user_id == ctx.user["id"] and (payload.actif is False or (payload.role and payload.role != "dg")):
        raise HTTPException(400, "Vous ne pouvez pas vous retirer vous-même le rôle de DG")
    maj = payload.model_dump(exclude_none=True)
    if "mot_de_passe" in maj:
        maj["password_hash"] = hash_password(maj.pop("mot_de_passe"))
    if maj:
        await db.users.update_one({"id": user_id, "boutique_id": ctx.boutique["id"]}, {"$set": maj})
    return user_public(await db.users.find_one({"id": user_id}, SANS_ID))
