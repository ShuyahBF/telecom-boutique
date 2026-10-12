"""Routes des SECTEURS D'ACTIVITÉ (lot A) — voir secteurs.py.

  - admin (super-administrateur uniquement) : liste complète, création, modification,
    suppression d'un secteur (vocabulaire, champs, modules, catégories de départ) ;
  - public (sans connexion) : liste des secteurs ACTIFS (code, libellé, pictogramme),
    pour le futur formulaire d'inscription libre des boutiques.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import options_sidebar
import secteurs as service
from auth import get_super_admin
from db import SANS_ID, db
from utils import now_iso

admin = APIRouter(prefix="/plateforme/secteurs", tags=["Secteurs d'activité (super-admin)"])
public = APIRouter(prefix="/secteurs", tags=["Secteurs d'activité (public)"])

# Code d'un secteur ou clé d'un champ : minuscules, chiffres et « _ » (ex. pret_a_porter)
_MOTIF_CODE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class ChampSecteur(BaseModel):
    """Un champ propre au secteur (ex. Taille, Date de péremption, ISBN)."""
    cle: str = Field(..., max_length=40)
    libelle: str = Field(..., min_length=1, max_length=80)
    type: Literal["texte", "nombre", "date", "liste", "multi_liste"] = "texte"
    options: list[str] = Field(default_factory=list, max_length=200)
    obligatoire: bool = False


class SecteurSaisie(BaseModel):
    """Contenu modifiable d'un secteur (le code est fixé à la création)."""
    libelle: str = Field(..., min_length=2, max_length=120)
    icone: str = Field("🏪", max_length=8)
    actif: bool = True
    ordre: int = Field(50, ge=0, le=9999)
    vocabulaire: dict[str, str] = Field(default_factory=dict)
    champs: list[ChampSecteur] = Field(default_factory=list, max_length=40)
    modules: list[str] = Field(default_factory=list)
    categories_depart: list[str] = Field(default_factory=list, max_length=50)
    catalogue_telecom: bool = False


class SecteurCreation(SecteurSaisie):
    code: str = Field(..., max_length=40)


def _nettoyer(payload: SecteurSaisie) -> dict:
    """Contrôle et nettoie la saisie : clés de champ uniques et valides, listes avec
    options, modules connus, vocabulaire limité aux termes connus, catégories sans doublon."""
    donnees = payload.model_dump(exclude={"code"})
    champs, vues = [], set()
    for c in payload.champs:
        cle = c.cle.strip()
        if not _MOTIF_CODE.match(cle):
            raise HTTPException(400, f"Clé de champ invalide : « {cle} » (minuscules, chiffres et _ ; ex. date_peremption)")
        if cle in vues:
            raise HTTPException(400, f"Clé de champ en double : {cle}")
        vues.add(cle)
        options = [o.strip() for o in c.options if o.strip()]
        if c.type in ("liste", "multi_liste") and not options:
            raise HTTPException(400, f"Le champ « {c.libelle} » est une liste : indiquez ses valeurs possibles")
        champs.append({"cle": cle, "libelle": c.libelle.strip(), "type": c.type,
                       "options": options if c.type in ("liste", "multi_liste") else [], "obligatoire": c.obligatoire})
    donnees["champs"] = champs
    inconnus = [m for m in payload.modules if m not in options_sidebar.LIBELLES]
    if inconnus:
        raise HTTPException(400, f"Module inconnu : {', '.join(inconnus)}")
    donnees["modules"] = list(dict.fromkeys(payload.modules))
    donnees["vocabulaire"] = {k: v.strip()[:60] for k, v in payload.vocabulaire.items()
                              if k in service.VOCABULAIRE_DEFAUT and v.strip()}
    categories = []
    for nom in payload.categories_depart:
        nom = nom.strip()[:100]
        if nom and nom.lower() not in {c.lower() for c in categories}:
            categories.append(nom)
    donnees["categories_depart"] = categories
    donnees["libelle"] = payload.libelle.strip()
    donnees["icone"] = payload.icone.strip() or "🏪"
    return donnees


async def _avec_compteur(secteur: dict) -> dict:
    """Fiche complète + nombre de boutiques du secteur (aide à la décision avant suppression)."""
    s = service.normaliser(secteur)
    filtre = ({"$or": [{"secteur": s["code"]}, {"secteur": {"$exists": False}}]}
              if s["code"] == service.SECTEUR_DEFAUT else {"secteur": s["code"]})
    s["nb_boutiques"] = await db.boutiques.count_documents(filtre)
    return s


