"""Présence auprès de SAWALI (règle 4 du propriétaire).

Le serveur adLyn déclare sa présence à SAWALI :
  POST https://api.sawalismartsystems.com/api/presence-logiciel
au démarrage (après 10 secondes) puis toutes les 5 minutes.

Suivi côté SAWALI : Plateformes en temps réel → « Postes Windows — versions
déployées » (poste en ligne si signal reçu il y a moins de 12 minutes).

Principes :
  - envoi en arrière-plan, JAMAIS bloquant : toute erreur est ignorée ;
  - aucun secret ni donnée client dans le signal ;
  - en-tête facultatif « X-Cle-Loois » lu dans la variable d'environnement
    LOOIS_SUPPORT_CLE (jamais écrite dans le code) ;
  - désactivable avec la variable d'environnement PRESENCE_SAWALI=0.

Version envoyée : la MÊME que celle affichée sur le site, lue dans la source
unique « frontend/src/version.js » (constante VERSION). Sur Render, le dépôt
entier est cloné même si le service démarre dans « backend » : le fichier est
donc présent. À défaut, on envoie le commit court (RENDER_GIT_COMMIT, 7 car.).
"""
from __future__ import annotations

import asyncio
import os
import platform
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

import httpx

# --- Constantes du signal ----------------------------------------------------
URL_PRESENCE = "https://api.sawalismartsystems.com/api/presence-logiciel"
APPLICATION = "adLyn"
SITE = "adlynservice.com"
UTILISATEUR = "serveur"
DELAI_PREMIER_ENVOI = 10        # secondes après le démarrage
INTERVALLE_ENVOI = 5 * 60       # toutes les 5 minutes
DELAI_RESEAU = 10               # délai maximal d'une requête HTTP (secondes)

# Source unique de la version (côté site), relative au dossier backend
FICHIER_VERSION = Path(__file__).resolve().parent.parent / "frontend" / "src" / "version.js"

# Heure de démarrage du processus (fixée au chargement du module)
DEMARRE_LE = datetime.now(timezone.utc)


def format_iso_utc(moment: datetime) -> str:
    """Date/heure au format ISO UTC court, ex. « 2026-10-06T13:40:00Z »."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lire_version(fichier: Path = FICHIER_VERSION) -> str:
    """Version déployée : constante VERSION de frontend/src/version.js.

    Si le fichier est absent ou illisible, on renvoie le commit court
    (RENDER_GIT_COMMIT sur Render), sinon « inconnue »."""
    try:
        texte = fichier.read_text(encoding="utf-8")
        trouve = re.search(r"export\s+const\s+VERSION\s*=\s*([0-9.]+)", texte)
        if trouve:
            return trouve.group(1)
    except OSError:
        pass
    commit = os.environ.get("RENDER_GIT_COMMIT", "")
    return commit[:7] if commit else "inconnue"


def lire_date_deploiement(fichier: Path = FICHIER_VERSION) -> str | None:
    """Date de déploiement (ISO UTC) si elle est connue, sinon None.

    Sur Render (variable RENDER présente), chaque déploiement repart d'un
    clone neuf du dépôt : la date de modification du fichier de version est
    donc l'heure du déploiement. Hors Render, on ne sait pas : None."""
    if not os.environ.get("RENDER"):
        return None
    try:
        return format_iso_utc(datetime.fromtimestamp(fichier.stat().st_mtime, timezone.utc))
    except OSError:
        return None


def nom_machine() -> str:
    """Nom du poste : nom du service Render, sinon nom réseau de la machine."""
    return os.environ.get("RENDER_SERVICE_NAME") or socket.gethostname()


def construire_signal(version: str, deploye_le: str | None, machine: str,
                      demarre_le: datetime, version_python: str) -> dict:
    """Fonction PURE : construit le corps JSON du signal de présence.

    Aucun accès au réseau ni à l'environnement ici (facile à tester)."""
    return {
        "application": APPLICATION,
        "version": version,
        "deploye_le": deploye_le,
        "machine": machine,
        "utilisateur": UTILISATEUR,
        "site": SITE,
        "systeme": f"Render · Python {version_python}",
        "demarre_le": format_iso_utc(demarre_le),
    }


def entetes() -> dict:
    """En-têtes HTTP : la clé du support n'est ajoutée que si elle existe."""
    resultat = {"Content-Type": "application/json"}
    cle = os.environ.get("LOOIS_SUPPORT_CLE")
    if cle:
        resultat["X-Cle-Loois"] = cle
    return resultat


async def envoyer_signal() -> None:
    """Envoie UN signal ; toute erreur (réseau, délai, réponse) est ignorée."""
    try:
        corps = construire_signal(lire_version(), lire_date_deploiement(), nom_machine(),
                                  DEMARRE_LE, platform.python_version())
        async with httpx.AsyncClient(timeout=DELAI_RESEAU) as client:
            await client.post(URL_PRESENCE, json=corps, headers=entetes())
    except Exception:  # noqa: BLE001 — le signal ne doit jamais gêner le serveur
        pass


def presence_active() -> bool:
    """Le signal est actif sauf si PRESENCE_SAWALI vaut « 0 »."""
    return os.environ.get("PRESENCE_SAWALI", "1").strip() != "0"


async def boucle_presence() -> None:
    """Tâche de fond : premier envoi après 10 s, puis toutes les 5 minutes."""
    if not presence_active():
        return
    await asyncio.sleep(DELAI_PREMIER_ENVOI)
    while True:
        await envoyer_signal()
        await asyncio.sleep(INTERVALLE_ENVOI)
