"""Administration de la PLATEFORME (super-administrateur uniquement) :
création des boutiques (tenants) et de leur premier compte : le DG."""
from __future__ import annotations

import re
import secrets
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr, Field

import kyc as service_kyc
from auth import get_super_admin, hash_password, user_public
from db import SANS_ID, db
from routes.auth import _sans_secrets
from utils import new_id, normaliser_telephone, now_iso, slugifier

router = APIRouter(prefix="/plateforme", tags=["Plateforme (super-admin)"])

# Alphabet du code marchand : sans 0/O ni 1/I, pour éviter les confusions à l'oral
_ALPHABET_CODE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


async def _code_marchand_unique() -> str:
    while True:
        code = "".join(secrets.choice(_ALPHABET_CODE) for _ in range(6))
        if not await db.boutiques.find_one({"code_marchand": code}):
            return code


async def _slug_unique(nom: str, sauf_id: Optional[str] = None) -> str:
    base = slugifier(nom)
    slug, n = base, 2
    while True:
        existant = await db.boutiques.find_one({"slug": slug}, {"_id": 0, "id": 1})
        if not existant or existant["id"] == sauf_id:
            return slug
        slug, n = f"{base}-{n}", n + 1


class Identification(BaseModel):
    """Informations légales et de localisation d'une boutique (KYC)."""
    pays: str = Field("Burkina Faso", max_length=60)
    ville: str = Field("", max_length=80)
    adresse: str = Field("", max_length=500)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    dg_nom: str = Field("", max_length=120)  # nom du Directeur Général
    dg_telephone: str = Field("", max_length=30)  # reçoit les identifiants par SMS
    ifu: str = Field("", max_length=50)
    cnss: str = Field("", max_length=50)
    rccm: str = Field("", max_length=60)


class BoutiqueCreation(Identification):
    nom: str = Field(..., min_length=2, max_length=120)
    telephone: str = ""
    email: Optional[EmailStr] = None
    code_marchand: Optional[str] = Field(None, max_length=12)
    # Premier compte gérant de la boutique
    # Compte du DG (son nom est celui de dg_nom, obligatoire ici)
    dg_email: EmailStr
    dg_mot_de_passe: str = Field(..., min_length=8)


class BoutiqueMaj(BaseModel):
    nom: Optional[str] = Field(None, min_length=2, max_length=120)
    pays: Optional[str] = Field(None, max_length=60)
    ville: Optional[str] = Field(None, max_length=80)
    adresse: Optional[str] = Field(None, max_length=500)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    dg_nom: Optional[str] = Field(None, max_length=120)
    dg_telephone: Optional[str] = Field(None, max_length=30)
    ifu: Optional[str] = Field(None, max_length=50)
    cnss: Optional[str] = Field(None, max_length=50)
    rccm: Optional[str] = Field(None, max_length=60)
    code_marchand: Optional[str] = Field(None, max_length=12)
    actif: Optional[bool] = None
    mise_en_avant: Optional[bool] = None  # affichée en tête du carrousel
    ordre: Optional[int] = None


def _normaliser_code(code: str) -> str:
    """Code marchand = « ID boutique » tapé à la connexion : exactement 6 lettres
    ou chiffres, sans espace (les tirets/espaces saisis sont retirés)."""
    code = re.sub(r"[^A-Za-z0-9]", "", code or "").upper()
    if len(code) != 6:
        raise HTTPException(400, "L'ID boutique (code marchand) doit contenir exactement 6 lettres ou chiffres")
    return code


def mot_de_passe_temporaire() -> str:
    """Mot de passe provisoire (10 caractères sans ambiguïté), à changer à la 1re connexion."""
    return "".join(secrets.choice(_ALPHABET_CODE + "abcdefghjkmnpqrstuvwxyz") for _ in range(10))


async def enregistrer_boutique(donnees: dict, *, dg_email: str, dg_mot_de_passe: str, validee: bool,
                               origine: str, doit_changer_mot_de_passe: bool = False,
                               code: Optional[str] = None) -> tuple[dict, dict, int]:
    """Crée la boutique, le compte de son DG et copie le catalogue public.
    Utilisé par la création manuelle (super-admin) ET par le webhook.
    `donnees` : nom, telephone, email + champs d'Identification."""
    nom = donnees["nom"].strip()
    boutique = {
        "id": new_id(), "nom": nom, "slug": await _slug_unique(nom),
        "code_marchand": code or await _code_marchand_unique(),
        "telephone": normaliser_telephone(donnees.get("telephone")), "email": donnees.get("email") or "",
        "actif": True, "mise_en_avant": False, "ordre": 0, "created_at": now_iso(),
        # validee = False : créée automatiquement, invisible du public jusqu'à validation
        "validee": validee, "origine": origine,
        **boutique_par_defaut(nom),
        **Identification(**{k: v for k, v in donnees.items() if k in Identification.model_fields}).model_dump(),
    }
    await db.boutiques.insert_one(boutique.copy())
    dg = {
        "id": new_id(), "email": dg_email.lower(), "nom": boutique["dg_nom"].strip(),
        "password_hash": hash_password(dg_mot_de_passe), "role": "dg",
        "boutique_id": boutique["id"], "actif": True, "created_at": now_iso(),
        "doit_changer_mot_de_passe": doit_changer_mot_de_passe,
    }
    await db.users.insert_one(dg.copy())
    # Première initialisation : la boutique reçoit tout le catalogue public (sans prix)
    from catalogue_public import copier_catalogue_dans_boutique
    nb_produits = await copier_catalogue_dans_boutique(boutique["id"])
    return boutique, dg, nb_produits


