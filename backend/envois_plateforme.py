"""Envois de la PLATEFORME adLyn (distincts de la messagerie de chaque boutique) :
  - e-mail par l'API Resend (RESEND_API_KEY, prioritaire : le SMTP est bloqué
    depuis Render), sinon par le serveur SMTP de la plateforme (PLATEFORME_SMTP_*) :
    rapport de la nuit, identifiants d'une nouvelle boutique... ;
  - SMS par Orange SMS API, avec OVH en repli (même code que beauthentik.net).

Aucune fonction ne lève d'exception vers l'appelant : chacune renvoie un
statut ("ENVOYE", "ECHEC" ou "NON_CONFIGURE") et un message d'erreur, pour
que l'appelant puisse l'enregistrer dans son journal.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import smtplib
import urllib.parse
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Optional

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

WA_GRAPH_URL = "https://graph.facebook.com/v21.0/{phone_number_id}/messages"
ORANGE_OAUTH_URL = "https://api.orange.com/oauth/v3/token"
ORANGE_SMS_URL = "https://api.orange.com/smsmessaging/v1/outbound/{sender}/requests"
_jeton_orange: dict = {}  # jeton OAuth Orange gardé en mémoire jusqu'à son expiration


# ---------------------------------------------------------------------------
# E-mail (serveur SMTP de la plateforme)
# ---------------------------------------------------------------------------
# Le serveur d'envoi se règle dans l'administration (/plateforme/parametres) ; il est
# gardé en base (mot de passe chiffré). À défaut, les variables PLATEFORME_SMTP_*.
def _cle_chiffrement() -> bytes:
    """Clé de chiffrement des secrets gardés en base, dérivée de JWT_SECRET."""
    return base64.urlsafe_b64encode(hashlib.sha256(("adlyn-secrets|" + get_settings().jwt_secret).encode()).digest())


def chiffrer(valeur: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_cle_chiffrement()).encrypt(valeur.encode()).decode()


def dechiffrer(valeur: str) -> str:
    from cryptography.fernet import Fernet, InvalidToken
    try:
        return Fernet(_cle_chiffrement()).decrypt(valeur.encode()).decode()
    except (InvalidToken, ValueError):
        return ""  # clé changée : le mot de passe est à ressaisir


async def config_smtp() -> dict:
    """Réglages en vigueur : ceux de l'administration, sinon les variables d'environnement."""
    from db import db
    doc = await db.parametres_plateforme.find_one({"_id": "smtp"}) or {}
    if doc.get("hote"):
        return {"hote": doc["hote"], "port": int(doc.get("port") or 587), "utilisateur": doc.get("utilisateur", ""),
                "mot_de_passe": dechiffrer(doc.get("mot_de_passe_chiffre", "")) if doc.get("mot_de_passe_chiffre") else "",
                "expediteur": doc.get("expediteur", ""), "nom_expediteur": doc.get("nom_expediteur", "adLyn"),
                "ssl": bool(doc.get("ssl")), "actif": doc.get("actif", True), "source": "administration"}
    s = get_settings()
    return {"hote": s.plateforme_smtp_hote or "", "port": s.plateforme_smtp_port, "utilisateur": s.plateforme_smtp_utilisateur or "",
            "mot_de_passe": s.plateforme_smtp_mot_de_passe or "", "expediteur": s.plateforme_expediteur or "",
            "nom_expediteur": "adLyn", "ssl": s.plateforme_smtp_ssl, "actif": bool(s.plateforme_smtp_hote),
            "source": "variables d'environnement"}


def email_configure() -> bool:
    return resend_configure() or bool(get_settings().plateforme_smtp_hote)


# ---------------------------------------------------------------------------
# E-mail par l'API Resend (HTTPS, port 443 : jamais bloqué par Render)
# ---------------------------------------------------------------------------
RESEND_URL = "https://api.resend.com/emails"


def resend_configure() -> bool:
    """Vrai si la clé ET l'adresse d'envoi Resend sont renseignées dans Render."""
    s = get_settings()
    return bool(s.resend_api_key and s.resend_expediteur)


def resend_expediteur() -> str:
    """Adresse d'envoi Resend (domaine validé), sans le nom affiché."""
    return (get_settings().resend_expediteur or "").strip()


