"""« Encaissement PI-SPI » de la boutique (Paramètres, réservé au gérant) et route de
notification de paiement (prévue, DÉSACTIVÉE tant qu'aucun connecteur bancaire n'existe).

Paramètres (champ `pispi` de la fiche boutique) : actif, banque (+ libellé si « Autre »),
titulaire, adresse de paiement (alias PI-SPI), QR fourni par la banque (texte décodé OU
image PNG/JPG de 1 Mo au plus) et consigne imprimée sous le QR. Ces données ne sont pas
secrètes (elles sont faites pour être imprimées sur les factures), mais seul le gérant
(permission « parametres ») peut les modifier. Voir pispi_connecteur.py.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

import pispi_connecteur as pispi
from auth import Contexte, permission
from db import SANS_ID, db
from storage import enregistrer_image, supprimer_image
from utils import now_iso

boutique = APIRouter(prefix="/boutique/pispi", tags=["Encaissement PI-SPI"])
public = APIRouter(prefix="/pispi", tags=["Encaissement PI-SPI"])
parametres = permission("parametres")

QR_IMAGE_MAX = 1024 * 1024  # 1 Mo
QR_TYPES = {"image/png", "image/jpeg"}


class ParametresPispi(BaseModel):
    actif: bool = False
    banque: Literal["UBA", "BSIC", "IB Bank", "Ecobank", "Autre"] = "UBA"
    banque_libelle: str = Field("", max_length=80)  # nom de la banque si « Autre »
    titulaire: str = Field("", max_length=120)
    adresse_paiement: str = Field("", max_length=200)
    qr_contenu: str = Field("", max_length=1500)  # texte décodé du QR de la banque, recopié TEL QUEL
    consigne: str = Field("", max_length=300)


def _etat(b: dict) -> dict:
    """Paramètres enregistrés + informations utiles à l'écran."""
    p = b.get("pispi") or {}
    connecteur = pispi.connecteur_actif()
    return {**ParametresPispi().model_dump(), "qr_image_url": None, **p,
            "consigne_defaut": pispi.CONSIGNE_DEFAUT, "banques": list(pispi.BANQUES),
            "connecteur": {"code": connecteur.code, "libelle": connecteur.libelle},
            "imprimable": pispi.bloc_impression(b) is not None}


@boutique.get("")
async def lire(ctx: Contexte = Depends(parametres)):
    return _etat(ctx.boutique)


@boutique.put("")
async def enregistrer(payload: ParametresPispi, ctx: Contexte = Depends(parametres)):
    donnees = {k: (v.strip() if isinstance(v, str) else v) for k, v in payload.model_dump().items()}
    if donnees["banque"] == "Autre" and not donnees["banque_libelle"]:
        raise HTTPException(400, "Indiquez le nom de la banque")
    actuel = ctx.boutique.get("pispi") or {}
    if donnees["actif"] and not (donnees["qr_contenu"] or actuel.get("qr_image_url")):
        raise HTTPException(400, "Ajoutez le QR code fourni par votre banque (texte ou image) avant d'activer")
    # L'image du QR (téléversée à part) est conservée
    maj = {**donnees, "qr_image_url": actuel.get("qr_image_url"), "modifie_le": now_iso(),
           "modifie_par": ctx.user.get("nom", "")}
    await db.boutiques.update_one({"id": ctx.boutique["id"]}, {"$set": {"pispi": maj}})
    return _etat(await db.boutiques.find_one({"id": ctx.boutique["id"]}, SANS_ID))


@boutique.post("/qr-image")
async def envoyer_qr_image(fichier: UploadFile = File(...), ctx: Contexte = Depends(parametres)):
    """Image du QR code fournie par la banque (PNG ou JPG, 1 Mo au plus), imprimée telle quelle."""
    if fichier.content_type not in QR_TYPES:
        raise HTTPException(400, "Format non accepté : PNG ou JPG")
    contenu = await fichier.read()
    if len(contenu) > QR_IMAGE_MAX:
        raise HTTPException(400, "Image trop lourde (1 Mo au maximum)")
    url = await enregistrer_image(ctx.boutique["id"], "pispi", contenu, fichier.content_type)
    await supprimer_image(ctx.boutique["id"], (ctx.boutique.get("pispi") or {}).get("qr_image_url"))
    await db.boutiques.update_one({"id": ctx.boutique["id"]}, {"$set": {"pispi.qr_image_url": url}})
    return _etat(await db.boutiques.find_one({"id": ctx.boutique["id"]}, SANS_ID))


@boutique.delete("/qr-image")
async def retirer_qr_image(ctx: Contexte = Depends(parametres)):
    await supprimer_image(ctx.boutique["id"], (ctx.boutique.get("pispi") or {}).get("qr_image_url"))
    await db.boutiques.update_one({"id": ctx.boutique["id"]}, {"$set": {"pispi.qr_image_url": None}})
    return _etat(await db.boutiques.find_one({"id": ctx.boutique["id"]}, SANS_ID))


@boutique.get("/transactions")
async def transactions(ctx: Contexte = Depends(parametres)):
    """Encaissements PI-SPI enregistrés (saisis à la main aujourd'hui)."""
    return await ctx.tdb.pispi_transactions.find().sort("date", -1).to_list(500)


@public.post("/notification")
async def notification():
    """Notification de paiement envoyée par une banque : PRÉVUE, mais fermée tant
    qu'aucun connecteur bancaire automatique n'est configuré (aujourd'hui : jamais)."""
    if not pispi.notifications_actives():
        raise HTTPException(503, "Notifications PI-SPI non disponibles : aucun connecteur bancaire configuré "
                                 "(encaissements saisis manuellement)")
    raise HTTPException(501, "Connecteur bancaire non implémenté")


async def enregistrer_transaction(ctx: Contexte, doc: dict, reglement: dict) -> None:
    """Règlement « PISPI » saisi sur une facture -> transaction rapprochée (source manuelle)."""
    await ctx.tdb.pispi_transactions.insert_one({
        "id": reglement["id"], "reference": doc.get("numero") or doc["id"], "montant": reglement["montant"],
        "statut": "rapproche", "date": now_iso(), "date_paiement": reglement.get("date"), "source": "manuel",
        "reference_bancaire": reglement.get("reference", ""), "document_id": doc["id"],
        "document_numero": doc.get("numero"), "saisi_par": reglement.get("saisi_par", ""),
    })


async def rejeter_transaction(ctx: Contexte, reglement_id: str, par: str) -> None:
    """Règlement PISPI supprimé : la transaction passe « rejete » (la trace est gardée)."""
    await ctx.tdb.pispi_transactions.update_one({"id": reglement_id}, {"$set": {
        "statut": "rejete", "rejete_le": now_iso(), "rejete_par": par}})


def bloc_public(b: Optional[dict]) -> Optional[dict]:
    return pispi.bloc_impression(b)
