"""Paramètres de SA boutique (réservé au DG) : fiche d'identité, logo,
messagerie (SMTP, textes des e-mails, journal) et équipe."""
from __future__ import annotations

from typing import Literal, Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError

import identifiants
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
    dg_telephone: Optional[str] = Field(None, max_length=30)
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
    # Coordonnées : une valeur vide (null) envoyée explicitement les efface
    for champ in ("latitude", "longitude"):
        if champ in payload.model_fields_set and getattr(payload, champ) is None:
            maj[champ] = None
    if "telephone" in maj:
        maj["telephone"] = normaliser_telephone(maj["telephone"])
    if "dg_telephone" in maj:
        maj["dg_telephone"] = normaliser_telephone(maj["dg_telephone"])
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


@router.get("/messagerie/fournisseur")
async def fournisseur_messagerie(_: Contexte = Depends(parametres)):
    """Mode d'envoi en vigueur : Resend (réglé par la plateforme) ou SMTP de la boutique."""
    import envois_plateforme
    actif = envois_plateforme.resend_configure()
    return {"resend_actif": actif, "resend_expediteur": envois_plateforme.resend_expediteur() if actif else ""}


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
    # Identifiants de connexion : e-mail et/ou téléphone (au moins l'un des deux)
    email: Optional[Union[EmailStr, Literal[""]]] = None
    telephone: Optional[str] = Field(None, max_length=30)
    # Vide = mot de passe provisoire tiré au hasard par le serveur (conseillé)
    mot_de_passe: Optional[str] = Field(None, max_length=200)
    role: Literal["dg", "commercial", "secretaire", "comptable", "technicien"] = "commercial"


class MembreMaj(BaseModel):
    nom: Optional[str] = Field(None, min_length=2, max_length=100)
    role: Optional[Literal["dg", "commercial", "secretaire", "comptable", "technicien"]] = None
    actif: Optional[bool] = None
    mot_de_passe: Optional[str] = Field(None, min_length=8)
    # Identifiants de connexion ("" = retirer ; il doit en rester au moins un)
    email: Optional[Union[EmailStr, Literal[""]]] = None
    telephone: Optional[str] = Field(None, max_length=30)


@router.get("/equipe")
async def lister_equipe(ctx: Contexte = Depends(tout_le_personnel)):
    membres = await db.users.find({"boutique_id": ctx.boutique["id"]}, SANS_ID).sort("nom", 1).to_list(500)
    return [user_public(m) for m in membres]


@router.post("/equipe", status_code=201)
async def ajouter_membre(payload: MembreCreation, request: Request, ctx: Contexte = Depends(parametres)):
    email = str(payload.email).lower() if payload.email else None
    telephone = identifiants.valeur_normalisee("telephone", payload.telephone) if (payload.telephone or "").strip() else None
    if not (email or telephone):
        raise HTTPException(400, "Indiquez l'e-mail ou le numéro de téléphone de la personne (au moins l'un des deux)")
    if payload.mot_de_passe and len(payload.mot_de_passe) < 8:
        raise HTTPException(400, "Le mot de passe provisoire doit contenir au moins 8 caractères")
    for type_, valeur in (("email", email), ("telephone", telephone)):
        if valeur:
            await identifiants.verifier_disponible(type_, valeur)
    mot_de_passe = payload.mot_de_passe or identifiants.mot_de_passe_provisoire()
    membre = {
        "id": new_id(), "nom": payload.nom.strip(),
        "password_hash": hash_password(mot_de_passe), "role": payload.role,
        "boutique_id": ctx.boutique["id"], "actif": True, "created_at": now_iso(),
        # Mot de passe choisi par le DG : provisoire, à changer à la 1re connexion
        "doit_changer_mot_de_passe": True,
    }
    # Un identifiant absent n'est PAS enregistré (ni vide) : l'index unique l'ignore
    if email:
        membre["email"] = email
    if telephone:
        membre["telephone"] = telephone
    try:
        await db.users.insert_one(membre.copy())
    except DuplicateKeyError:
        raise HTTPException(409, "Un compte existe déjà avec cet e-mail ou ce téléphone") from None
    # Identifiants provisoires envoyés à la personne : WhatsApp, sinon SMS, sinon e-mail
    envoi = await identifiants.envoyer_identifiants_provisoires(membre, ctx.boutique, mot_de_passe)
    await identifiants.journaliser("COMPTE_CREE", cible=membre, par=ctx.user, request=request,
                                   canal=envoi["canal"], statut=envoi["statut"])
    return {**user_public(membre), "envoi": _envoi_public(envoi, mot_de_passe)}


