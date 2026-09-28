"""Contrôle d'accès des boutiques : adresses IP et appareils autorisés / interdits.

Chaque boutique (son DG) tient une liste de RÈGLES :
  - type « IP » : adresse ou motif avec « * » (ex. 196.28.245.12, 196.28.*, *) ;
  - type « APPAREIL » : identifiant d'appareil (cookie posé par le site à la
    première connexion, visible dans le journal) ou « * » ;
  - action « INTERDIRE » ou « AUTORISER ».
Décision, pour chaque connexion ET chaque requête du back-office :
  1. une règle INTERDIRE qui correspond -> refus (l'interdiction l'emporte toujours) ;
  2. s'il existe au moins une règle AUTORISER (liste blanche), il faut en
     satisfaire une ; « * » dans la liste blanche autorise tout le monde ;
  3. sans liste blanche : accès autorisé.
Le super-administrateur de la plateforme n'est jamais soumis à ces règles.

Chaque tentative de connexion au back-office est tracée (journal de la
boutique + journal du serveur) : date, compte, adresse IP, appareil, résultat.
Depuis une ligne du journal, le DG peut autoriser ou interdire cette adresse
ou cet appareil pour les connexions futures.
"""
from __future__ import annotations

import fnmatch
import logging
import re
import secrets
from typing import Optional

from fastapi import Request, Response

from config import get_settings
from db import db
from utils import new_id, now_iso

logger = logging.getLogger("adlyn.connexions")

COOKIE_APPAREIL = "adlyn_appareil"
MOTIF_IP = re.compile(r"^[0-9A-Fa-f:.*]{1,45}$")
MOTIF_APPAREIL = re.compile(r"^(\*|[A-Za-z0-9]{8,40})$")


# ---------------------------------------------------------------------------
# Identification de la connexion : adresse IP, appareil
# ---------------------------------------------------------------------------
def ip_client(request: Request) -> str:
    """Adresse de l'appelant. Derrière le proxy de Render, c'est la DERNIÈRE
    adresse de X-Forwarded-For (celle ajoutée par Render, non falsifiable)."""
    transmis = request.headers.get("x-forwarded-for", "")
    if transmis:
        return transmis.split(",")[-1].strip()
    return request.client.host if request.client else "inconnue"


def appareil_id(request: Request) -> str:
    """Identifiant de l'appareil (cookie), "" s'il n'en a pas encore."""
    valeur = request.cookies.get(COOKIE_APPAREIL, "")
    return valeur if MOTIF_APPAREIL.match(valeur or "") and valeur != "*" else ""


def poser_cookie_appareil(request: Request, response: Response) -> str:
    """Donne un identifiant à l'appareil s'il n'en a pas (cookie HttpOnly de 2 ans)."""
    actuel = appareil_id(request)
    if actuel:
        return actuel
    nouveau = secrets.token_hex(8).upper()
    securise = get_settings().public_site_url.startswith("https://")
    response.set_cookie(COOKIE_APPAREIL, nouveau, max_age=2 * 365 * 24 * 3600, httponly=True, secure=securise,
                        samesite="none" if securise else "lax", path="/")
    return nouveau


def description_appareil(user_agent: str) -> str:
    """« Chrome sur Android », « Safari sur iPhone »... (lisible dans le journal)."""
    ua = user_agent or ""
    systeme = next((nom for cle, nom in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                                         ("Windows", "Windows"), ("Mac OS", "Mac"), ("Linux", "Linux")) if cle in ua), "")
    navigateur = next((nom for cle, nom in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"),
                                            ("Chrome/", "Chrome"), ("Safari/", "Safari")) if cle in ua), "")
    if not (systeme or navigateur):
        return (ua[:60] or "Appareil inconnu")
    return f"{navigateur or 'Navigateur'} sur {systeme or 'système inconnu'}"


# ---------------------------------------------------------------------------
# Règles
# ---------------------------------------------------------------------------
def regles(boutique: dict) -> list[dict]:
    return (boutique.get("acces") or {}).get("regles") or []


def _correspond(regle: dict, ip: str, appareil: str) -> bool:
    valeur = regle["valeur"]
    if regle["type"] == "IP":
        return fnmatch.fnmatchcase(ip, valeur)
    return valeur == "*" or (bool(appareil) and valeur == appareil)


def verdict(liste: list[dict], ip: str, appareil: str) -> tuple[bool, str]:
    """(autorisé ?, raison du refus)."""
    for r in liste:
        if r["action"] == "INTERDIRE" and _correspond(r, ip, appareil):
            return False, "Adresse IP interdite" if r["type"] == "IP" else "Appareil interdit"
    blanche = [r for r in liste if r["action"] == "AUTORISER"]
    if blanche and not any(_correspond(r, ip, appareil) for r in blanche):
        return False, "Adresse IP ou appareil absent de la liste des accès autorisés"
    return True, ""


def controler(boutique: dict, request: Request) -> tuple[bool, str]:
    return verdict(regles(boutique), ip_client(request), appareil_id(request))


def valider_regle(type_: str, valeur: str) -> str:
    """Valeur nettoyée, ou ValueError si elle n'a pas le bon format."""
    valeur = (valeur or "").strip()
    if type_ == "IP" and not MOTIF_IP.match(valeur):
        raise ValueError("Adresse IP invalide : chiffres, points (ou « : » en IPv6) et « * » seulement, ex. 196.28.*")
    if type_ == "APPAREIL":
        valeur = valeur.upper() if valeur != "*" else valeur
        if not MOTIF_APPAREIL.match(valeur):
            raise ValueError("Identifiant d'appareil invalide (copiez-le depuis le journal des connexions)")
    return valeur


# ---------------------------------------------------------------------------
# Journal des connexions
# ---------------------------------------------------------------------------
RESULTATS = {"SUCCES": "Connexion réussie", "ECHEC": "Identifiants incorrects", "BLOQUE": "Connexion refusée (règle d'accès)"}


async def journaliser(boutique_id: str, request: Request, resultat: str, *, user: Optional[dict] = None,
                      email: str = "", raison: str = "", appareil: str = "") -> None:
    ua = request.headers.get("user-agent", "")
    ligne = {"id": new_id(), "boutique_id": boutique_id, "date": now_iso(), "resultat": resultat, "raison": raison,
             "ip": ip_client(request), "appareil_id": appareil or appareil_id(request),
             "appareil": description_appareil(ua), "user_agent": ua[:250],
             "user_id": (user or {}).get("id"), "email": (user or {}).get("email") or email,
             "nom": (user or {}).get("nom", ""), "role": (user or {}).get("role", "")}
    await db.connexions_journal.insert_one(ligne.copy())
    # Même trace dans le journal du serveur (fichier de logs Render)
    logger.info("connexion boutique=%s resultat=%s email=%s ip=%s appareil=%s (%s) %s", boutique_id, resultat,
                ligne["email"], ligne["ip"], ligne["appareil_id"] or "-", ligne["appareil"], raison)
