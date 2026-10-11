"""Lot 39 — Connexions et visites d'adLyn signalées à SAWALI (alerte WhatsApp du propriétaire).

Demande du propriétaire (11/10/2026) : recevoir un message WhatsApp, envoyé par
SAWALI, à chaque connexion sur adLyn (et à l'arrivée d'un visiteur sur le site).

En résumé (pour un développeur WinDev) :
  - adLyn appelle la route SIGNÉE de SAWALI (SAWALI lot 109) :
        POST https://api.sawalismartsystems.com/api/webhook/plateforme-connexion
    avec EXACTEMENT la même signature que le support SAWALI et la Transmission WA :
    en-têtes X-Emetteur (code d'adLyn chez SAWALI), X-Timestamp (secondes depuis
    1970) et X-Signature = HMAC-SHA256(clé, "<horodatage>.<corps brut>") en hexadécimal ;
  - clé, code émetteur et adresse de SAWALI : ceux déjà configurés sur Render
    (LILUVINE_WA_HMAC, LILUVINE_WA_EMETTEUR, SAWALI_API_URL / LILUVINE_WA_URL),
    relus par les fonctions de support_sawali.py — aucun secret dans le code ;
  - corps JSON : {type: "connexion" | "visite", le, ip, utilisateur, telephone, role,
    visiteur, url_site, page, agent} — JAMAIS de mot de passe, de jeton ni de clé ;
  - SAWALI décide d'alerter ou non (anti-répétition, robots, plafond) et répond
    {ok, alerte, raison} : adLyn n'en fait rien de plus ;
  - l'envoi part EN ARRIÈRE-PLAN (tâche asyncio), délai court (5 s), ne lève
    JAMAIS d'exception et ne retarde jamais la connexion de l'utilisateur ;
  - rien n'est envoyé si la clé SAWALI n'est pas saisie, ou si la variable
    SIGNAL_CONNEXIONS_SAWALI vaut « 0 » (interrupteur, coupé pendant les tests).

Points branchés :
  - « connexion » : routes/auth.py (/auth/login : mot de passe, e-mail ou téléphone,
    personnel des boutiques et super-administrateur) et routes/espace_client.py
    (/espace-client/verifier-code : code à usage unique reçu par WhatsApp / SMS) ;
  - « visite »    : route publique POST /api/presence/visite (ci-dessous), appelée
    par le site au chargement quand personne n'est connecté.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

import support_sawali  # clé, code émetteur et adresse de SAWALI (mêmes réglages que le support)
from config import get_settings
from transmission_wa import signer  # même signature HMAC que la Transmission WA et le support

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
CHEMIN_SAWALI = "/api/webhook/plateforme-connexion"   # route de SAWALI (lot 109)
DELAI_SECONDES = 5                                    # délai maximal de l'appel à SAWALI
INTERVALLE_VISITES = 30 * 60                          # 1 visite signalée / 30 min par visiteur ou par IP
TAILLE_MAX_CACHE = 20_000                             # au-delà, on purge les entrées périmées

# Libellés des rôles du personnel (même liste que l'onglet « Usage » de la plateforme)
ROLES = {"super_admin": "Super-administrateur", "dg": "DG", "commercial": "Commercial",
         "secretaire": "Secrétaire", "comptable": "Comptable", "technicien": "Technicien"}

# Robots évidents (moteurs de recherche, aperçus de liens, outils en ligne de commande…)
MOTIF_ROBOT = re.compile(
    r"bot|crawl|spider|slurp|curl|wget|python|httpx|aiohttp|requests|java/|go-http|okhttp|headless|"
    r"phantom|selenium|puppeteer|playwright|lighthouse|facebookexternalhit|whatsapp|preview|monitor|"
    r"uptime|pingdom|render/|axios/|node-fetch|scrapy|feedfetcher|validator", re.IGNORECASE)

# Transport HTTP de remplacement (tests) : None en production
_transport: Optional[httpx.AsyncBaseTransport] = None

# Tâches d'envoi en cours : gardées ici pour qu'asyncio ne les oublie pas en route
_taches: Set[asyncio.Task] = set()

# Mémoire des dernières visites signalées : clé (« v:<id> » ou « ip:<adresse> ») -> heure (secondes)
_dernieres_visites: Dict[str, float] = {}


# ---------------------------------------------------------------------------
# Réglages
# ---------------------------------------------------------------------------
def actif() -> bool:
    """Vrai si l'envoi est permis : interrupteur non coupé ET clé SAWALI saisie sur Render."""
    if os.environ.get("SIGNAL_CONNEXIONS_SAWALI", "1").strip() == "0":
        return False
    return support_sawali.configure()