async def envoyer_identifiants(boutique: dict, dg: dict, mot_de_passe: str, telephone: str) -> dict:
    """Envoie au DG son ID boutique et son mot de passe provisoire, par e-mail
    ET par SMS (serveurs de la plateforme). Renvoie le statut de chaque canal,
    sans jamais le mot de passe."""
    from config import get_settings
    import envois_plateforme as envois

    url = get_settings().public_site_url
    sujet = f"[adLyn] Votre boutique « {boutique['nom']} » est créée"
    corps = "\n".join([
        f"Bonjour {dg.get('nom') or ''},", "",
        f"Votre boutique « {boutique['nom']} » a été créée sur adLyn.", "",
        f"Adresse de connexion : {url}/connexion",
        f"ID boutique : {boutique['code_marchand']}",
        f"E-mail : {dg['email']}",
        f"Mot de passe provisoire : {mot_de_passe}", "",
        "Ce mot de passe devra être changé dès votre première connexion.",
        "Votre boutique sera visible du public après validation par l'équipe adLyn.", "",
        "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.",
    ])
    sms = (f"adLyn : boutique {boutique['nom'][:40]} creee. ID boutique {boutique['code_marchand']}, "
           f"mot de passe provisoire {mot_de_passe} (a changer a la 1re connexion). {url}/connexion")
    email_statut, email_erreur = await envois.envoyer_email(sujet, corps, dg["email"])
    sms_statut, sms_erreur = await envois.envoyer_sms(telephone, sms)
    envoi = {"date": now_iso(), "email": email_statut, "email_erreur": email_erreur,
             "sms": sms_statut, "sms_erreur": sms_erreur}
    await db.boutiques.update_one({"id": boutique["id"]}, {"$set": {"identifiants_envoi": envoi}})
    return envoi


def boutique_par_defaut(nom: str) -> dict:
    """Valeurs initiales d'une nouvelle boutique (modifiables par son gérant)."""
    return {
        "slogan": "", "logo_url": None, "kyc": service_kyc.kyc_vide(),
        "devise": "FCFA", "taux_tva_defaut": 18.0, "prix_ttc": True, "validite_proforma_jours": 15,
        "conditions_facture": "Les marchandises vendues ne sont ni reprises ni échangées.",
        "couleur": "#0b5ed7", "paiement_mobile_money": True,
        "messagerie": {"email_actif": False, "smtp_hote": "", "smtp_port": 587, "smtp_utilisateur": "",
                       "smtp_mot_de_passe": "", "smtp_tls": True, "smtp_ssl": False,
                       "expediteur_nom": nom, "expediteur_email": "", "email_equipe": ""},
    }


@router.get("/boutiques")
async def lister_boutiques(_: dict = Depends(get_super_admin)):
    boutiques = await db.boutiques.find({}, SANS_ID).sort("nom", 1).to_list(1000)
    # Nombre de comptes par boutique (aide au suivi)
    for b in boutiques:
        b["nb_utilisateurs"] = await db.users.count_documents({"boutique_id": b["id"]})
    return [_sans_secrets(b) for b in boutiques]


@router.post("/boutiques", status_code=201)
async def creer_boutique(payload: BoutiqueCreation, admin: dict = Depends(get_super_admin)):
    if len(payload.dg_nom.strip()) < 2:
        raise HTTPException(400, "Indiquez le nom du DG de la boutique")
    if await db.users.find_one({"email": payload.dg_email.lower()}):
        raise HTTPException(409, "Un compte existe déjà avec l'e-mail du DG")
    code = _normaliser_code(payload.code_marchand) if payload.code_marchand else None
    if code and await db.boutiques.find_one({"code_marchand": code}):
        raise HTTPException(409, "Ce code marchand est déjà utilisé")
    donnees = payload.model_dump(exclude={"dg_email", "dg_mot_de_passe", "code_marchand"})
    boutique, dg, nb_produits = await enregistrer_boutique(
        donnees, dg_email=payload.dg_email, dg_mot_de_passe=payload.dg_mot_de_passe,
        validee=True, origine="super_admin", code=code)
    return {"boutique": _sans_secrets(boutique), "dg": user_public(dg), "produits_copies": nb_produits}


@router.post("/boutiques/{boutique_id}/valider")
async def valider_boutique(boutique_id: str, admin: dict = Depends(get_super_admin)):
    """Boutique créée par le webhook : après vérification, elle devient visible du public."""
    res = await db.boutiques.update_one({"id": boutique_id}, {"$set": {
        "validee": True, "validee_le": now_iso(), "validee_par": admin.get("email", "")}})
    if not res.matched_count:
        raise HTTPException(404, "Boutique introuvable")
    return _sans_secrets(await db.boutiques.find_one({"id": boutique_id}, SANS_ID))


