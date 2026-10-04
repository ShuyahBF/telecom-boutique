"""Transmission WA : point d'envoi UNIQUE des messages WhatsApp d'adLyn.

Règle du propriétaire — chaque plateforme envoie avec SES PROPRES paramètres WABA
s'ils existent. Ordre de priorité appliqué ici :
  1. paramètres WABA de la BOUTIQUE concernée (champ « whatsapp_waba » de la fiche
     boutique : phone_number_id + access_token CHIFFRÉ) ;
  2. paramètres WABA de la PLATEFORME adLyn (WHATSAPP_ACCESS_TOKEN,
     WHATSAPP_PHONE_NUMBER_ID) ;
  3. À DÉFAUT, « Transmission WA Universelle Liluvine » : appel HTTP signé (HMAC)
     vers SAWALI, qui envoie le message avec son propre compte WhatsApp
     (variables LILUVINE_WA_URL, LILUVINE_WA_HMAC, LILUVINE_WA_EMETTEUR).

Un compte WABA configuré qui échoue NE bascule PAS sur le canal suivant : le
comportement reste identique à celui d'avant quand WhatsApp est branché.

Résultat toujours uniforme, jamais d'exception :
  {"ok", "canal": "waba_boutique"|"waba_plateforme"|"liluvine"|None,
   "message_id", "erreur", "statut": "ENVOYE"|"ECHEC"|"NON_CONFIGURE"}
Sécurité : la clé HMAC et le texte complet du message ne sont jamais journalisés.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Optional, Union

import httpx

import envois_plateforme as envois
from config import get_settings

logger = logging.getLogger(__name__)

DELAI_LILUVINE = 15  # secondes (protocole v2)
LONGUEUR_MAX = 4096  # caractères au plus acceptés par SAWALI


# ---------------------------------------------------------------------------
# Construction du résultat uniforme
# ---------------------------------------------------------------------------
def _resultat(ok: bool, canal: Optional[str], *, message_id: Optional[str] = None, erreur: Optional[str] = None,
              statut: Optional[str] = None) -> dict:
    """Résultat commun à tous les canaux. `statut` sert aux anciens appelants
    (journal : ENVOYE / ECHEC / NON_CONFIGURE)."""
    return {"ok": ok, "canal": canal, "message_id": message_id, "erreur": erreur,
            "statut": statut or ("ENVOYE" if ok else "ECHEC")}


# ---------------------------------------------------------------------------
# État de la configuration (sans jamais exposer de secret)
# ---------------------------------------------------------------------------
def liluvine_configure() -> bool:
    """Vrai si l'URL et la clé de la transmission universelle sont saisies."""
    s = get_settings()
    return bool((s.liluvine_wa_url or "").strip() and (s.liluvine_wa_hmac or "").strip())


def emetteur() -> str:
    """Code émetteur d'adLyn chez SAWALI (pas secret)."""
    return (get_settings().liluvine_wa_emetteur or "adlyn").strip() or "adlyn"


def etat() -> dict:
    """État lisible de la transmission (écran / route d'administration)."""
    return {"waba_plateforme_configure": envois.whatsapp_configure(),
            "liluvine_configure": liluvine_configure(), "emetteur": emetteur()}


# ---------------------------------------------------------------------------
# Paramètres WABA d'une boutique
# ---------------------------------------------------------------------------
async def _charger_boutique(boutique: Union[dict, str, None]) -> Optional[dict]:
    """Accepte la fiche boutique (dict) ou son identifiant (lu en base)."""
    if not boutique:
        return None
    if isinstance(boutique, dict):
        return boutique
    from db import SANS_ID, db  # import local : inutile pour les envois sans boutique

    return await db.boutiques.find_one({"id": str(boutique)}, SANS_ID)


def waba_boutique(boutique: Optional[dict]) -> Optional[tuple[str, str]]:
    """(phone_number_id, access_token) du compte WABA PROPRE à la boutique, ou None.
    Champ de la fiche boutique : « whatsapp_waba » = {"phone_number_id", "access_token"
    (chiffré comme les autres secrets en base), "actif" (vrai par défaut)}."""
    conf = (boutique or {}).get("whatsapp_waba") or {}
    if not isinstance(conf, dict) or conf.get("actif", True) is False:
        return None
    phone_number_id = str(conf.get("phone_number_id") or "").strip()
    jeton = envois.dechiffrer(conf.get("access_token") or "") if conf.get("access_token") else ""
    return (phone_number_id, jeton) if phone_number_id and jeton else None


def source_par_defaut(boutique: Optional[dict]) -> str:
    """Libellé affiché au destinataire : « adLyn — <boutique> » ou « adLyn »."""
    nom = ((boutique or {}).get("nom") or "").strip()
    return f"adLyn — {nom}" if nom else "adLyn"


# ---------------------------------------------------------------------------
# Transmission WA Universelle Liluvine (protocole v2)
# ---------------------------------------------------------------------------
def signer(cle: str, horodatage: str, corps_brut: bytes) -> str:
    """X-Signature = hex(HMAC-SHA256(clé, "<timestamp>.<corps brut>"))."""
    return hmac.new(cle.encode(), horodatage.encode() + b"." + corps_brut, hashlib.sha256).hexdigest()


