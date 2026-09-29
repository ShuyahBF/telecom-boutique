"""TikTok : connexion du compte TikTok d'une boutique (Login Kit, OAuth v2) et
publication de photos de produits (Content Posting API, Direct Post).

Règles TikTok appliquées ici et dans l'écran de publication (vérifiées lors de
la revue et de l'audit de l'app) :
  - chaque boutique connecte SON compte ; les jetons sont chiffrés en base ;
  - avant chaque publication, `creator_info/query` donne les visibilités
    autorisées : l'utilisateur en choisit une (aucune valeur par défaut) ;
  - « Branded content » est incompatible avec la visibilité « Only me » ;
  - aucun filigrane n'est ajouté ; la publication n'a lieu qu'après accord
    explicite ; son état est suivi par `status/fetch`.
Documentation : https://developers.tiktok.com/doc/content-posting-api-get-started
"""
from __future__ import annotations

import base64
import hashlib
import io
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from config import get_settings

URL_AUTORISATION = "https://www.tiktok.com/v2/auth/authorize/"
URL_JETON = "https://open.tiktokapis.com/v2/oauth/token/"
URL_REVOCATION = "https://open.tiktokapis.com/v2/oauth/revoke/"
URL_PROFIL = "https://open.tiktokapis.com/v2/user/info/"
URL_CREATEUR = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
URL_PUBLICATION = "https://open.tiktokapis.com/v2/post/publish/content/init/"
URL_STATUT = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
# Droits demandés : nom + avatar du compte, publication directe. Rien d'autre.
SCOPES = "user.info.basic,video.publish"
# Photo acceptée par TikTok : JPEG ou WebP, 1080 px au plus
TAILLE_PHOTO_MAX = 1080


def configure() -> bool:
    s = get_settings()
    return bool(s.tiktok_client_key and s.tiktok_client_secret)


def redirect_uri() -> str:
    """Adresse de retour déclarée dans le portail TikTok (identique, au caractère près)."""
    s = get_settings()
    return s.tiktok_redirect_uri or f"{s.public_base_url.rstrip('/')}/api/tiktok/callback"


# ---------------------------------------------------------------------------
# Chiffrement des jetons TikTok en base (Fernet = AES-128-CBC + HMAC)
# ---------------------------------------------------------------------------
def _fernet() -> Fernet:
    s = get_settings()
    if s.tiktok_jetons_cle:
        return Fernet(s.tiktok_jetons_cle.encode())
    # Repli : clé dérivée du secret des sessions (définir TIKTOK_JETONS_CLE en production)
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(f"tiktok:{s.jwt_secret}".encode()).digest()))


def chiffrer(valeur: str) -> str:
    return _fernet().encrypt(valeur.encode()).decode()