def url_site() -> str:
    """Adresse publique du site adLyn : la PREMIÈRE adresse de FRONTEND_ORIGIN."""
    return get_settings().public_site_url


def ip_reelle(request: Request) -> str:
    """Adresse IP du visiteur : premier élément de X-Forwarded-For, sinon l'adresse de la connexion."""
    transmis = request.headers.get("x-forwarded-for", "")
    if transmis:
        premiere = transmis.split(",")[0].strip()
        if premiere:
            return premiere[:64]
    return request.client.host if request.client else ""


def maintenant_iso() -> str:
    """Date/heure actuelle en ISO UTC court, ex. « 2026-10-11T08:15:00Z »."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def telephone_chiffres(valeur: Any) -> Optional[str]:
    """Numéro réduit à ses chiffres (« +226 70 12 34 56 » -> « 22670123456 »), None s'il est vide."""
    chiffres = re.sub(r"\D", "", str(valeur or ""))
    return chiffres or None


def est_robot(agent: str) -> bool:
    """Vrai pour un navigateur sans identité ou un robot évident."""
    return not agent.strip() or bool(MOTIF_ROBOT.search(agent))


# ---------------------------------------------------------------------------
# Construction du corps (fonction PURE : facile à tester, aucun accès réseau)
# ---------------------------------------------------------------------------
def construire_corps(type_signal: str, request: Request, *, utilisateur: Optional[str] = None,
                     telephone: Optional[str] = None, role: Optional[str] = None,
                     visiteur: Optional[str] = None, page: Optional[str] = None,
                     boutique: Optional[str] = None) -> Dict[str, Any]:
    """Corps JSON envoyé à SAWALI. Aucun secret : ni mot de passe, ni jeton, ni clé."""
    corps: Dict[str, Any] = {
        "type": type_signal,
        "le": maintenant_iso(),
        "ip": ip_reelle(request),
        "utilisateur": utilisateur or None,
        "telephone": telephone_chiffres(telephone),
        "role": role or None,
        "visiteur": visiteur or None,
        "url_site": url_site(),
        "page": page or None,
        "agent": (request.headers.get("user-agent") or "")[:300],
    }
    if boutique:
        corps["boutique"] = boutique  # information en plus (nom de la boutique), ignorée si SAWALI ne la lit pas
    return corps


