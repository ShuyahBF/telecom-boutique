"""Tâches automatiques de la nuit (00h, heure locale) :
1. sauvegarde chiffrée de CHAQUE boutique, envoyée sur Google Drive
   (un dossier par boutique), puis suppression des sauvegardes trop anciennes ;
2. rapport envoyé par e-mail à l'administrateur de la plateforme :
   résultat de chaque sauvegarde + publication du catalogue de 23h.
Chaque résultat (succès ou échec) est aussi conservé en base et visible
dans l'écran « Sauvegardes » de la plateforme.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from pymongo.errors import DuplicateKeyError

import envois_plateforme
import gdrive
import sauvegarde
from config import get_settings
from db import SANS_ID, db
from utils import new_id, now_iso

logger = logging.getLogger(__name__)


async def sauvegarder_toutes(declencheur: str = "planification") -> list[dict]:
    """Sauvegarde toutes les boutiques ; un échec n'empêche jamais les suivantes."""
    s = get_settings()
    # Boutiques internes (présentation) : pas de sauvegarde sur le Drive
    boutiques = await db.boutiques.find({"test": {"$ne": True}}, SANS_ID).sort("nom", 1).to_list(None)
    resultats: list[dict] = []
    drive = None
    async with httpx.AsyncClient(timeout=120) as client:
        erreur_drive = ""
        if gdrive.configure():
            drive = gdrive.GoogleDrive(client)
            try:
                await drive.connecter()
                racine = await drive.dossier(s.gdrive_nom_dossier)
            except Exception as exc:  # noqa: BLE001
                drive, erreur_drive = None, f"Google Drive inaccessible : {exc}"
        else:
            erreur_drive = "Google Drive non configuré (GDRIVE_CLIENT_ID / SECRET / REFRESH_TOKEN)"
        for b in boutiques:
            r = {"id": new_id(), "date": now_iso(), "declencheur": declencheur, "boutique_id": b["id"],
                 "boutique_nom": b["nom"], "code_marchand": b["code_marchand"], "statut": "ECHEC",
                 "fichier": "", "taille": 0, "drive_id": None, "purges": 0, "erreur": ""}
            try:
                nom, archive = await sauvegarde.creer_archive(b["id"])
                r.update({"fichier": nom, "taille": len(archive)})
                if not drive:
                    raise RuntimeError(erreur_drive)
                dossier = await drive.dossier(f"{b['code_marchand']} - {b['nom']}", racine)
                envoye = await drive.envoyer(dossier, nom, archive)
                r.update({"statut": "SUCCES", "drive_id": envoye.get("id")})
                r["purges"] = await drive.purger(dossier, s.sauvegarde_retention_jours)
            except Exception as exc:  # noqa: BLE001 — noté dans le rapport, on continue
                r["erreur"] = getattr(exc, "detail", None) or str(exc)
                logger.warning("Sauvegarde de %s en échec : %s", b["nom"], r["erreur"])
            await db.sauvegardes.insert_one(r.copy())
            resultats.append(r)
    return resultats


def _taille(octets: int) -> str:
    return f"{octets / 1024:.0f} Ko" if octets < 1024 * 1024 else f"{octets / 1024 / 1024:.1f} Mo"


