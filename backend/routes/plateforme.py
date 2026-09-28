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
    ifu: Optional[str] = Field(None, max_length=50)
    cnss: Optional[str] = Field(None, max_length=50)
    rccm: Optional[str] = Field(None, max_length=60)
    code_marchand: Optional[str] = Field(None, max_length=12)
    actif: Optional[bool] = None
    mise_en_avant: Optional[bool] = None  # affichée en tête du carrousel
    ordre: Optional[int] = None


def _normaliser_code(code: str) -> str:
    code = re.sub(r"[^A-Za-z0-9]", "", code or "").upper()
    if len(code) < 3:
        raise HTTPException(400, "Le code marchand doit contenir au moins 3 lettres ou chiffres")
    return code


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
    code = _normaliser_code(payload.code_marchand) if payload.code_marchand else await _code_marchand_unique()
    if await db.boutiques.find_one({"code_marchand": code}):
        raise HTTPException(409, "Ce code marchand est déjà utilisé")
    boutique = {
        "id": new_id(), "nom": payload.nom.strip(), "slug": await _slug_unique(payload.nom),
        "code_marchand": code, "telephone": normaliser_telephone(payload.telephone), "email": payload.email or "",
        "actif": True, "mise_en_avant": False, "ordre": 0, "created_at": now_iso(),
        **boutique_par_defaut(payload.nom.strip()),
        **Identification(**payload.model_dump(include=set(Identification.model_fields))).model_dump(),
    }
    await db.boutiques.insert_one(boutique.copy())
    dg = {
        "id": new_id(), "email": payload.dg_email.lower(), "nom": payload.dg_nom.strip(),
        "password_hash": hash_password(payload.dg_mot_de_passe), "role": "dg",
        "boutique_id": boutique["id"], "actif": True, "created_at": now_iso(),
    }
    await db.users.insert_one(dg.copy())
    # Première initialisation : la boutique reçoit tout le catalogue public (sans prix)
    from catalogue_public import copier_catalogue_dans_boutique
    nb_produits = await copier_catalogue_dans_boutique(boutique["id"])
    return {"boutique": _sans_secrets(boutique), "dg": user_public(dg), "produits_copies": nb_produits}


@router.patch("/boutiques/{boutique_id}")
async def modifier_boutique(boutique_id: str, payload: BoutiqueMaj, _: dict = Depends(get_super_admin)):
    boutique = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not boutique:
        raise HTTPException(404, "Boutique introuvable")
    maj = payload.model_dump(exclude_none=True)
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