async def envoyer_resend(sujet: str, corps: str, destinataire: str, nom_expediteur: str = "adLyn",
                         reponse_a: Optional[str] = None) -> None:
    """Envoie un e-mail texte par l'API Resend ; lève une exception en cas d'échec.
    `nom_expediteur` : nom affiché (ex. nom de la boutique), l'adresse reste celle du
    domaine validé ; `reponse_a` : adresse qui recevra les réponses (ex. celle de la boutique)."""
    from email.utils import formataddr
    # Nom affiché nettoyé : pas de retour à la ligne ni de caractères d'en-tête
    nom = " ".join((nom_expediteur or "adLyn").replace("<", "").replace(">", "").split())[:60] or "adLyn"
    charge = {"from": formataddr((nom, resend_expediteur())), "to": [destinataire],
              "subject": sujet, "text": corps}
    if reponse_a:
        charge["reply_to"] = reponse_a
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(RESEND_URL, json=charge,
                              headers={"Authorization": f"Bearer {get_settings().resend_api_key}"})
    if r.status_code >= 300:
        # Message d'erreur de Resend (jamais la clé) : ex. « domain is not verified »
        try:
            detail = r.json().get("message") or r.text
        except ValueError:
            detail = r.text
        raise RuntimeError(f"Resend {r.status_code} : {str(detail)[:250]}")


def envoyer_smtp(sujet: str, corps: str, destinataire: str, c: Optional[dict] = None) -> None:
    """Envoi SYNCHRONE (à appeler dans un thread) ; lève une exception en cas d'échec.
    `c` : réglages (config_smtp) ; à défaut, variables d'environnement."""
    if c is None:
        s = get_settings()
        c = {"hote": s.plateforme_smtp_hote, "port": s.plateforme_smtp_port, "utilisateur": s.plateforme_smtp_utilisateur,
             "mot_de_passe": s.plateforme_smtp_mot_de_passe, "expediteur": s.plateforme_expediteur,
             "nom_expediteur": "adLyn", "ssl": s.plateforme_smtp_ssl}
    from email.utils import formataddr
    msg = EmailMessage()
    msg["Subject"], msg["To"] = sujet, destinataire
    msg["From"] = formataddr((c.get("nom_expediteur") or "adLyn", c.get("expediteur") or c.get("utilisateur") or ""))
    msg.set_content(corps)
    if c.get("ssl"):
        serveur = smtplib.SMTP_SSL(c["hote"], int(c["port"]), timeout=20)
    else:
        serveur = smtplib.SMTP(c["hote"], int(c["port"]), timeout=20)
        serveur.starttls()
    with serveur:
        if c.get("utilisateur"):
            serveur.login(c["utilisateur"], c.get("mot_de_passe") or "")
        serveur.send_message(msg)


async def envoyer_email(sujet: str, corps: str, destinataire: str) -> tuple[str, str]:
    """E-mail de la plateforme -> (statut, erreur)."""
    if not destinataire:
        return "NON_CONFIGURE", "Aucune adresse e-mail"
    if resend_configure():
        # Resend en priorité : le SMTP ne passe pas depuis Render
        try:
            await envoyer_resend(sujet, corps, destinataire)
            return "ENVOYE", ""
        except Exception as exc:  # noqa: BLE001 — l'échec est rapporté, pas propagé
            logger.warning("E-mail plateforme (Resend) vers %s en échec : %s", destinataire, exc)
            return "ECHEC", str(exc)[:300]
    c = await config_smtp()
    if not (c["hote"] and c["actif"]):
        return "NON_CONFIGURE", "Serveur d'envoi de la plateforme non réglé (Plateforme > Paramètres)"
    try:
        await asyncio.to_thread(envoyer_smtp, sujet, corps, destinataire, c)
        return "ENVOYE", ""
    except Exception as exc:  # noqa: BLE001 — l'échec est rapporté, pas propagé
        logger.warning("E-mail plateforme vers %s en échec : %s", destinataire, exc)
        return "ECHEC", str(exc)[:300]


# ---------------------------------------------------------------------------
# SMS : Orange (fournisseur principal pour le Burkina Faso), OVH en repli
# ---------------------------------------------------------------------------
def orange_configure() -> bool:
    s = get_settings()
    return bool(s.orange_sms_client_id and s.orange_sms_client_secret and s.orange_sms_sender_msisdn)


def ovh_configure() -> bool:
    s = get_settings()
    return bool(s.ovh_sms_application_key and s.ovh_sms_application_secret
                and s.ovh_sms_consumer_key and s.ovh_sms_service_name)


def msisdn(telephone: str, indicatif_defaut: str = "226") -> Optional[str]:
    """« +226 70 12 34 56 » ou « 70123456 » -> « 22670123456 » (format international sans +).
    Un numéro local à 8 chiffres reçoit l'indicatif du Burkina Faso."""
    tel = (telephone or "").strip()
    chiffres = "".join(c for c in tel if c.isdigit())
    if tel.startswith("00"):
        chiffres = chiffres[2:]
    elif not tel.startswith("+") and len(chiffres) == 8:
        chiffres = indicatif_defaut + chiffres
    return chiffres if 8 <= len(chiffres) <= 15 else None


