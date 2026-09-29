"""Abonnements adLyn : page « Abonnement » du DG (état, paiement en ligne) et
administration par le super-administrateur (retards, suspension, paiements
reçus, formules, rappels)."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import abonnements as service
import parrainage
from auth import Contexte, contexte_abonnement, get_super_admin
from db import SANS_ID, db
from routes.paiements import creer_page_abonnement, paiement_disponible
from utils import new_id

boutique = APIRouter(prefix="/boutique/abonnement", tags=["Abonnement (DG)"])
admin = APIRouter(prefix="/plateforme/abonnements", tags=["Abonnements (super-admin)"])


# ---------------------------------------------------------------------------
# Côté boutique (DG) — accessible même quand la boutique est suspendue
# ---------------------------------------------------------------------------
@boutique.get("")
async def mon_abonnement(ctx: Contexte = Depends(contexte_abonnement)):
    """État de l'abonnement, formules proposées et historique des paiements."""
    paiements = await db.abonnement_paiements.find(
        {"boutique_id": ctx.boutique["id"], "statut": "VALIDE"}, SANS_ID).sort("created_at", -1).to_list(100)
    return {"etat": await service.etat(ctx.boutique), "formules": await service.formules(),
            "paiements": paiements, "paiement_en_ligne": paiement_disponible(),
            # Bonus de parrainage déductibles de l'abonnement
            "bonus": await parrainage.solde(ctx.boutique["id"])}


class DemandePaiement(BaseModel):
    formule: str = Field(..., max_length=40)
    telephone: str = Field("", max_length=30)  # numéro Mobile Money (prérempli sur la page PawaPay)
    utiliser_bonus: bool = False  # déduire les bonus de parrainage disponibles


@boutique.post("/payer")
async def payer(payload: DemandePaiement, ctx: Contexte = Depends(contexte_abonnement)):
    """Page de paiement Mobile Money (PawaPay) pour la formule choisie. Le montant
    vient TOUJOURS de la formule enregistrée, jamais du navigateur."""
    f = await service.formule(payload.formule)
    if not f or not f.get("actif") or int(f.get("montant", 0)) <= 0:
        raise HTTPException(400, "Formule indisponible")
    # Bonus de parrainage : jamais plus que le prix de la formule (calculé côté serveur)
    bonus = await parrainage.deduction_possible(ctx.boutique["id"], int(f["montant"])) if payload.utiliser_bonus else 0
    if bonus >= int(f["montant"]):
        # Renouvellement entièrement payé par les bonus : pas de paiement en ligne
        reference = f"bonus-{new_id()}"
        if not await parrainage.utiliser(ctx.boutique["id"], bonus, reference=reference,
                                         libelle=f"Abonnement {f['libelle']}"):
            raise HTTPException(409, "Vos bonus de parrainage ont changé : rechargez la page")
        paiement = await service.enregistrer_paiement(
            ctx.boutique["id"], f["code"], 0, "BONUS_PARRAINAGE", reference=reference,
            saisi_par="Bonus de parrainage", cle=reference, bonus_deduit=bonus)
        return {"paye_par_bonus": True, "paiement": paiement}
    return {"url": await creer_page_abonnement(ctx.boutique, f, payload.telephone, bonus_deduit=bonus)}


# ---------------------------------------------------------------------------
# Super-administrateur
# ---------------------------------------------------------------------------
async def _liste() -> list[dict]:
    """Toutes les boutiques avec la situation de leur abonnement."""
    tarifs = {f["code"]: f for f in await service.formules(False)}
    resultat = []
    async for b in db.boutiques.find({}, SANS_ID).sort("nom", 1):
        resultat.append({"id": b["id"], "nom": b["nom"], "code_marchand": b.get("code_marchand", ""),
                         "ville": b.get("ville", ""), "dg_nom": b.get("dg_nom", ""),
                         "telephone": b.get("dg_telephone") or b.get("telephone", ""),
                         "created_at": b.get("created_at"), "abonnement": await service.etat(b, tarifs)})
    return resultat


@admin.get("")
async def toutes(_: dict = Depends(get_super_admin)):
    boutiques = await _liste()
    compte = {code: sum(1 for b in boutiques if b["abonnement"]["statut"] == code) for code in service.STATUTS}
    return {"boutiques": boutiques, "compte": compte, "statuts": service.STATUTS}


@admin.get("/retards")
async def retards(_: dict = Depends(get_super_admin)):
    """Boutiques dont l'échéance est dépassée (y compris celles déjà suspendues),
    les plus en retard d'abord, avec le montant attendu."""
    lignes = [b for b in await _liste() if b["abonnement"]["jours_retard"] > 0]
    lignes.sort(key=lambda b: -b["abonnement"]["jours_retard"])
    a_suspendre = [b for b in lignes if b["abonnement"]["statut"] == "EN_RETARD"]
    return {"boutiques": lignes, "total_attendu": sum(b["abonnement"]["montant_attendu"] for b in lignes),
            "nb_a_traiter": len(a_suspendre)}


class Selection(BaseModel):
    boutique_ids: list[str] = Field(..., min_length=1, max_length=500)


@admin.post("/suspendre")
async def suspendre(payload: Selection, adm: dict = Depends(get_super_admin)):
    """Suspend l'accès des boutiques choisies dans la liste des retards (motif : impayé).
    Leur DG garde l'accès à la page Abonnement pour régler et retrouver l'accès."""
    n = 0
    for bid in dict.fromkeys(payload.boutique_ids):
        n += await service.suspendre(bid, "IMPAYE", adm.get("email", ""))
    return {"suspendues": n}