async def envoyer_liluvine(numero: str, message: str, *, source: Optional[str] = None,
                           id_message: Optional[str] = None) -> dict:
    """Appel signé vers SAWALI. Un seul nouvel essai (même id, nouvelle signature)
    sur erreur réseau ou réponse 5xx ; aucun nouvel essai sur 4xx."""
    s = get_settings()
    if not liluvine_configure():
        return _resultat(False, None, statut="NON_CONFIGURE",
                         erreur="Transmission WA Universelle non configurée (LILUVINE_WA_URL, LILUVINE_WA_HMAC)")
    chiffres = envois.msisdn(numero)
    if not chiffres:
        return _resultat(False, None, statut="NON_CONFIGURE", erreur="Numéro de téléphone absent ou invalide")
    texte = (message or "").strip()
    if not texte:
        return _resultat(False, None, statut="NON_CONFIGURE",
                         erreur="Aucun texte à transmettre (la transmission universelle n'envoie que du texte)")
    # Corps sérialisé UNE SEULE FOIS : ce sont exactement ces octets qui sont signés et envoyés
    corps = {"id": id_message or str(uuid.uuid4()), "to": "+" + chiffres, "message": texte[:LONGUEUR_MAX]}
    if source:
        corps["source"] = source[:120]
    corps_brut = json.dumps(corps, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    url, cle = s.liluvine_wa_url.strip(), s.liluvine_wa_hmac.strip()

    derniere_erreur = "Erreur inconnue"
    async with httpx.AsyncClient(timeout=DELAI_LILUVINE) as client:
        for essai in (1, 2):
            # Horodatage et signature recalculés à chaque essai (même id => pas de doublon)
            horodatage = str(int(time.time()))
            entetes = {"Content-Type": "application/json", "X-Emetteur": emetteur(),
                       "X-Timestamp": horodatage, "X-Signature": signer(cle, horodatage, corps_brut)}
            try:
                r = await client.post(url, content=corps_brut, headers=entetes)
            except httpx.HTTPError as exc:
                derniere_erreur = f"Erreur réseau : {type(exc).__name__}"
                logger.warning("Transmission Liluvine (essai %s) vers %s… : %s", essai, chiffres[:5], derniere_erreur)
                continue  # nouvel essai
            if r.status_code == 200:
                try:
                    donnees = r.json()
                except ValueError:
                    donnees = {}
                if donnees.get("ok", True):
                    return _resultat(True, "liluvine", message_id=donnees.get("message_id"))
                return _resultat(False, "liluvine", erreur=str(donnees.get("detail") or "Envoi refusé")[:200])
            derniere_erreur = f"HTTP {r.status_code} {r.text[:150]}"
            logger.warning("Transmission Liluvine (essai %s) vers %s… : HTTP %s", essai, chiffres[:5], r.status_code)
            if r.status_code < 500:
                break  # 4xx : données ou signature refusées, inutile de réessayer
    return _resultat(False, "liluvine", erreur=derniere_erreur[:300])


# ---------------------------------------------------------------------------
# Point d'entrée unique
# ---------------------------------------------------------------------------
async def envoyer_whatsapp(numero: str, message: str, *, boutique: Union[dict, str, None] = None,
                           source: Optional[str] = None, variables: Optional[list[str]] = None,
                           modele: Optional[str] = None, composants: Optional[list] = None) -> dict:
    """Envoie un WhatsApp en appliquant l'ordre de priorité (voir en-tête du module).
    `boutique` : fiche ou identifiant de la boutique concernée (None = message de la
    plateforme). `variables` / `modele` / `composants` : modèle Meta, utilisés par les
    comptes WABA ; la transmission universelle n'envoie que `message` (texte)."""
    try:
        fiche = await _charger_boutique(boutique)
        # 1) Compte WABA propre à la boutique
        identifiants = waba_boutique(fiche)
        if identifiants:
            statut, erreur, mid = await envois.envoyer_whatsapp_waba(
                numero, variables or [], message, modele=modele, composants=composants, identifiants=identifiants)
            return _resultat(statut == "ENVOYE", "waba_boutique", message_id=mid, erreur=erreur or None, statut=statut)
        # 2) Compte WABA de la plateforme adLyn
        if envois.whatsapp_configure():
            statut, erreur, mid = await envois.envoyer_whatsapp_waba(
                numero, variables or [], message, modele=modele, composants=composants)
            return _resultat(statut == "ENVOYE", "waba_plateforme", message_id=mid, erreur=erreur or None,
                             statut=statut)
        # 3) À défaut : Transmission WA Universelle Liluvine
        return await envoyer_liluvine(numero, message, source=source or source_par_defaut(fiche))
    except Exception as exc:  # noqa: BLE001 — un envoi WhatsApp ne doit jamais casser l'appelant
        logger.warning("Transmission WA impossible : %s", type(exc).__name__)
        return _resultat(False, None, erreur="Erreur inattendue lors de l'envoi WhatsApp")