@admin.get("")
async def lister(_: dict = Depends(get_super_admin)):
    """Tous les secteurs (actifs et inactifs) + termes et modules disponibles pour l'éditeur."""
    liste = await db.secteurs.find({}, SANS_ID).sort([("ordre", 1), ("libelle", 1)]).to_list(500)
    return {
        "secteurs": [await _avec_compteur(s) for s in liste],
        "vocabulaire_defaut": service.VOCABULAIRE_DEFAUT,
        "modules": [{"cle": c, "libelle": l, "obligatoire": c in options_sidebar.OPTIONS_OBLIGATOIRES}
                    for c, l in options_sidebar.OPTIONS],
        "types_champ": list(service.TYPES_CHAMP),
    }


@admin.post("", status_code=201)
async def creer(payload: SecteurCreation, admin_: dict = Depends(get_super_admin)):
    code = payload.code.strip().lower()
    if not _MOTIF_CODE.match(code):
        raise HTTPException(400, "Code invalide : minuscules, chiffres et _ (ex. pret_a_porter)")
    if await db.secteurs.find_one({"code": code}, {"_id": 0, "code": 1}):
        raise HTTPException(409, "Ce code de secteur existe déjà")
    doc = {**_nettoyer(payload), "code": code, "created_at": now_iso(), "cree_par": admin_.get("email", "")}
    await db.secteurs.insert_one(doc.copy())
    await service.rafraichir_cache(force=True)
    return await _avec_compteur(doc)


@admin.put("/{code}")
async def modifier(code: str, payload: SecteurSaisie, admin_: dict = Depends(get_super_admin)):
    actuel = await db.secteurs.find_one({"code": code}, SANS_ID)
    if not actuel:
        raise HTTPException(404, "Secteur introuvable")
    maj = {**_nettoyer(payload), "modifie_le": now_iso(), "modifie_par": admin_.get("email", "")}
    if code == service.SECTEUR_DEFAUT and not maj["actif"]:
        raise HTTPException(400, "Le secteur Télécom (secteur par défaut) ne peut pas être désactivé")
    await db.secteurs.update_one({"code": code}, {"$set": maj})
    await service.rafraichir_cache(force=True)
    return await _avec_compteur(await db.secteurs.find_one({"code": code}, SANS_ID))


@admin.delete("/{code}")
async def supprimer(code: str, _: dict = Depends(get_super_admin)):
    """Suppression refusée pour le télécom et pour un secteur encore utilisé
    (le désactiver à la place : il disparaît alors des nouveaux choix)."""
    if code == service.SECTEUR_DEFAUT:
        raise HTTPException(400, "Le secteur Télécom (secteur par défaut) ne peut pas être supprimé")
    if not await db.secteurs.find_one({"code": code}, {"_id": 0, "code": 1}):
        raise HTTPException(404, "Secteur introuvable")
    n = await db.boutiques.count_documents({"secteur": code})
    if n:
        raise HTTPException(409, f"{n} boutique(s) utilisent ce secteur : désactivez-le plutôt")
    await db.secteurs.delete_one({"code": code})
    await service.rafraichir_cache(force=True)
    return {"ok": True}


@public.get("")
async def secteurs_actifs():
    """Secteurs proposés aux commerçants (formulaire d'inscription) : code, libellé, pictogramme."""
    liste = await db.secteurs.find({"actif": {"$ne": False}}, {"_id": 0, "code": 1, "libelle": 1, "icone": 1, "ordre": 1}) \
        .sort([("ordre", 1), ("libelle", 1)]).to_list(500)
    return [{"code": s["code"], "libelle": s.get("libelle") or s["code"], "icone": s.get("icone") or "🏪"} for s in liste]


async def changer_secteur_boutique(boutique_id: str, code: Optional[str]) -> str:
    """Change le secteur d'une boutique (fiche boutique de la plateforme). Seuls le
    vocabulaire et les champs suivent : les modules, catégories et articles déjà en
    place ne sont pas touchés (aucune perte de données)."""
    code = await service.code_valide(code)
    await db.boutiques.update_one({"id": boutique_id}, {"$set": {"secteur": code}})
    return code
