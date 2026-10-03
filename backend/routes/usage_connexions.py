"""Onglet « Usage » de l'espace plateforme (lot 25) — règles : voir blocages_acces.py.

Super-administrateur UNIQUEMENT (rôle « super_admin » ; 403 pour les DG et le personnel) :
  - GET  /api/plateforme/usage/connexions          : historique des connexions (50 par page,
                                                     plus récentes en haut ; filtres q, boutique,
                                                     du, au, abonnement, etat) ;
  - GET  /api/plateforme/usage/presence?sids=a,b   : pastilles de présence (rafraîchies toutes
                                                     les 30 s par le site, en requête de FOND
                                                     « X-Adlyn-Fond » : ne compte pas comme une
                                                     activité de l'administrateur) ;
  - GET  /api/plateforme/usage/blocages            : blocages en cours ;
  - POST /api/plateforme/usage/blocages            : bloquer une IP (ce compte / tous) ou un compte ;
  - POST /api/plateforme/usage/blocages/{id}/lever : lever un blocage ;
  - POST /api/plateforme/usage/autoriser           : lever tous les blocages d'une IP ou d'un compte ;
  - GET  /api/plateforme/usage/journal             : journal des actions (qui, quand, quoi) ;
  - GET/PUT /api/plateforme/usage/contact          : contact affiché sur la page de blocage.
Public (sans connexion) :
  - GET  /api/acces-suspendu/contact               : contact affiché sur la page « Accès
                                                     momentanément suspendu ».
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

import abonnements
import blocages_acces as service
from auth import get_super_admin
from db import SANS_ID, db

admin = APIRouter(prefix="/plateforme/usage", tags=["Usage (super-admin)"])
public = APIRouter(tags=["Accès suspendu"])

PAR_PAGE = 50

# États d'abonnement montrés dans l'onglet (filtre et badge)
ETATS_ABONNEMENT = ("actif", "grace", "expire", "aucun")

ROLES = {"super_admin": "Super-administrateur", "dg": "DG", "commercial": "Commercial",
         "secretaire": "Secrétaire", "comptable": "Comptable", "technicien": "Technicien"}


class Blocage(BaseModel):
    """Demande de blocage envoyée par l'onglet « Usage »."""
    type: Literal["ip", "compte"]
    ip: Optional[str] = Field(None, max_length=64)
    user_id: Optional[str] = Field(None, max_length=64)
    tous_comptes: bool = True              # IP : bloquée pour tous les comptes (case cochée par défaut)
    libelle: Optional[str] = Field(None, max_length=120)  # nom facultatif du site (ex. « Cybercafé X »)
    motif: Optional[str] = Field(None, max_length=300)    # motif interne, jamais montré


class Autorisation(BaseModel):
    type: Literal["ip", "compte"]
    ip: Optional[str] = Field(None, max_length=64)
    user_id: Optional[str] = Field(None, max_length=64)


class Contact(BaseModel):
    email: Optional[str] = Field(None, max_length=200)
    whatsapp: Optional[str] = Field(None, max_length=40)


# ---------------------------------------------------------------------------
# État de l'abonnement d'une boutique, ramené à 4 cas lisibles
# ---------------------------------------------------------------------------
def resume_abonnement(etat: Optional[dict]) -> dict:
    """Situation calculée par abonnements.etat -> {statut, libelle, formule}.
    statut : « actif » (essai compris), « grace », « expire » (ou suspendu), « aucun »."""
    if not etat:
        return {"statut": "aucun", "libelle": "Aucun", "formule": None}
    formule = "Essai gratuit" if etat.get("en_essai") else (etat.get("formule_libelle") or None)
    statut = etat.get("statut")
    grace = etat.get("grace") or {}
    if statut == "SUSPENDU":
        return {"statut": "expire", "libelle": "Suspendu", "formule": formule}
    if statut == "EN_RETARD":
        if grace.get("en_grace"):
            return {"statut": "grace", "libelle": f"Période de grâce ({grace.get('jours_grace_restants', 0)} j)",
                    "formule": formule}
        return {"statut": "expire", "libelle": "Expiré", "formule": formule}
    libelle = {"ESSAI": "Actif (essai)", "A_RENOUVELER": "Actif (à renouveler)"}.get(statut, "Actif")
    return {"statut": "actif", "libelle": libelle, "formule": formule}