@router.post("/boutiques/{boutique_id}/renvoyer-identifiants")
async def renvoyer_identifiants(boutique_id: str, _: dict = Depends(get_super_admin)):
    """Nouveau mot de passe provisoire pour le DG, renvoyé par e-mail et SMS
    (ex. : le premier envoi a échoué). L'ancien mot de passe ne fonctionne plus."""
    boutique = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    dg = await db.users.find_one({"boutique_id": boutique_id, "role": "dg", "actif": True}, SANS_ID) if boutique else None
    if not dg:
        raise HTTPException(404, "Boutique ou DG introuvable")
    mot_de_passe = mot_de_passe_temporaire()
    await db.users.update_one({"id": dg["id"]}, {
        "$set": {"password_hash": hash_password(mot_de_passe), "doit_changer_mot_de_passe": True},
        "$inc": {"version_session": 1}})  # déconnecte les sessions ouvertes
    telephone = boutique.get("dg_telephone") or boutique.get("telephone", "")
    return await envoyer_identifiants(boutique, dg, mot_de_passe, telephone)


@router.patch("/boutiques/{boutique_id}")
async def modifier_boutique(boutique_id: str, payload: BoutiqueMaj, _: dict = Depends(get_super_admin)):
    boutique = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not boutique:
        raise HTTPException(404, "Boutique introuvable")
    maj = payload.model_dump(exclude_none=True)
    # Coordonnées : une valeur vide (null) envoyée explicitement les efface
    for champ in ("latitude", "longitude"):
        if champ in payload.model_fields_set and getattr(payload, champ) is None:
            maj[champ] = None
    if "code_marchand" in maj:
        maj["code_marchand"] = _normaliser_code(maj["code_marchand"])
        autre = await db.boutiques.find_one({"code_marchand": maj["code_marchand"]}, {"_id": 0, "id": 1})
        if autre and autre["id"] != boutique_id:
            raise HTTPException(409, "Ce code marchand est déjà utilisé")
    if "nom" in maj:
        maj["slug"] = await _slug_unique(maj["nom"], sauf_id=boutique_id)
    if maj:
        await db.boutiques.update_one({"id": boutique_id}, {"$set": maj})
    return _sans_secrets(await db.boutiques.find_one({"id": boutique_id}, SANS_ID))


@router.get("/statistiques")
async def statistiques(_: dict = Depends(get_super_admin)):
    return {
        "boutiques": await db.boutiques.count_documents({}),
        "boutiques_actives": await db.boutiques.count_documents({"actif": True}),
        "utilisateurs": await db.users.count_documents({"role": {"$ne": "super_admin"}}),
        "commandes": await db.commandes.count_documents({}),
        "factures_validees": await db.documents.count_documents({"type_document": "FAC", "statut": "VALIDE"}),
    }


# ---------------------------------------------------------------------------
# Dossier KYC d'une boutique (vérification par l'administrateur)
# ---------------------------------------------------------------------------
@router.post("/boutiques/{boutique_id}/kyc/documents")
async def ajouter_justificatif(boutique_id: str, fichier: UploadFile = File(...), type_piece: str = Form(...),
                               admin: dict = Depends(get_super_admin)):
    boutique = await service_kyc.boutique_ou_404(boutique_id)
    return await service_kyc.ajouter_piece(boutique, fichier, type_piece, admin.get("nom", "Administrateur"))


@router.get("/boutiques/{boutique_id}/kyc/documents/{piece_id}")
async def ouvrir_justificatif(boutique_id: str, piece_id: str, _: dict = Depends(get_super_admin)):
    return await service_kyc.ouvrir_piece(await service_kyc.boutique_ou_404(boutique_id), piece_id)


@router.delete("/boutiques/{boutique_id}/kyc/documents/{piece_id}")
async def retirer_justificatif(boutique_id: str, piece_id: str, _: dict = Depends(get_super_admin)):
    return await service_kyc.retirer_piece(await service_kyc.boutique_ou_404(boutique_id), piece_id)


class DecisionKyc(BaseModel):
    statut: Literal["VERIFIE", "REJETE", "EN_ATTENTE"]
    motif_rejet: str = Field("", max_length=500)


@router.post("/boutiques/{boutique_id}/kyc/decision")
async def decider_kyc(boutique_id: str, payload: DecisionKyc, admin: dict = Depends(get_super_admin)):
    boutique = await service_kyc.boutique_ou_404(boutique_id)
    kyc = boutique.get("kyc") or service_kyc.kyc_vide()
    if payload.statut == "REJETE" and not payload.motif_rejet.strip():
        raise HTTPException(400, "Indiquez le motif du rejet (il sera affiché au DG)")
    kyc.update({"statut": payload.statut, "motif_rejet": payload.motif_rejet.strip(),
                "verifie_par": admin.get("nom", ""), "date_verification": now_iso()})
    await db.boutiques.update_one({"id": boutique_id}, {"$set": {"kyc": kyc}})
    return service_kyc.kyc_public(kyc)
