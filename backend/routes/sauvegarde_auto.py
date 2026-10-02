"""Sauvegarde générale automatique (logique : sauvegarde_auto.py).

  - Cron Job Render  : POST /sauvegarde-auto/declencher (en-tête X-Sauvegarde-Jeton), réponse
                       immédiate, travail en tâche de fond, une fois par jour ;
  - super-admin      : GET  /plateforme/sauvegarde-auto (état, alertes, historique, fichiers R2),
                       POST /plateforme/sauvegarde-auto/lancer (sauvegarde du jour, si pas encore faite),
                       POST /plateforme/sauvegarde-auto/restaurer (import « Remplacer » d'un fichier R2) ;
  - tout utilisateur : GET  /auth/sauvegardes/dernieres (« Mon compte » et pied de page).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

import acces
import sauvegarde_auto as service
import transfert_donnees
from auth import get_current_user, get_super_admin

cron = APIRouter(prefix="/sauvegarde-auto", tags=["Sauvegarde générale"])
admin = APIRouter(prefix="/plateforme/sauvegarde-auto", tags=["Sauvegarde générale (super-admin)"])
compte = APIRouter(prefix="/auth", tags=["Authentification"])


async def _demarrer(taches: BackgroundTasks, declencheur: str) -> dict:
    jour = service.jour_local()
    if not service.phrase():
        await service.noter_desactivee()
        return {"statut": "DESACTIVEE", "jour": jour,
                "message": "Sauvegarde générale désactivée : SAUVEGARDE_AUTO_PHRASE absente ou trop courte"}
    if not await service.reserver_jour(jour):
        return {"statut": "DEJA_FAITE", "jour": jour, "message": "La sauvegarde générale du jour est déjà faite ou en cours"}
    taches.add_task(service.executer, jour, declencheur)
    return {"statut": "LANCEE", "jour": jour}


@cron.post("/declencher", status_code=202)
async def declencher(taches: BackgroundTasks, x_sauvegarde_jeton: Optional[str] = Header(default=None)):
    service.verifier_jeton(x_sauvegarde_jeton)
    return await _demarrer(taches, "cron")


@admin.get("")
async def etat(_: dict = Depends(get_super_admin)):
    resultat = await service.etat()
    try:
        resultat["fichiers_r2"] = await service.lister_r2() if service.r2_configure() else []
        resultat["erreur_r2"] = ""
    except Exception as exc:  # noqa: BLE001 — affiché dans l'écran, sans bloquer le reste
        resultat["fichiers_r2"], resultat["erreur_r2"] = [], str(exc)[:300]
    return resultat


@admin.post("/lancer", status_code=202)
async def lancer(taches: BackgroundTasks, _: dict = Depends(get_super_admin)):
    return await _demarrer(taches, "manuel")


class DemandeRestauration(BaseModel):
    cle: str = Field(..., max_length=500)
    mot_de_passe: str = Field(..., max_length=200)
    confirmation: str = Field("", max_length=40)


@admin.post("/restaurer", status_code=202)
async def restaurer(payload: DemandeRestauration, request: Request, user: dict = Depends(get_super_admin)):
    """Mêmes garde-fous que l'import manuel en mode « Remplacer » : mot de passe du
    super-administrateur et mot REMPLACER. Progression : /plateforme/transfert/taches/{id}."""
    if payload.confirmation.strip() != transfert_donnees.MOT_REMPLACER:
        raise HTTPException(400, f"Pour remplacer les données, tapez « {transfert_donnees.MOT_REMPLACER} »")
    ip = acces.ip_client(request)
    await transfert_donnees.verifier_mot_de_passe(user, payload.mot_de_passe, "import", ip)
    return transfert_donnees.publique(await service.restaurer(payload.cle, user, ip))


@compte.get("/sauvegardes/dernieres")
async def dernieres(user: dict = Depends(get_current_user), x_boutique_id: Optional[str] = Header(default=None)):
    """Dernière sauvegarde générale et dernière sauvegarde de la boutique de l'utilisateur
    (pour le super-administrateur : la boutique qu'il consulte, s'il en consulte une)."""
    boutique_id = x_boutique_id if user.get("role") == "super_admin" else user.get("boutique_id")
    return await service.dernieres_sauvegardes(boutique_id)
