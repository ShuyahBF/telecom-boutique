"""Sauvegardes et restaurations des boutiques, rapports de la nuit
(réservé à l'administrateur de la plateforme)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

import envois_plateforme
import gdrive
import sauvegarde
import taches_nocturnes
from auth import get_super_admin
from config import get_settings
from db import SANS_ID, db
from fastapi.responses import FileResponse, RedirectResponse

from storage import chemin_local_prive, enregistrer_prive, lien_temporaire_prive
from utils import new_id, now_iso

router = APIRouter(prefix="/plateforme", tags=["Sauvegardes (super-admin)"])


@router.get("/sauvegardes")
async def historique(boutique_id: str = "", du: str = "", au: str = "", _: dict = Depends(get_super_admin)):
    filtre: dict = {}
    if boutique_id:
        filtre["boutique_id"] = boutique_id
    if du or au:
        filtre["date"] = {**({"$gte": du} if du else {}), **({"$lte": au + "T23:59:59"} if au else {})}
    s = get_settings()
    return {
        "configuration": {"cle_chiffrement": bool(s.sauvegarde_cle), "google_drive": gdrive.configure(),
                          "dossier_drive": s.gdrive_nom_dossier, "retention_jours": s.sauvegarde_retention_jours,
                          "rapport_email": s.rapport_email or "", "smtp_plateforme": await envois_plateforme.email_pret(),
                          "prochaine_execution": taches_nocturnes.prochaine_execution().isoformat()},
        "sauvegardes": await db.sauvegardes.find(filtre, SANS_ID).sort("date", -1).to_list(500),
        "rapports": await db.rapports.find({}, {"_id": 0, "corps": 0}).sort("date", -1).to_list(30),
    }


@router.get("/rapports/{rapport_id}")
async def lire_rapport(rapport_id: str, _: dict = Depends(get_super_admin)):
    r = await db.rapports.find_one({"id": rapport_id}, SANS_ID)
    if not r:
        raise HTTPException(404, "Rapport introuvable")
    return r


@router.get("/sauvegardes/{sauvegarde_id}/fichier")
async def telecharger_sauvegarde_privee(sauvegarde_id: str, _: dict = Depends(get_super_admin)):
    """Télécharge une sauvegarde gardée sur le serveur (celle faite juste avant une restauration)."""
    entree = await db.sauvegardes.find_one({"id": sauvegarde_id}, SANS_ID)
    if not entree or not entree.get("cle_privee"):
        raise HTTPException(404, "Cette sauvegarde n'est pas conservée sur le serveur")
    lien = await lien_temporaire_prive(entree["cle_privee"])
    if lien:
        return RedirectResponse(lien)
    chemin = chemin_local_prive(entree["cle_privee"])
    if not chemin.exists():
        raise HTTPException(404, "Fichier introuvable")
    return FileResponse(chemin, media_type="application/octet-stream", filename=entree["fichier"])


@router.post("/sauvegardes/lancer")
async def lancer_maintenant(_: dict = Depends(get_super_admin)):
    """Lance tout de suite les sauvegardes de toutes les boutiques + le rapport."""
    return await taches_nocturnes.nuit("manuel")


@router.get("/boutiques/{boutique_id}/sauvegarde")
async def telecharger(boutique_id: str, _: dict = Depends(get_super_admin)):
    """Télécharge une sauvegarde chiffrée de la boutique (à conserver en lieu sûr)."""
    nom, archive = await sauvegarde.creer_archive(boutique_id)
    return Response(archive, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})


@router.post("/boutiques/{boutique_id}/restauration")
async def restaurer(boutique_id: str, fichier: UploadFile = File(...), confirmation: str = Form(...),
                    admin: dict = Depends(get_super_admin)):
    """Remplace toutes les données de la boutique par celles de la sauvegarde.
    Garde-fous : confirmation = code marchand, et sauvegarde automatique de
    l'état actuel juste avant (restauration annulable)."""
    boutique = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not boutique:
        raise HTTPException(404, "Boutique introuvable")
    if confirmation.strip().upper() != boutique["code_marchand"]:
        raise HTTPException(400, f"Pour confirmer, saisissez le code marchand de la boutique ({boutique['code_marchand']})")
    contenu = await fichier.read()
    sauvegarde.dechiffrer(contenu)  # vérifie clé et intégrité AVANT de toucher aux données
    # État actuel mis de côté (stockage privé) avant de l'écraser
    nom, avant = await sauvegarde.creer_archive(boutique_id)
    cle = await _garder_prive(boutique_id, avant)
    await db.sauvegardes.insert_one({
        "id": new_id(), "date": now_iso(), "declencheur": "avant_restauration", "boutique_id": boutique_id,
        "boutique_nom": boutique["nom"], "code_marchand": boutique["code_marchand"], "statut": "SUCCES",
        "fichier": nom, "taille": len(avant), "drive_id": None, "cle_privee": cle, "purges": 0, "erreur": ""})
    resultat = await sauvegarde.restaurer(boutique_id, contenu)
    return {**resultat, "sauvegarde_avant_restauration": nom, "restaure_par": admin.get("nom", "")}


async def _garder_prive(boutique_id: str, archive: bytes) -> str:
    """Range l'archive dans le stockage privé de la boutique."""
    return await enregistrer_prive(boutique_id, archive, "application/octet-stream")