@admin.post("/reactiver")
async def reactiver(payload: Selection, _: dict = Depends(get_super_admin)):
    """Rend l'accès sans paiement (ex. promesse de paiement, geste commercial)."""
    res = await db.boutiques.update_many({"id": {"$in": payload.boutique_ids}},
                                         {"$set": {"actif": True, "suspension": None}})
    return {"reactivees": res.modified_count}


class PaiementSaisi(BaseModel):
    formule: str = Field(..., max_length=40)
    montant: Optional[int] = Field(None, ge=0)  # vide = prix de la formule
    mode: Literal["MOBILE_MONEY", "ESPECES", "VIREMENT", "CHEQUE", "OFFERT"] = "MOBILE_MONEY"
    reference: str = Field("", max_length=120)
    date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    utiliser_bonus: bool = False  # déduire les bonus de parrainage de la boutique


@admin.post("/boutiques/{boutique_id}/paiements", status_code=201)
async def saisir_paiement(boutique_id: str, payload: PaiementSaisi, adm: dict = Depends(get_super_admin)):
    """Paiement reçu hors du site (espèces, transfert...) : prolonge l'abonnement."""
    f = await service.formule(payload.formule)
    if not f:
        raise HTTPException(400, "Formule inconnue")
    bonus = await parrainage.deduction_possible(boutique_id, int(f["montant"])) if payload.utiliser_bonus else 0
    montant = int(f["montant"]) - bonus if payload.montant is None else payload.montant
    cle = new_id()
    if bonus and not await parrainage.utiliser(boutique_id, bonus, reference=f"admin-{cle}",
                                               libelle=f"Abonnement {f['libelle']} (saisi par l'administrateur)"):
        raise HTTPException(409, "Bonus de parrainage insuffisants")
    try:
        return await service.enregistrer_paiement(boutique_id, f["code"], montant, payload.mode,
                                                  reference=payload.reference, saisi_par=adm.get("email", ""),
                                                  date_paiement=payload.date, cle=cle, bonus_deduit=bonus)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


class Ajustement(BaseModel):
    echeance: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    formule: Optional[str] = Field(None, max_length=40)


@admin.patch("/boutiques/{boutique_id}")
async def ajuster(boutique_id: str, payload: Ajustement, _: dict = Depends(get_super_admin)):
    """Correction manuelle : nouvelle échéance (ex. essai prolongé) ou formule par défaut."""
    b = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    ab = b.get("abonnement") or service.abonnement_initial(b.get("created_at"))
    if payload.echeance:
        date.fromisoformat(payload.echeance)  # date valide
        ab["echeance"] = payload.echeance
        if ab.get("en_essai"):
            ab["fin_essai"] = payload.echeance
    if payload.formule:
        if not await service.formule(payload.formule):
            raise HTTPException(400, "Formule inconnue")
        ab["formule"] = payload.formule
    await db.boutiques.update_one({"id": boutique_id}, {"$set": {"abonnement": ab}})
    return await service.etat(await db.boutiques.find_one({"id": boutique_id}, SANS_ID))


@admin.get("/paiements")
async def paiements(debut: str = "", fin: str = "", _: dict = Depends(get_super_admin)):
    """Paiements d'abonnement reçus sur une période (dates AAAA-MM-JJ incluses)."""
    filtre: dict = {"statut": "VALIDE"}
    if debut or fin:
        filtre["date"] = {k: v for k, v in (("$gte", debut), ("$lte", fin)) if v}
    lignes = await db.abonnement_paiements.find(filtre, SANS_ID).sort("created_at", -1).to_list(2000)
    return {"paiements": lignes, "total": sum(p["montant"] for p in lignes), "modes": service.MODES_PAIEMENT}


# --- Formules ---
class FormuleSaisie(BaseModel):
    libelle: str = Field(..., min_length=2, max_length=60)
    mois: int = Field(..., ge=1, le=60)
    montant: int = Field(..., ge=0)
    actif: bool = True
    ordre: int = 0


@admin.get("/formules")
async def lister_formules(_: dict = Depends(get_super_admin)):
    return await service.formules(False)


@admin.post("/formules", status_code=201)
async def creer_formule(payload: FormuleSaisie, _: dict = Depends(get_super_admin)):
    code = f"F{payload.mois}M-{new_id()[:4].upper()}"
    formule = {"id": new_id(), "code": code, **payload.model_dump()}
    await db.formules.insert_one(formule.copy())
    return formule


@admin.put("/formules/{code}")
async def modifier_formule(code: str, payload: FormuleSaisie, _: dict = Depends(get_super_admin)):
    """Un nouveau prix vaut pour les prochains paiements (les paiements passés ne changent pas)."""
    res = await db.formules.update_one({"code": code}, {"$set": payload.model_dump()})
    if not res.matched_count:
        raise HTTPException(404, "Formule introuvable")
    return await service.formule(code)


# --- Rappels ---
@admin.get("/rappels")
async def journal_rappels(_: dict = Depends(get_super_admin)):
    return await db.abonnement_rappels_journal.find({}, SANS_ID).sort("date", -1).to_list(300)


@admin.post("/rappels/envoyer")
async def envoyer_maintenant(_: dict = Depends(get_super_admin)):
    """Envoie tout de suite les rappels du jour (ceux déjà partis aujourd'hui ne sont pas renvoyés)."""
    return {"envoyes": await service.envoyer_rappels("manuel")}