def _envoi_public(envoi: dict, mot_de_passe: str) -> dict:
    """Résultat de l'envoi affiché au DG. Si RIEN n'a pu partir, le mot de passe
    provisoire lui est montré (une seule fois) pour qu'il le remette en main propre."""
    public = {k: envoi[k] for k in ("canal", "statut", "erreur", "essais")}
    if envoi["statut"] != "ENVOYE":
        public["mot_de_passe_provisoire"] = mot_de_passe
    return public


async def _membre_de_la_boutique(user_id: str, ctx: Contexte) -> dict:
    # Filtre boutique_id : un gérant ne peut modifier QUE les comptes de sa boutique
    membre = await db.users.find_one({"id": user_id, "boutique_id": ctx.boutique["id"]}, SANS_ID)
    if not membre:
        raise HTTPException(404, "Membre introuvable")
    return membre


@router.patch("/equipe/{user_id}")
async def modifier_membre(user_id: str, payload: MembreMaj, request: Request, ctx: Contexte = Depends(parametres)):
    membre = await _membre_de_la_boutique(user_id, ctx)
    if user_id == ctx.user["id"] and (payload.actif is False or (payload.role and payload.role != "dg")):
        raise HTTPException(400, "Vous ne pouvez pas vous retirer vous-même le rôle de DG")
    # Identifiants de connexion (e-mail / téléphone) : sans code, le DG en répond ;
    # le membre est prévenu sur l'ancien ET le nouveau contact
    champs_identifiants = {k: (str(getattr(payload, k)) if getattr(payload, k) is not None else "")
                           for k in ("email", "telephone") if k in payload.model_fields_set}
    notifications = []
    if champs_identifiants:
        if user_id == ctx.user["id"]:
            raise HTTPException(400, "Pour vos propres identifiants, passez par « Mon compte » (confirmation par code)")
        membre, notifications = await identifiants.modifier_par_responsable(
            membre, ctx.boutique, champs_identifiants, par=ctx.user, request=request)
    maj = payload.model_dump(exclude_none=True, exclude={"email", "telephone"})
    operation: dict = {}
    if "mot_de_passe" in maj:
        maj["password_hash"] = hash_password(maj.pop("mot_de_passe"))
        # Mot de passe donné par le DG : provisoire, le membre le changera à sa connexion
        maj["doit_changer_mot_de_passe"] = user_id != ctx.user["id"]
        await identifiants.journaliser("MDP_MODIFIE_PAR_DG", cible=membre, par=ctx.user, request=request)
    if ("password_hash" in maj and user_id != ctx.user["id"]) or payload.actif is False:
        operation["$inc"] = {"version_session": 1}  # ses sessions ouvertes sont fermées
    if maj:
        operation["$set"] = maj
    if operation:
        await db.users.update_one({"id": user_id, "boutique_id": ctx.boutique["id"]}, operation)
    resultat = user_public(await db.users.find_one({"id": user_id}, SANS_ID))
    if notifications:
        resultat["notifications"] = notifications
    return resultat


@router.post("/equipe/{user_id}/nouveau-mot-de-passe")
async def envoyer_nouveau_mot_de_passe(user_id: str, request: Request, ctx: Contexte = Depends(parametres)):
    """Nouveau mot de passe PROVISOIRE tiré au hasard et envoyé au membre (WhatsApp,
    sinon SMS, sinon e-mail). L'ancien ne fonctionne plus et ses sessions sont fermées."""
    membre = await _membre_de_la_boutique(user_id, ctx)
    if user_id == ctx.user["id"]:
        raise HTTPException(400, "Pour votre propre mot de passe, utilisez « Changer mon mot de passe »")
    mot_de_passe = identifiants.mot_de_passe_provisoire()
    await db.users.update_one({"id": user_id}, {
        "$set": {"password_hash": hash_password(mot_de_passe), "doit_changer_mot_de_passe": True},
        "$inc": {"version_session": 1}})
    envoi = await identifiants.envoyer_identifiants_provisoires(membre, ctx.boutique, mot_de_passe)
    await identifiants.journaliser("MDP_PROVISOIRE_ENVOYE", cible=membre, par=ctx.user, request=request,
                                   canal=envoi["canal"], statut=envoi["statut"])
    return {"envoi": _envoi_public(envoi, mot_de_passe)}


@router.get("/equipe/journal-identifiants")
async def journal_identifiants(ctx: Contexte = Depends(parametres)):
    """Historique des actions sur les identifiants des comptes de la boutique (sans secret)."""
    return await identifiants.lire_journal({"boutique_id": ctx.boutique["id"]})
