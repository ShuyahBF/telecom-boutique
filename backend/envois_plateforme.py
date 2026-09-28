"""Envois de la PLATEFORME adLyn (distincts de la messagerie de chaque boutique) :
  - e-mail par le serveur SMTP de la plateforme (PLATEFORME_SMTP_*) :
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
def email_configure() -> bool:
    return bool(get_settings().plateforme_smtp_hote)


def envoyer_smtp(sujet: str, corps: str, destinataire: str) -> None:
    """Envoi SYNCHRONE (à appeler dans un thread) ; lève une exception en cas d'échec."""
    s = get_settings()
    msg = EmailMessage()
    msg["Subject"], msg["To"] = sujet, destinataire
    msg["From"] = s.plateforme_expediteur or s.plateforme_smtp_utilisateur
    msg.set_content(corps)
    if s.plateforme_smtp_ssl:
        serveur = smtplib.SMTP_SSL(s.plateforme_smtp_hote, s.plateforme_smtp_port, timeout=20)
    else:
        serveur = smtplib.SMTP(s.plateforme_smtp_hote, s.plateforme_smtp_port, timeout=20)
        serveur.starttls()
    with serveur:
        if s.plateforme_smtp_utilisateur:
            serveur.login(s.plateforme_smtp_utilisateur, s.plateforme_smtp_mot_de_passe or "")
        serveur.send_message(msg)


async def envoyer_email(sujet: str, corps: str, destinataire: str) -> tuple[str, str]:
    """E-mail de la plateforme -> (statut, erreur)."""
    if not destinataire:
        return "NON_CONFIGURE", "Aucune adresse e-mail"
    if not email_configure():
        return "NON_CONFIGURE", "PLATEFORME_SMTP_HOTE non configuré"
    try:
        await asyncio.to_thread(envoyer_smtp, sujet, corps, destinataire)
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


async def _sms_ovh(numero: str, texte: str) -> bool:
    """OVH : requête signée « $1$ » + SHA1(secret+consumer+méthode+url+corps+horodatage)."""
    s = get_settings()
    hote = "https://ca.api.ovh.com/1.0" if (s.ovh_sms_endpoint or "").lower() == "ovh-ca" else "https://eu.api.ovh.com/1.0"
    url = f"{hote}/sms/{s.ovh_sms_service_name}/jobs"
    corps = json.dumps({"charset": "UTF-8", "class": "phoneDisplay", "coding": "8bit", "message": texte,
                        "noStopClause": True, "priority": "high", "receivers": [f"+{numero}"],
                        "senderForResponse": False, "sender": s.ovh_sms_sender or "adLyn", "validityPeriod": 60})
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


async def envoyer_whatsapp(telephone: str, variables: list[str], texte: str) -> tuple[str, str]:
    """Message WhatsApp -> (statut, erreur).
    1) MODÈLE approuvé (WHATSAPP_RAPPEL_TEMPLATE) avec ses variables : seul moyen
       d'écrire à quelqu'un qui n'a pas écrit au numéro dans les dernières 24 h ;
    2) en repli, message texte libre (ne passe que dans cette fenêtre de 24 h)."""
    s = get_settings()
    numero = msisdn(telephone)
    if not numero:
        return "NON_CONFIGURE", "Numéro de téléphone absent ou invalide"
    if not whatsapp_configure():
        return "NON_CONFIGURE", "WhatsApp non configuré (WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID)"
    url = WA_GRAPH_URL.format(phone_number_id=s.whatsapp_phone_number_id)
    entetes = {"Authorization": f"Bearer {s.whatsapp_access_token}"}
    essais = []
    if (s.whatsapp_rappel_template or "").strip():
        essais.append({"messaging_product": "whatsapp", "to": numero, "type": "template", "template": {
            "name": s.whatsapp_rappel_template.strip(), "language": {"code": s.whatsapp_template_langue},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": v[:200]} for v in variables]}]}})
    essais.append({"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": texte[:4000]}})
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