async def _abonnements_boutiques(ids: list[str]) -> dict[str, dict]:
    """boutique_id -> {nom, code, abonnement résumé} pour une liste de boutiques."""
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    tarifs = {f["code"]: f for f in await abonnements.formules(False)}
    resultat = {}
    for b in await db.boutiques.find({"id": {"$in": ids}}, SANS_ID).to_list(len(ids)):
        resultat[b["id"]] = {"nom": b.get("nom"), "code": b.get("code_marchand"),
                             "abonnement": resume_abonnement(await abonnements.etat(b, tarifs))}
    return resultat


# ---------------------------------------------------------------------------
# Historique des connexions
# ---------------------------------------------------------------------------
@admin.get("/connexions")
async def connexions(
    q: str = Query("", max_length=100),
    boutique: str = Query("", max_length=100),
    du: str = Query("", max_length=10),
    au: str = Query("", max_length=10),
    abonnement: str = Query("", max_length=10),
    etat: str = Query("", max_length=10),
    page: int = Query(1, ge=1, le=10_000),
    _: dict = Depends(get_super_admin),
):
    # --- 1. Filtre MongoDB (période, état, compte / IP, boutique) ---
    conditions: list[dict] = []
    debut, fin = service.borne_jour(du or None), service.borne_jour(au or None, fin=True)
    if debut or fin:
        conditions.append({"date": {k: v for k, v in (("$gte", debut), ("$lt", fin)) if v}})
    if etat in ("reussie", "refusee"):
        conditions.append({"etat": etat})
    if q.strip():
        motif = {"$regex": re.escape(q.strip()), "$options": "i"}
        ids = await db.users.distinct("id", {"$or": [{"nom": motif}, {"email": motif}, {"telephone": motif}]})
        conditions.append({"$or": [{"ip": motif}, {"identifiant": motif}, {"user_id": {"$in": ids}}]})
    if boutique.strip():
        motif = {"$regex": re.escape(boutique.strip()), "$options": "i"}
        ids = await db.boutiques.distinct("id", {"$or": [{"nom": motif}, {"code_marchand": motif}]})
        conditions.append({"boutique_id": {"$in": ids}})
    # État de l'abonnement : calculé (pas stocké) -> on retient les boutiques qui conviennent
    if abonnement in ETATS_ABONNEMENT:
        filtre_partiel = {"$and": conditions} if conditions else {}
        presentes = [b for b in await db.usage_connexions.distinct("boutique_id", filtre_partiel) if b]
        infos = await _abonnements_boutiques(presentes)
        retenues = [bid for bid, i in infos.items() if i["abonnement"]["statut"] == abonnement]
        if abonnement == "aucun":
            # Comptes sans boutique (super-administrateur, demandes refusées) : « aucun »
            conditions.append({"$or": [{"boutique_id": {"$in": retenues}}, {"boutique_id": None}]})
        else:
            conditions.append({"boutique_id": {"$in": retenues}})
    filtre = {"$and": conditions} if conditions else {}

    # --- 2. Page demandée (50 lignes, plus récentes en haut) ---
    total = await db.usage_connexions.count_documents(filtre)
    lignes = await db.usage_connexions.find(filtre, SANS_ID).sort("date", -1) \
        .skip((page - 1) * PAR_PAGE).limit(PAR_PAGE).to_list(PAR_PAGE)

    # --- 3. Compléments : comptes, boutiques et abonnements, blocages, présence ---
    uids = list({ligne["user_id"] for ligne in lignes if ligne.get("user_id")})
    comptes = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": uids}},
        {"_id": 0, "id": 1, "nom": 1, "email": 1, "telephone": 1, "role": 1, "boutique_id": 1}).to_list(len(uids) or 1)}
    boutiques = await _abonnements_boutiques([ligne.get("boutique_id") for ligne in lignes])
    blocages = await service.blocages_actifs(cache=False)
    presence = await service.presence_sessions([ligne.get("sid") for ligne in lignes if ligne.get("sid")])

    items = []
    for ligne in lignes:
        uid = ligne.get("user_id")
        compte = comptes.get(uid)
        b = boutiques.get(ligne.get("boutique_id"))
        role = (compte or {}).get("role") or ligne.get("role") or ""
        items.append({
            "id": ligne["id"], "date": ligne["date"], "ip": ligne.get("ip"), "etat": ligne.get("etat"),
            "motif": ligne.get("motif"), "methode": ligne.get("methode"),
            "methode_libelle": service.METHODES.get(ligne.get("methode"), ligne.get("methode")),
            "appareil": ligne.get("appareil"), "sid": ligne.get("sid"), "identifiant": ligne.get("identifiant"),
            "role": role, "role_libelle": ROLES.get(role, role or "—"),
            "compte": {"id": compte["id"], "nom": compte.get("nom"),
                       "identifiant": compte.get("email") or compte.get("telephone"),
                       "super_admin": compte.get("role") == "super_admin"} if compte else None,
            "boutique": {"id": ligne.get("boutique_id"), "nom": b["nom"], "code": b["code"]} if b else None,
            # Pas de boutique (super-administrateur, demande refusée) : aucun abonnement
            "abonnement": b["abonnement"] if b else resume_abonnement(None),
            "ip_etat": service.etat_ip(blocages, uid, ligne.get("ip")),
            "compte_bloque": service.compte_bloque(blocages, uid),
            "presence": presence.get(ligne.get("sid")) or service.couleur_presence(None),
        })
    return {"items": items, "total": total, "page": page, "par_page": PAR_PAGE,
            "pages": max(1, -(-total // PAR_PAGE))}


@admin.get("/presence")
async def presence(sids: str = Query("", max_length=20_000), _: dict = Depends(get_super_admin)):
    """Pastilles de présence d'une liste de sessions (identifiants séparés par des virgules)."""
    return {"presence": await service.presence_sessions([s.strip() for s in sids.split(",") if s.strip()])}


# ---------------------------------------------------------------------------
# Blocages
# ---------------------------------------------------------------------------
@admin.get("/blocages")
async def blocages_en_cours(_: dict = Depends(get_super_admin)):
    liste = await db.usage_blocages.find({"actif": True}, SANS_ID).sort("cree_le", -1).to_list(1000)
    return {"blocages": liste}


@admin.post("/blocages")
async def creer_blocage(data: Blocage, request: Request, adm: dict = Depends(get_super_admin)):
    return await service.bloquer(adm, request, type_=data.type, ip=data.ip, user_id=data.user_id,
                                 tous_comptes=data.tous_comptes, libelle=data.libelle, motif=data.motif)


@admin.post("/blocages/{blocage_id}/lever")
async def lever_blocage(blocage_id: str, adm: dict = Depends(get_super_admin)):
    return await service.lever(adm, blocage_id)


@admin.post("/autoriser")
async def autoriser(data: Autorisation, adm: dict = Depends(get_super_admin)):
    n = await service.autoriser(adm, type_=data.type, ip=data.ip, user_id=data.user_id)
    return {"ok": True, "leves": n}


@admin.get("/journal")
async def journal_actions(_: dict = Depends(get_super_admin)):
    return {"actions": await db.usage_blocages_journal.find({}, SANS_ID).sort("date", -1).to_list(100)}


@admin.get("/contact")
async def lire_contact(_: dict = Depends(get_super_admin)):
    return await service.lire_contact()


@admin.put("/contact")
async def regler_contact(data: Contact, adm: dict = Depends(get_super_admin)):
    return await service.regler_contact(adm, data.email, data.whatsapp)


@public.get("/acces-suspendu/contact")
async def contact_public():
    """Contact de la plateforme pour la page « Accès momentanément suspendu »
    (vide = le site affiche le contact officiel des pages légales)."""
    return await service.lire_contact()