async def _jeton_oauth_orange(client: httpx.AsyncClient, forcer: bool = False) -> Optional[str]:
    """Jeton OAuth2 Orange, mis en cache jusqu'à 1 minute avant son expiration."""
    maintenant = datetime.now(timezone.utc).timestamp()
    if not forcer and _jeton_orange.get("jeton") and float(_jeton_orange.get("expire", 0)) > maintenant:
        return str(_jeton_orange["jeton"])
    s = get_settings()
    basic = base64.b64encode(f"{s.orange_sms_client_id}:{s.orange_sms_client_secret}".encode()).decode()
    r = await client.post(ORANGE_OAUTH_URL, data={"grant_type": "client_credentials"},  # corps form-urlencoded exigé
                          headers={"Authorization": f"Basic {basic}", "Accept": "application/json"})
    if r.status_code >= 300:
        logger.warning("OAuth Orange en échec : HTTP %s %s", r.status_code, r.text[:200])
        return None
    doc = r.json()
    _jeton_orange.update({"jeton": doc["access_token"],
                          "expire": maintenant + max(60, int(doc.get("expires_in") or 3600) - 60)})
    return doc["access_token"]


async def _sms_orange(numero: str, texte: str) -> bool:
    s = get_settings()
    emetteur = s.orange_sms_sender_msisdn.strip()
    emetteur = emetteur if emetteur.startswith("+") else f"+{emetteur}"
    url = ORANGE_SMS_URL.format(sender=urllib.parse.quote(f"tel:{emetteur}", safe=""))
    demande = {"address": f"tel:+{numero}", "senderAddress": f"tel:{emetteur}",
               "outboundSMSTextMessage": {"message": texte}}
    if s.orange_sms_sender_name:
        demande["senderName"] = s.orange_sms_sender_name
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            jeton = await _jeton_oauth_orange(client)
            if not jeton:
                return False
            for essai in range(2):
                r = await client.post(url, json={"outboundSMSMessageRequest": demande},
                                      headers={"Authorization": f"Bearer {jeton}", "Accept": "application/json"})
                if r.status_code == 401 and essai == 0:
                    jeton = await _jeton_oauth_orange(client, forcer=True)  # jeton expiré : un seul nouvel essai
                    if not jeton:
                        return False
                    continue
                if 200 <= r.status_code < 300:
                    return True
                logger.warning("SMS Orange vers %s… en échec : HTTP %s %s", numero[:5], r.status_code, r.text[:200])
                return False
    except httpx.HTTPError as exc:
        logger.warning("SMS Orange vers %s… en échec : %r", numero[:5], exc)
    return False


async def _sms_ovh(numero: str, texte: str, expediteur: Optional[str] = None, service: Optional[str] = None) -> bool:
    """OVH : requête signée « $1$ » + SHA1(secret+consumer+méthode+url+corps+horodatage).
    expediteur / service : ceux d'une boutique (sinon ceux de la plateforme)."""
    s = get_settings()
    hote = "https://ca.api.ovh.com/1.0" if (s.ovh_sms_endpoint or "").lower() == "ovh-ca" else "https://eu.api.ovh.com/1.0"
    url = f"{hote}/sms/{service or s.ovh_sms_service_name}/jobs"
    corps = json.dumps({"charset": "UTF-8", "class": "phoneDisplay", "coding": "8bit", "message": texte,
                        "noStopClause": True, "priority": "high", "receivers": [f"+{numero}"],
                        "senderForResponse": False, "sender": expediteur or s.ovh_sms_sender or "adLyn",
                        "validityPeriod": 60})
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # Horloge du serveur OVH (la signature exige son horodatage)
            rt = await client.get(f"{hote}/auth/time")
            ts = rt.text.strip() if rt.status_code == 200 else str(int(datetime.now(timezone.utc).timestamp()))
            a_signer = "+".join([s.ovh_sms_application_secret, s.ovh_sms_consumer_key, "POST", url, corps, ts])
            r = await client.post(url, content=corps, headers={
                "X-Ovh-Application": s.ovh_sms_application_key, "X-Ovh-Consumer": s.ovh_sms_consumer_key,
                "X-Ovh-Timestamp": ts, "X-Ovh-Signature": "$1$" + hashlib.sha1(a_signer.encode()).hexdigest(),
                "Content-Type": "application/json"})
        doc = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code < 300 and not (doc.get("invalidReceivers") and not doc.get("validReceivers")):
            return True
        logger.warning("SMS OVH vers %s… en échec : HTTP %s %s", numero[:5], r.status_code, r.text[:200])
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("SMS OVH vers %s… en échec : %r", numero[:5], exc)
    return False


