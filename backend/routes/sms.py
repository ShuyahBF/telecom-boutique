"""Service SMS des boutiques : envois et journal par contact (boutique),
configuration, facturation et suspension (super-administrateur)."""
from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import sms_boutiques as service
from auth import Contexte, contexte_abonnement, get_super_admin, permission
from db import SANS_ID, db
from routes.paiements import creer_page_facture_sms
from utils import now_iso

boutique = APIRouter(prefix="/boutique/sms", tags=["SMS (boutique)"])
admin = APIRouter(prefix="/plateforme/sms", tags=["SMS (super-admin)"])
messagerie = permission("messagerie")


# ---------------------------------------------------------------------------
# Boutique : état, envoi, journal par contact
# ---------------------------------------------------------------------------
@boutique.get("")
async def etat(ctx: Contexte = Depends(messagerie)):
    """État du service, et SMS facturables du mois en cours (pas encore facturés)."""
    mois = now_iso()[:7]
    envoyes = await db.sms_envois.find({"boutique_id": ctx.boutique["id"], "statut": "ENVOYE", "facture_id": None,
                                        "jour": {"$regex": f"^{mois}"}}, {"_id": 0, "nb_sms": 1}).to_list(None)
    e = service.etat(ctx.boutique)
    nb = sum(x.get("nb_sms", 0) for x in envoyes)
    return {**e, "mois_nb_sms": nb, "mois_montant": nb * e["prix_sms"]}


class NouveauSms(BaseModel):
    telephone: str = Field(..., min_length=8, max_length=30)
    texte: str = Field(..., min_length=1, max_length=918)
    contact_nom: str = Field("", max_length=120)


@boutique.post("/envoyer", status_code=201)
async def envoyer(payload: NouveauSms, ctx: Contexte = Depends(messagerie)):
    if not service.peut_envoyer(ctx.boutique):
        raise HTTPException(403, service.etat(ctx.boutique)["libelle"])
    return await service.envoyer(ctx.boutique, payload.telephone, payload.texte, origine="MANUEL",
                                 contact_nom=payload.contact_nom, auteur=ctx.user.get("nom", ""))


@boutique.get("/contacts")
async def contacts(q: str = "", ctx: Contexte = Depends(messagerie)):
    return await service.contacts(ctx.boutique["id"], q)


@boutique.get("/contacts/{telephone}")
async def messages(telephone: str, ctx: Contexte = Depends(messagerie)):
    return await service.messages_du_contact(ctx.boutique["id"], telephone)


# Factures du service SMS : DG, même si la boutique est suspendue (pour payer)
@boutique.get("/factures")
async def mes_factures(ctx: Contexte = Depends(contexte_abonnement)):
    return await service.factures(ctx.boutique["id"])


class PaiementFacture(BaseModel):
    telephone: str = Field("", max_length=30)


@boutique.post("/factures/{facture_id}/payer")
async def payer(facture_id: str, payload: PaiementFacture, ctx: Contexte = Depends(contexte_abonnement)):
    """Paiement Mobile Money d'une facture SMS ; le montant vient de la facture enregistrée."""
    f = await db.sms_factures.find_one({"id": facture_id, "boutique_id": ctx.boutique["id"]}, SANS_ID)
    if not f or f["statut"] != "A_PAYER":
        raise HTTPException(400, "Facture introuvable ou déjà payée")
    return {"url": await creer_page_facture_sms(ctx.boutique, f, payload.telephone)}


# ---------------------------------------------------------------------------
# Super-administrateur
# ---------------------------------------------------------------------------
@admin.get("/boutiques")
async def boutiques(_: dict = Depends(get_super_admin)):
    """Chaque boutique : configuration du service, SMS non encore facturés, factures dues."""
    a_payer = await service.factures(statut="A_PAYER")
    resultat = []
    async for b in db.boutiques.find({}, SANS_ID).sort("nom", 1):
        non_factures = await db.sms_envois.find({"boutique_id": b["id"], "statut": "ENVOYE", "facture_id": None},
                                                {"_id": 0, "nb_sms": 1}).to_list(None)
        dues = [f for f in a_payer if f["boutique_id"] == b["id"]]
        c = service.config(b)
        resultat.append({
            "id": b["id"], "nom": b["nom"], "code_marchand": b.get("code_marchand", ""), "service": service.etat(b),
            "service_ovh": c.get("service_ovh", ""), "actif": c.get("actif", True),
            "sms_non_factures": sum(x.get("nb_sms", 0) for x in non_factures),
            "montant_du": sum(f["montant"] for f in dues), "retard_max": max([f["jours_retard"] for f in dues], default=0),
        })
    return resultat


