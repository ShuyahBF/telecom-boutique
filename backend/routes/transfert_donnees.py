"""Sauvegarde / transfert COMPLET des données de la plateforme (changement de
cluster MongoDB) — réservé au super-administrateur, avec ressaisie de son mot
de passe à chaque action. Logique : voir transfert_donnees.py."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

import acces
import chiffrement_flux
import transfert_donnees as service
from auth import get_super_admin

# on_startup : nettoyage des fichiers temporaires (repris par l'application
# lors de l'inclusion du routeur, sans toucher au démarrage de server.py)
router = APIRouter(prefix="/plateforme/transfert", tags=["Transfert des données (super-admin)"],
                   on_startup=[service.au_demarrage])


class DemandeExport(BaseModel):
    mot_de_passe: str = Field(max_length=200)
    phrase: str = Field(max_length=chiffrement_flux.PHRASE_MAX)
    phrase_confirmation: str = Field(max_length=chiffrement_flux.PHRASE_MAX)


@router.get("")
async def etat(_: dict = Depends(get_super_admin)):
    """Base actuelle, opération en cours, dernières opérations du journal."""
    return await service.etat_base()


@router.post("/export", status_code=202)
async def exporter(payload: DemandeExport, request: Request, user: dict = Depends(get_super_admin)):
    try:
        phrase = chiffrement_flux.valider_phrase(payload.phrase, payload.phrase_confirmation)
    except chiffrement_flux.ErreurChiffrement as exc:
        raise HTTPException(400, str(exc)) from exc
    ip = acces.ip_client(request)
    await service.verifier_mot_de_passe(user, payload.mot_de_passe, "export", ip)
    return service.publique(await service.lancer_export(user, phrase, ip))


@router.post("/import", status_code=202)
async def importer(
    request: Request,
    fichier: UploadFile = File(...),
    phrase: str = Form(..., max_length=chiffrement_flux.PHRASE_MAX),
    mot_de_passe: str = Form(..., max_length=200),
    mode: str = Form("vide"),
    confirmation: str = Form(""),
    user: dict = Depends(get_super_admin),
):
    if mode not in service.MODES:
        raise HTTPException(400, "Mode d'import inconnu")
    if mode == "remplacer" and confirmation.strip() != service.MOT_REMPLACER:
        raise HTTPException(400, f"Pour remplacer les données, tapez « {service.MOT_REMPLACER} »")
    ip = acces.ip_client(request)
    await service.verifier_mot_de_passe(user, mot_de_passe, "import", ip)
    return service.publique(await service.preparer_import(user, fichier, phrase, mode, ip))


@router.get("/taches/{tache_id}")
async def suivre(tache_id: str):
    """Progression d'un export / import. Sans session : pendant un import, les
    comptes (dont celui du super-administrateur) sont remplacés et la session
    en cours devient invalide ; l'identifiant de la tâche, aléatoire (256 bits)
    et connu du seul navigateur qui l'a lancée, sert de clé de suivi. Seuls la
    progression et les nombres de documents sont renvoyés, jamais de données."""
    return service.publique(service.lire_tache(tache_id))


@router.get("/taches/{tache_id}/fichier")
async def telecharger(tache_id: str, request: Request, user: dict = Depends(get_super_admin)):
    """Téléchargement (unique) du fichier chiffré ; il est ensuite supprimé du serveur."""
    chemin, nom = await service.fichier_export(tache_id, user, acces.ip_client(request))
    return FileResponse(chemin, media_type="application/octet-stream", filename=nom,
                        background=BackgroundTask(service.apres_telechargement, tache_id))