async def envoyer_sms_ovh(telephone: str, texte: str, expediteur: str, service: Optional[str] = None) -> tuple[str, str]:
    """SMS d'une BOUTIQUE à ses clients, par OVH, avec l'expéditeur déclaré pour elle
    (et son service OVH dédié s'il existe). -> (statut, erreur)."""
    numero = msisdn(telephone)
    if not numero:
        return "ECHEC", "Numéro de téléphone invalide"
    if not ovh_configure():
        return "NON_CONFIGURE", "Compte OVH SMS non configuré (OVH_SMS_*)"
    if await _sms_ovh(numero, texte, expediteur, service):
        return "ENVOYE", ""
    return "ECHEC", "Envoi refusé par OVH (voir les journaux du serveur)"


async def envoyer_sms(telephone: str, texte: str) -> tuple[str, str]:
    """SMS de la plateforme -> (statut, erreur). Orange d'abord pour un numéro
    du Burkina (+226), OVH d'abord ailleurs ; l'autre sert de repli."""
    numero = msisdn(telephone)
    if not numero:
        return "NON_CONFIGURE", "Numéro de téléphone absent ou invalide"
    fournisseurs = [(orange_configure(), _sms_orange), (ovh_configure(), _sms_ovh)]
    if not numero.startswith("226"):
        fournisseurs.reverse()
    actifs = [fn for ok, fn in fournisseurs if ok]
    if not actifs:
        return "NON_CONFIGURE", "Envoi de SMS non configuré (ORANGE_SMS_* ou OVH_SMS_*)"
    for fn in actifs:
        if await fn(numero, texte):
            return "ENVOYE", ""
    return "ECHEC", "Tous les fournisseurs SMS ont échoué"


# ---------------------------------------------------------------------------
# WhatsApp Cloud API (Meta), même compte que beauthentik.net
# ---------------------------------------------------------------------------
def whatsapp_configure() -> bool:
    s = get_settings()
    return bool(s.whatsapp_access_token and s.whatsapp_phone_number_id)


async def envoyer_whatsapp(telephone: str, variables: list[str], texte: str, *, modele: Optional[str] = None,
                           composants: Optional[list] = None) -> tuple[str, str]:
    """Message WhatsApp -> (statut, erreur).
    1) MODÈLE approuvé avec ses variables : seul moyen d'écrire à quelqu'un qui
       n'a pas écrit au numéro dans les dernières 24 h. Par défaut le modèle des
       rappels (WHATSAPP_RAPPEL_TEMPLATE) ; `modele` en désigne un autre ("" = aucun)
       et `composants` remplace les variables du corps (ex. bouton « Copier le code ») ;
    2) en repli, message texte libre `texte` (ne passe que dans cette fenêtre de 24 h ;
       texte vide = pas de repli)."""
    s = get_settings()
    numero = msisdn(telephone)
    if not numero:
        return "NON_CONFIGURE", "Numéro de téléphone absent ou invalide"
    if not whatsapp_configure():
        return "NON_CONFIGURE", "WhatsApp non configuré (WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID)"
    url = WA_GRAPH_URL.format(phone_number_id=s.whatsapp_phone_number_id)
    entetes = {"Authorization": f"Bearer {s.whatsapp_access_token}"}
    essais = []
    nom_modele = (s.whatsapp_rappel_template if modele is None else modele) or ""
    if nom_modele.strip():
        if composants is None:
            composants = [{"type": "body", "parameters": [{"type": "text", "text": v[:200]} for v in variables]}]
        essais.append({"messaging_product": "whatsapp", "to": numero, "type": "template", "template": {
            "name": nom_modele.strip(), "language": {"code": s.whatsapp_template_langue}, "components": composants}})
    if texte:
        essais.append({"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": texte[:4000]}})
    if not essais:
        return "NON_CONFIGURE", "Aucun modèle WhatsApp utilisable"
    erreurs = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for corps in essais:
                r = await client.post(url, json=corps, headers=entetes)
                if r.status_code == 200:
                    return "ENVOYE", ""
                erreurs.append(f"{corps['type']} : HTTP {r.status_code} {r.text[:150]}")
    except httpx.HTTPError as exc:
        erreurs.append(repr(exc))
    logger.warning("WhatsApp vers %s… en échec : %s", numero[:5], " | ".join(erreurs))
    return "ECHEC", " | ".join(erreurs)[:300]
