"""Administration de la PLATEFORME (super-administrateur uniquement) :
création des boutiques (tenants) et de leur premier compte gérant."""
from __future__ import annotations

import re
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

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


class BoutiqueCreation(BaseModel):
    nom: str = Field(..., min_length=2, max_length=120)
    ville: str = ""
    telephone: str = ""
    email: Optional[EmailStr] = None
    code_marchand: Optional[str] = Field(None, max_length=12)
    # Premier compte gérant de la boutique
    gerant_nom: str = Field(..., min_length=2)
    gerant_email: EmailStr
    gerant_mot_de_passe: str = Field(..., min_length=8)


class BoutiqueMaj(BaseModel):
    nom: Optional[str] = Field(None, min_length=2, max_length=120)
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
        "slogan": "", "adresse": "", "ifu": "", "rccm": "", "logo_url": None,
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
    if await db.users.find_one({"email": payload.gerant_email.lower()}):
        raise HTTPException(409, "Un compte existe déjà avec l'e-mail du gérant")
    code = _normaliser_code(payload.code_marchand) if payload.code_marchand else await _code_marchand_unique()
    if await db.boutiques.find_one({"code_marchand": code}):
        raise HTTPException(409, "Ce code marchand est déjà utilisé")
    boutique = {
        "id": new_id(), "nom": payload.nom.strip(), "slug": await _slug_unique(payload.nom),
        "code_marchand": code, "ville": payload.ville.strip(),
        "telephone": normaliser_telephone(payload.telephone), "email": payload.email or "",
        "actif": True, "mise_en_avant": False, "ordre": 0, "created_at": now_iso(),
        **boutique_par_defaut(payload.nom.strip()),
    }
    await db.boutiques.insert_one(boutique.copy())
    gerant = {
        "id": new_id(), "email": payload.gerant_email.lower(), "nom": payload.gerant_nom.strip(),
        "password_hash": hash_password(payload.gerant_mot_de_passe), "role": "gerant",
        "boutique_id": boutique["id"], "actif": True, "created_at": now_iso(),
    }
    await db.users.insert_one(gerant.copy())
    return {"boutique": _sans_secrets(boutique), "gerant": user_public(gerant)}


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