class ConfigSms(BaseModel):
    # Nom d'expéditeur déclaré chez OVH : 3 à 11 lettres/chiffres (norme des expéditeurs SMS)
    expediteur: str = Field(..., min_length=3, max_length=11)
    service_ovh: str = Field("", max_length=60)  # vide = service OVH de la plateforme
    prix_sms: int = Field(..., ge=0, le=1000)
    notifications_auto: bool = True
    actif: bool = True


@admin.put("/boutiques/{boutique_id}")
async def configurer(boutique_id: str, payload: ConfigSms, adm: dict = Depends(get_super_admin)):
    """Configuration du service SMS d'une boutique (faite une fois, modifiable par le super-admin seul)."""
    if not re.fullmatch(r"[A-Za-z0-9]{3,11}", payload.expediteur):
        raise HTTPException(400, "L'expéditeur doit contenir 3 à 11 lettres ou chiffres, sans espace")
    b = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    actuel = service.config(b)
    nouvelle = {**actuel, **payload.model_dump(), "service_ovh": payload.service_ovh.strip(),
                "configure_le": actuel.get("configure_le") or now_iso(), "configure_par": adm.get("email", ""),
                "suspendu": actuel.get("suspendu", False), "motif": actuel.get("motif")}
    await db.boutiques.update_one({"id": boutique_id}, {"$set": {"sms": nouvelle}})
    return service.etat(await db.boutiques.find_one({"id": boutique_id}, SANS_ID))


@admin.get("/boutiques/{boutique_id}/contacts")
async def contacts_boutique(boutique_id: str, q: str = "", _: dict = Depends(get_super_admin)):
    return await service.contacts(boutique_id, q)


@admin.get("/boutiques/{boutique_id}/contacts/{telephone}")
async def messages_boutique(boutique_id: str, telephone: str, _: dict = Depends(get_super_admin)):
    return await service.messages_du_contact(boutique_id, telephone)


class Periode(BaseModel):
    debut: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    fin: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    boutique_id: Optional[str] = None  # vide = toutes les boutiques


@admin.post("/factures/generer", status_code=201)
async def generer(payload: Periode, adm: dict = Depends(get_super_admin)):
    if payload.fin < payload.debut:
        raise HTTPException(400, "La fin de période est avant son début")
    return await service.facturer(payload.debut, payload.fin, payload.boutique_id, adm.get("email", ""))


@admin.get("/factures")
async def lister(statut: str = "", boutique_id: str = "", _: dict = Depends(get_super_admin)):
    return await service.factures(boutique_id or None, statut)


class PaiementSaisi(BaseModel):
    mode: Literal["MOBILE_MONEY", "ESPECES", "VIREMENT", "CHEQUE", "OFFERT"] = "MOBILE_MONEY"
    reference: str = Field("", max_length=120)


@admin.post("/factures/{facture_id}/paiements")
async def saisir_paiement(facture_id: str, payload: PaiementSaisi, adm: dict = Depends(get_super_admin)):
    f = await service.payer_facture(facture_id, payload.mode, reference=payload.reference, saisi_par=adm.get("email", ""))
    if not f:
        raise HTTPException(404, "Facture introuvable")
    return f


@admin.get("/retards")
async def retards(_: dict = Depends(get_super_admin)):
    lignes = await service.retards()
    return {"boutiques": lignes, "total_du": sum(g["montant_du"] for g in lignes)}


class Selection(BaseModel):
    boutique_ids: list[str] = Field(..., min_length=1, max_length=500)


@admin.post("/suspendre")
async def suspendre(payload: Selection, _: dict = Depends(get_super_admin)):
    """Suspend le SEUL service SMS des boutiques choisies (le reste de la boutique continue)."""
    return {"suspendues": await service.suspendre(payload.boutique_ids)}


@admin.post("/reactiver")
async def reactiver(payload: Selection, _: dict = Depends(get_super_admin)):
    return {"reactivees": await service.reactiver(payload.boutique_ids)}
