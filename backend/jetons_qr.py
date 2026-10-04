"""Jetons CHIFFRÉS et SIGNÉS des QR codes imprimés sur les factures et proformas,
et jetons des sessions de l'« espace client » public.

Pourquoi un jeton chiffré : le QR code d'une facture mène à la page publique de la
boutique et doit permettre de reconnaître le client SANS jamais montrer son numéro
de téléphone. Le jeton contient :
  - b : identifiant de la boutique ;
  - c : identifiant du client ;
  - e : EMPREINTE du téléphone du client (HMAC-SHA256 salé par la boutique, avec une
        clé secrète du serveur) — jamais le numéro lui-même ;
  - n : numéro du document, d : date d'émission, i : identifiant du document.
Le tout est chiffré ET signé avec Fernet (AES-128-CBC + HMAC-SHA256, bibliothèque
« cryptography ») : illisible, infalsifiable (toute modification est refusée) et non
devinable (vecteur d'initialisation aléatoire à chaque création).

CLÉ : variable d'environnement QR_JETONS_CLE (générée par Render, « generateValue »).
Repli sûr si elle est absente : clé DÉRIVÉE de JWT_SECRET (déjà secrète), avec un
libellé propre aux QR codes pour qu'elle ne serve à rien d'autre. Attention : changer
QR_JETONS_CLE (ou JWT_SECRET en l'absence de QR_JETONS_CLE) rend illisibles les QR codes
déjà imprimés (le client peut toujours utiliser « Mon espace » depuis la vitrine).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from config import get_settings
from utils import normaliser_telephone, telephone_e164

VERSION_JETON = 1


# ---------------------------------------------------------------------------
# Clés (jamais affichées ni journalisées)
# ---------------------------------------------------------------------------
def _materiau() -> str:
    """Secret de base : QR_JETONS_CLE, sinon JWT_SECRET (repli documenté ci-dessus)."""
    s = get_settings()
    propre = (s.qr_jetons_cle or "").strip()
    return f"qr:{propre}" if propre else f"jwt:{s.jwt_secret}"


def _derivee(usage: str) -> bytes:
    """Clé de 32 octets dérivée du secret de base pour un USAGE précis (chiffrement,
    empreinte, session...) : une clé ne sert jamais à deux choses différentes."""
    return hashlib.sha256(f"adlyn|{usage}|v1|{_materiau()}".encode()).digest()


def _fernet(usage: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_derivee(usage)))


# ---------------------------------------------------------------------------
# Téléphone : forme canonique et empreinte
# ---------------------------------------------------------------------------
def telephone_canonique(telephone: Optional[str]) -> str:
    """Forme unique d'un numéro pour les comparaisons : « +22670112233 » (E.164),
    sinon les seuls chiffres. « 70 11 22 33 », « 0022670112233 » et « +226 70 11 22 33 »
    donnent la même valeur."""
    return telephone_e164(telephone) or normaliser_telephone(telephone).lstrip("+")


def empreinte_telephone(boutique_id: str, telephone: Optional[str]) -> str:
    """Empreinte (« hash salé ») du numéro : HMAC-SHA256 avec une clé secrète du serveur,
    salé par la boutique. Impossible de retrouver le numéro à partir de l'empreinte."""
    canonique = telephone_canonique(telephone)
    if not canonique:
        return ""
    return hmac.new(_derivee("empreinte-telephone"), f"{boutique_id}|{canonique}".encode(),
                    hashlib.sha256).hexdigest()[:32]


def empreintes_egales(a: str, b: str) -> bool:
    """Comparaison à temps constant (ne laisse rien deviner par la durée)."""
    return bool(a) and bool(b) and hmac.compare_digest(a, b)


def hacher(usage: str, valeur: str) -> str:
    """Empreinte HMAC d'une valeur secrète (code reçu, identifiant de session...)."""
    return hmac.new(_derivee(usage), valeur.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Chiffrement / déchiffrement d'un contenu
# ---------------------------------------------------------------------------
def _chiffrer(usage: str, contenu: dict) -> str:
    brut = json.dumps(contenu, separators=(",", ":"), ensure_ascii=True).encode()
    # Le jeton Fernet est déjà en base64 « URL » ; les « = » de fin sont retirés (adresse plus courte)
    return _fernet(usage).encrypt(brut).decode().rstrip("=")


def _dechiffrer(usage: str, jeton: str, duree_max: Optional[int] = None) -> Optional[dict]:
    """Contenu du jeton, ou None s'il est falsifié, illisible ou trop ancien."""
    jeton = (jeton or "").strip()
    if not jeton or len(jeton) > 2000:
        return None
    try:
        brut = _fernet(usage).decrypt((jeton + "=" * (-len(jeton) % 4)).encode(), ttl=duree_max)
        contenu = json.loads(brut)
    except (InvalidToken, ValueError, TypeError):
        return None
    return contenu if isinstance(contenu, dict) else None


# ---------------------------------------------------------------------------
# Jeton du QR code d'un document
# ---------------------------------------------------------------------------
def creer_jeton_document(boutique: dict, doc: dict) -> str:
    """Jeton chiffré imprimé dans le QR code d'une facture / proforma."""
    telephone = (doc.get("client") or {}).get("telephone") or ""
    return _chiffrer("qr-document", {
        "v": VERSION_JETON, "b": boutique["id"], "c": doc.get("client_id") or "",
        "e": empreinte_telephone(boutique["id"], telephone),
        "n": doc.get("numero") or "", "d": doc.get("date") or "", "i": doc.get("id") or "",
    })


def lire_jeton_document(jeton: str) -> Optional[dict]:
    """Contenu vérifié d'un jeton de QR code, ou None (falsifié / illisible)."""
    contenu = _dechiffrer("qr-document", jeton)
    if not contenu or contenu.get("v") != VERSION_JETON or not contenu.get("b"):
        return None
    return contenu


def url_qr(jeton: str) -> str:
    """Adresse encodée dans le QR code : page « /q/<jeton> » du site public."""
    return f"{get_settings().public_site_url}/q/{jeton}"


# ---------------------------------------------------------------------------
# Jeton de session de l'espace client (chiffré, durée vérifiée en base)
# ---------------------------------------------------------------------------
def creer_jeton_session(sid: str, boutique_id: str, client_id: str) -> str:
    return _chiffrer("session-espace-client", {"v": VERSION_JETON, "s": sid, "b": boutique_id, "c": client_id})


def lire_jeton_session(jeton: str, duree_max: int) -> Optional[dict]:
    contenu = _dechiffrer("session-espace-client", jeton, duree_max=duree_max)
    if not contenu or contenu.get("v") != VERSION_JETON or not contenu.get("s"):
        return None
    return contenu