def dechiffrer(valeur: str) -> str:
    try:
        return _fernet().decrypt(valeur.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(409, "Connexion TikTok à refaire (clé de chiffrement modifiée)") from exc


# ---------------------------------------------------------------------------
# OAuth : état signé (anti-CSRF) et échange du code
# ---------------------------------------------------------------------------
def etat_signe(boutique_id: str, user_id: str) -> str:
    """Paramètre « state » : signé et valable 10 minutes. Il porte la boutique,
    lue ensuite côté serveur (jamais depuis un paramètre libre du navigateur)."""
    s = get_settings()
    return jwt.encode({"b": boutique_id, "u": user_id, "t": "tiktok",
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, s.jwt_secret, algorithm=s.jwt_algorithm)


def lire_etat(etat: str) -> Optional[dict]:
    s = get_settings()
    try:
        donnees = jwt.decode(etat, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    return donnees if donnees.get("t") == "tiktok" else None


def url_autorisation(etat: str) -> str:
    s = get_settings()
    return f"{URL_AUTORISATION}?" + urlencode({
        "client_key": s.tiktok_client_key, "scope": SCOPES, "response_type": "code",
        "redirect_uri": redirect_uri(), "state": etat})


def _erreur_tiktok(reponse: httpx.Response, contexte: str) -> HTTPException:
    """Message lisible à partir d'une réponse d'erreur TikTok."""
    try:
        corps = reponse.json()
        err = corps.get("error") or {}
        detail = (err.get("message") if isinstance(err, dict) else None) or corps.get("error_description") or ""
        code = err.get("code") if isinstance(err, dict) else err
    except ValueError:
        detail, code = reponse.text[:200], ""
    if code == "unaudited_client_can_only_post_to_private_accounts":
        return HTTPException(409, "Application TikTok pas encore auditée : publiez depuis un compte TikTok PRIVÉ, "
                                  "avec la visibilité « Moi uniquement ».")
    return HTTPException(502, f"TikTok ({contexte}) : {detail or code or reponse.status_code}")


async def _post_formulaire(url: str, donnees: dict, contexte: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, data=donnees, headers={"Content-Type": "application/x-www-form-urlencoded"})
    corps = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400 or corps.get("error"):
        raise _erreur_tiktok(r, contexte)
    return corps


async def echanger_code(code: str) -> dict:
    s = get_settings()
    return await _post_formulaire(URL_JETON, {
        "client_key": s.tiktok_client_key, "client_secret": s.tiktok_client_secret, "code": code,
        "grant_type": "authorization_code", "redirect_uri": redirect_uri()}, "connexion")


async def rafraichir(refresh_token: str) -> dict:
    s = get_settings()
    return await _post_formulaire(URL_JETON, {
        "client_key": s.tiktok_client_key, "client_secret": s.tiktok_client_secret,
        "grant_type": "refresh_token", "refresh_token": refresh_token}, "renouvellement")


async def revoquer(access_token: str) -> None:
    s = get_settings()
    try:
        await _post_formulaire(URL_REVOCATION, {"client_key": s.tiktok_client_key,
                                                "client_secret": s.tiktok_client_secret, "token": access_token}, "révocation")
    except HTTPException:
        pass  # le compte est de toute façon retiré côté adLyn


def fiche_jetons(reponse: dict) -> dict:
    """Champs à enregistrer (chiffrés) à partir de la réponse de /oauth/token/."""
    maintenant = datetime.now(timezone.utc)
    return {
        "open_id": reponse.get("open_id"),
        "access_token": chiffrer(reponse["access_token"]),
        "refresh_token": chiffrer(reponse["refresh_token"]),
        "expire_le": (maintenant + timedelta(seconds=int(reponse.get("expires_in", 86400)))).isoformat(),
        "refresh_expire_le": (maintenant + timedelta(seconds=int(reponse.get("refresh_expires_in", 31536000)))).isoformat(),
        "scopes": reponse.get("scope", SCOPES),
    }


async def _appel_json(url: str, access_token: str, corps: Optional[dict] = None, params: Optional[dict] = None,
                      contexte: str = "") -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, params=params, json=corps or {}, headers={
            "Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"})
    try:
        donnees = r.json()
    except ValueError:
        donnees = {}
    erreur = donnees.get("error") or {}
    if r.status_code >= 400 or (isinstance(erreur, dict) and erreur.get("code") not in (None, "", "ok")):
        raise _erreur_tiktok(r, contexte)
    return donnees.get("data") or {}


async def profil(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(URL_PROFIL, params={"fields": "open_id,avatar_url,display_name"},
                             headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code >= 400:
        raise _erreur_tiktok(r, "profil")
    return (r.json().get("data") or {}).get("user") or {}


async def infos_createur(access_token: str) -> dict:
    """Nom, avatar, visibilités autorisées et interactions désactivées du créateur."""
    return await _appel_json(URL_CREATEUR, access_token, contexte="infos du compte")


async def publier_photos(access_token: str, *, urls: list[str], titre: str, description: str, visibilite: str,
                         desactiver_commentaires: bool, ma_marque: bool, contenu_sponsorise: bool) -> str:
    """Publication directe de photos (PULL_FROM_URL : domaine vérifié dans le portail TikTok)."""
    corps = {
        "post_info": {
            "title": titre, "description": description, "privacy_level": visibilite,
            "disable_comment": desactiver_commentaires, "auto_add_music": True,
            "brand_organic_toggle": ma_marque, "brand_content_toggle": contenu_sponsorise,
        },
        "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": urls},
        "post_mode": "DIRECT_POST", "media_type": "PHOTO",
    }
    data = await _appel_json(URL_PUBLICATION, access_token, corps, contexte="publication")
    return data.get("publish_id", "")


async def statut_publication(access_token: str, publish_id: str) -> dict:
    return await _appel_json(URL_STATUT, access_token, {"publish_id": publish_id}, contexte="statut")


async def telecharger(url: str) -> bytes:
    """Contenu d'une photo publique (bucket R2 ou fichiers locaux de l'API)."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


def photo_pour_tiktok(contenu: bytes) -> bytes:
    """Copie JPEG de la photo, 1080 px au plus sur le grand côté (format accepté par TikTok).
    Aucun texte ni logo n'est ajouté à l'image."""
    from PIL import Image

    image = Image.open(io.BytesIO(contenu))
    if image.mode in ("RGBA", "LA", "P"):
        # PNG transparent : on pose l'image sur un fond blanc (sinon la transparence deviendrait noire)
        image = image.convert("RGBA")
        fond = Image.new("RGB", image.size, (255, 255, 255))
        fond.paste(image, mask=image.getchannel("A"))
        image = fond
    else:
        image = image.convert("RGB")
    image.thumbnail((TAILLE_PHOTO_MAX, TAILLE_PHOTO_MAX))
    sortie = io.BytesIO()
    image.save(sortie, "JPEG", quality=90, optimize=True)
    return sortie.getvalue()