# ---------------------------------------------------------------------------
# Envoi signé (jamais d'exception)
# ---------------------------------------------------------------------------
async def envoyer(corps: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """POST signé vers SAWALI. Renvoie la réponse JSON, ou None (non configuré, erreur, délai dépassé)."""
    try:
        if not actif():
            return None
        # Corps sérialisé UNE SEULE FOIS : ce sont exactement ces octets qui sont signés puis envoyés
        brut = json.dumps(corps, ensure_ascii=False).encode("utf-8")
        ts = str(int(time.time()))
        entetes = {"Content-Type": "application/json", "X-Emetteur": support_sawali.emetteur(),
                   "X-Timestamp": ts, "X-Signature": signer(support_sawali.cle(), ts, brut)}
        async with httpx.AsyncClient(timeout=DELAI_SECONDES, transport=_transport) as client:
            r = await client.post(f"{support_sawali.url_sawali()}{CHEMIN_SAWALI}", content=brut, headers=entetes)
        if r.status_code >= 400:
            logger.info("Signal %s refusé par SAWALI (HTTP %s)", corps.get("type"), r.status_code)
            return None
        return r.json()
    except Exception as exc:  # noqa: BLE001 — le signal ne doit JAMAIS gêner adLyn
        logger.info("Signal %s non transmis à SAWALI : %s", corps.get("type"), type(exc).__name__)
        return None


def planifier(corps: Dict[str, Any]) -> None:
    """Lance l'envoi en arrière-plan (la requête de l'utilisateur n'attend pas)."""
    try:
        if not actif():
            return
        tache = asyncio.get_running_loop().create_task(envoyer(corps))
        _taches.add(tache)
        tache.add_done_callback(_taches.discard)
    except Exception:  # noqa: BLE001 — pas de boucle asyncio, etc. : on ignore
        pass


# ---------------------------------------------------------------------------
# « connexion » : appelé par chaque route qui ouvre une session
# ---------------------------------------------------------------------------
def signaler_connexion_personnel(request: Request, user: dict, boutique: Optional[dict] = None) -> None:
    """Connexion réussie du personnel d'une boutique ou du super-administrateur (mot de passe)."""
    try:
        role_brut = user.get("role") or ""
        libelle_role = ROLES.get(role_brut, role_brut)
        nom = user.get("nom") or user.get("email") or "Compte sans nom"
        nom_boutique = (boutique or {}).get("nom") or ""
        # Libellé lisible dans le WhatsApp : « Awa Ouédraogo (DG) · Télécom Wendpanga »
        libelle = f"{nom} ({libelle_role})" + (f" · {nom_boutique}" if nom_boutique else "")
        planifier(construire_corps(
            "connexion", request, utilisateur=libelle,
            telephone=user.get("telephone") or (boutique or {}).get("telephone"),
            role="admin" if role_brut == "super_admin" else "boutique",
            page="/connexion", boutique=nom_boutique or None))
    except Exception:  # noqa: BLE001
        pass


def signaler_connexion_client(request: Request, client: dict, boutique: dict) -> None:
    """Ouverture de « Mon espace » par un client (code à usage unique reçu par WhatsApp / SMS)."""
    try:
        nom_boutique = boutique.get("nom") or ""
        nom = client.get("nom") or "Client"
        planifier(construire_corps(
            "connexion", request, utilisateur=f"{nom} (client) · {nom_boutique}" if nom_boutique else f"{nom} (client)",
            telephone=client.get("telephone"), role="client", page="/mon-espace",
            boutique=nom_boutique or None))
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# « visite » : visiteur non connecté (1 signal / 30 min par visiteur ou par IP)
# ---------------------------------------------------------------------------
def _purger(maintenant: float) -> None:
    """Oublie les visites de plus de 30 minutes quand la mémoire devient trop grosse."""
    if len(_dernieres_visites) <= TAILLE_MAX_CACHE:
        return
    for cle in [c for c, t in _dernieres_visites.items() if maintenant - t >= INTERVALLE_VISITES]:
        _dernieres_visites.pop(cle, None)
    if len(_dernieres_visites) > TAILLE_MAX_CACHE:  # toujours trop : on repart de zéro
        _dernieres_visites.clear()


def visite_autorisee(visiteur: str, ip: str, maintenant: Optional[float] = None) -> bool:
    """Vrai si ni ce visiteur ni cette IP n'ont été signalés depuis 30 minutes (et on le note)."""
    t = time.time() if maintenant is None else maintenant
    _purger(t)
    cles = [c for c in (f"v:{visiteur}" if visiteur else "", f"ip:{ip}" if ip else "") if c]
    if any(t - _dernieres_visites.get(c, -INTERVALLE_VISITES) < INTERVALLE_VISITES for c in cles):
        return False
    for c in cles:
        _dernieres_visites[c] = t
    return True


class Visite(BaseModel):
    """Envoyé par le site : identifiant anonyme du navigateur (aléatoire) et page d'arrivée."""
    visiteur: str = Field("", max_length=80)
    page: str = Field("", max_length=300)


public = APIRouter(prefix="/presence", tags=["Présence (visites)"])


@public.post("/visite")
async def visite(entree: Visite, request: Request):
    """Route publique légère : répond tout de suite ; le signal (s'il y a lieu) part en arrière-plan."""
    try:
        if not actif():
            return {"ok": True, "signale": False}
        agent = request.headers.get("user-agent") or ""
        if est_robot(agent):
            return {"ok": True, "signale": False}
        # Personne connectée (cookie de session du personnel) : ce n'est pas une « visite »
        if request.cookies.get(get_settings().session_cookie_nom):
            return {"ok": True, "signale": False}
        visiteur = re.sub(r"[^A-Za-z0-9_-]", "", entree.visiteur)[:64]
        page = entree.page.strip()[:200] or "/"
        if not page.startswith("/"):
            page = "/" + page
        if not visite_autorisee(visiteur, ip_reelle(request)):
            return {"ok": True, "signale": False}
        planifier(construire_corps("visite", request, visiteur=visiteur or None, page=page))
        return {"ok": True, "signale": True}
    except Exception:  # noqa: BLE001 — une visite ne doit jamais provoquer d'erreur
        return {"ok": True, "signale": False}
