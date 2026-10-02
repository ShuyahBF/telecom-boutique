"""Cycle de vie du non-renouvellement (logique : cycle_vie.py) et écran « KYC des DG » (kyc_dg.py).

  - Cron Job Render : POST /cycle-vie/declencher (en-tête X-Sauvegarde-Jeton = SAUVEGARDE_AUTO_JETON,
                      comme la sauvegarde générale) : réponse immédiate, tâche de fond, une fois par jour ;
  - super-admin     : GET  /plateforme/cycle-vie              (paramètres, boutiques concernées, archives,
                                                               derniers rapports, alertes)
                      PUT  /plateforme/cycle-vie/parametres   (interrupteur, simulation, conservation, frais)
                      POST /plateforme/cycle-vie/executer     (exécution manuelle ; {"simulation": true} = à blanc)
                      GET  /plateforme/cycle-vie/journal
                      POST /plateforme/cycle-vie/boutiques/{id}/reouvrir
                      GET  /plateforme/kyc-dg                 (?inclure_en_attente=true)
                      POST /plateforme/kyc-dg/rappels         (rappel WhatsApp aux DG sélectionnés)
                      GET  /plateforme/kyc-dg/journal
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header
from pydantic import BaseModel, Field

import cycle_vie as service
import kyc_dg
import sauvegarde_auto
from auth import get_super_admin

cron = APIRouter(prefix="/cycle-vie", tags=["Cycle de vie des boutiques"])
admin = APIRouter(prefix="/plateforme", tags=["Cycle de vie et KYC (super-admin)"])


async def _executer_du_jour(jour) -> None:
    await service.executer(jour, "cron")


@cron.post("/declencher", status_code=202)
async def declencher(taches: BackgroundTasks, x_sauvegarde_jeton: Optional[str] = Header(default=None)):
    """Appelé chaque nuit par le Cron Job (après la sauvegarde générale) ; idempotent sur la journée."""
    sauvegarde_auto.verifier_jeton(x_sauvegarde_jeton)
    jour = service.aujourd_hui()
    if not await service.reserver_jour(jour.isoformat()):
        return {"statut": "DEJA_FAITE", "jour": jour.isoformat()}
    taches.add_task(_executer_du_jour, jour)
    return {"statut": "LANCEE", "jour": jour.isoformat()}


@admin.get("/cycle-vie")
async def etat(_: dict = Depends(get_super_admin)):
    return await service.etat()


class Parametres(BaseModel):
    actif: Optional[bool] = None
    simulation: Optional[bool] = None
    conservation_jours: Optional[int] = None
    frais_montant: Optional[int] = None
    frais_devise: Optional[str] = Field(None, max_length=10)


@admin.put("/cycle-vie/parametres")
async def regler(payload: Parametres, adm: dict = Depends(get_super_admin)):
    return await service.enregistrer_parametres(payload.model_dump(exclude_none=True), adm.get("email", ""))


class Execution(BaseModel):
    simulation: Optional[bool] = None  # None = réglage de la plateforme


@admin.post("/cycle-vie/executer")
async def executer(payload: Execution, _: dict = Depends(get_super_admin)):
    """Exécution immédiate (les étapes déjà faites ne sont jamais refaites)."""
    return await service.executer(None, "manuel-simulation" if payload.simulation else "manuel", payload.simulation)


@admin.get("/cycle-vie/journal")
async def journal(_: dict = Depends(get_super_admin)):
    return await service.journal()


class Reouverture(BaseModel):
    mode: str = Field(..., max_length=30)  # mode de paiement des frais (abonnements.MODES_PAIEMENT)
    montant: int = Field(0, ge=0)  # frais de réouverture encaissés
    reference: str = Field("", max_length=120)
    formule: Optional[str] = Field(None, max_length=30)  # abonnement payé en même temps (facultatif)
    montant_abonnement: int = Field(0, ge=0)


@admin.post("/cycle-vie/boutiques/{boutique_id}/reouvrir")
async def reouvrir(boutique_id: str, payload: Reouverture, adm: dict = Depends(get_super_admin)):
    return await service.reouvrir(boutique_id, mode=payload.mode, montant=payload.montant,
                                  reference=payload.reference, formule=payload.formule, admin=adm,
                                  montant_abonnement=payload.montant_abonnement)


# ---------------------------------------------------------------------------
# KYC des DG
# ---------------------------------------------------------------------------
@admin.get("/kyc-dg")
async def kyc_liste(inclure_en_attente: bool = False, _: dict = Depends(get_super_admin)):
    return {"dg": await kyc_dg.lister(inclure_en_attente), "message_defaut": kyc_dg.MESSAGE_DEFAUT,
            "limite_heures": kyc_dg.LIMITE_HEURES, "etats": kyc_dg.ETATS}


class Rappels(BaseModel):
    boutique_ids: list[str] = Field(..., max_length=kyc_dg.RAPPELS_MAX_PAR_ENVOI)
    message: str = Field("", max_length=1000)


@admin.post("/kyc-dg/rappels")
async def kyc_rappels(payload: Rappels, adm: dict = Depends(get_super_admin)):
    resultats = await kyc_dg.envoyer_rappels(payload.boutique_ids, payload.message, adm)
    return {"resultats": resultats, "envoyes": sum(1 for r in resultats if r["statut"] == "ENVOYE")}


@admin.get("/kyc-dg/journal")
async def kyc_journal(_: dict = Depends(get_super_admin)):
    return await kyc_dg.journal()