async def construire_rapport(sauvegardes: list[dict]) -> tuple[str, str]:
    """Sujet et texte du rapport de la nuit."""
    depuis = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    publications = await db.catalogue_publications.find({"date": {"$gte": depuis}}, SANS_ID).sort("date", 1).to_list(None)
    reussies = [x for x in sauvegardes if x["statut"] == "SUCCES"]
    echecs = [x for x in sauvegardes if x["statut"] != "SUCCES"]
    etat = "✅ tout est OK" if not echecs else f"⚠️ {len(echecs)} échec(s)"
    sujet = f"[adLyn] Rapport de la nuit — sauvegardes {len(reussies)}/{len(sauvegardes)} {etat}"
    lignes = [f"Rapport du {datetime.now(ZoneInfo(get_settings().fuseau_horaire)):%d/%m/%Y à %H:%M}", "",
              "=== SAUVEGARDES DES BOUTIQUES ===",
              f"Réussies : {len(reussies)} — Échecs : {len(echecs)}", ""]
    for x in sauvegardes:
        if x["statut"] == "SUCCES":
            lignes.append(f"  ✅ {x['code_marchand']} {x['boutique_nom']} : {x['fichier']} ({_taille(x['taille'])})"
                          + (f", {x['purges']} ancienne(s) supprimée(s)" if x.get("purges") else ""))
        else:
            lignes.append(f"  ❌ {x['code_marchand']} {x['boutique_nom']} : {x['erreur']}")
    lignes += ["", "=== CATALOGUE PUBLIC (dernières 24 h) ==="]
    if not publications:
        lignes.append("  Aucune publication (rien n'était prêt à publier, ou la publication n'a pas eu lieu).")
    for p in publications:
        lignes.append(f"  ✅ Publication {p['declencheur']} du {p['date'][:16].replace('T', ' ')} : "
                      f"{p['nouveaux']} nouveauté(s), {p['mises_a_jour']} mise(s) à jour, {p['boutiques']} boutique(s)")
    echecs_catalogue = await db.catalogue_echecs.find({"date": {"$gte": depuis}}, SANS_ID).to_list(None)
    for e in echecs_catalogue:
        lignes.append(f"  ❌ Publication du {e['date'][:16].replace('T', ' ')} en échec : {e['erreur']}")
    return sujet, "\n".join(lignes)


async def envoyer_rapport(sauvegardes: list[dict]) -> dict:
    """Envoie le rapport à RAPPORT_EMAIL et garde une copie en base."""
    s = get_settings()
    sujet, corps = await construire_rapport(sauvegardes)
    rapport = {"id": new_id(), "date": now_iso(), "destinataire": s.rapport_email or "", "sujet": sujet,
               "corps": corps, "statut": "NON_ENVOYE", "erreur": ""}
    if not s.rapport_email:
        rapport["erreur"] = "RAPPORT_EMAIL non configuré"
    else:
        # Serveur d'envoi de la plateforme (réglé dans l'administration ou par variables)
        statut, erreur = await envois_plateforme.envoyer_email(sujet, corps, s.rapport_email)
        rapport.update({"statut": "ENVOYE" if statut == "ENVOYE" else ("ECHEC" if statut == "ECHEC" else "NON_ENVOYE"),
                        "erreur": erreur})
    await db.rapports.insert_one(rapport.copy())
    return rapport


async def nuit(declencheur: str = "planification") -> dict:
    import sms_boutiques

    resultats = await sauvegarder_toutes(declencheur)
    # Le 1er du mois : factures du service SMS pour le mois écoulé
    factures_sms = await sms_boutiques.facturation_mensuelle()
    return {"sauvegardes": resultats, "factures_sms": factures_sms, "rapport": await envoyer_rapport(resultats)}


def prochaine_execution(maintenant: datetime | None = None) -> datetime:
    s = get_settings()
    tz = ZoneInfo(s.fuseau_horaire)
    maintenant = maintenant or datetime.now(tz)
    cible = maintenant.replace(hour=s.sauvegarde_heure, minute=0, second=0, microsecond=0)
    return cible if cible > maintenant else cible + timedelta(days=1)


async def boucle_nocturne() -> None:
    """Démarrée avec le serveur ; un verrou par nuit évite les doublons si
    plusieurs serveurs tournent."""
    tz = ZoneInfo(get_settings().fuseau_horaire)
    while True:
        cible = prochaine_execution()
        await asyncio.sleep(max((cible - datetime.now(tz)).total_seconds(), 1))
        try:
            await db.verrous.insert_one({"_id": f"nuit-{cible.date().isoformat()}", "date": now_iso()})
        except DuplicateKeyError:
            continue
        try:
            await nuit("planification")
        except Exception:  # noqa: BLE001
            logger.exception("Échec des tâches de nuit")
