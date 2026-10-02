"""Envois de la PLATEFORME adLyn (distincts de la messagerie de chaque boutique) :
  - e-mail par le service choisi dans l'écran Plateforme > Paramètres : Resend,
    ZeptoMail (Zoho), Brevo (API HTTPS) ou SMTP (bloqué sur les services Render
    gratuits) ; à défaut, variables d'environnement de repli (RESEND_*, SMTP...) :
    rapport de la nuit, identifiants d'une nouvelle boutique... Les mêmes fonctions
    servent aux boutiques qui ont leur propre service (messagerie.py) ;
  - SMS par Orange SMS API, avec OVH en repli (même code que beauthentik.net).

Les points d'entrée (envoyer_email, envoyer_sms...) ne lèvent pas d'exception : ils renvoient un
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
# E-mail : chiffrement des secrets gardés en base
# ---------------------------------------------------------------------------
# Clés API et mots de passe (plateforme et boutiques) sont gardés CHIFFRÉS en base,
# jamais renvoyés au navigateur (seulement « a_cle » / « a_mot_de_passe »).
def _cle_chiffrement() -> bytes:
    """Clé de chiffrement des secrets gardés en base, dérivée de JWT_SECRET."""
    return base64.urlsafe_b64encode(hashlib.sha256(("adlyn-secrets|" + get_settings().jwt_secret).encode()).digest())


def chiffrer(valeur: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_cle_chiffrement()).encrypt(valeur.encode()).decode()


def dechiffrer(valeur: str) -> str:
    from cryptography.fernet import Fernet, InvalidToken
    if not valeur:
        return ""
    try:
        return Fernet(_cle_chiffrement()).decrypt(valeur.encode()).decode()
    except (InvalidToken, ValueError):
        return ""  # clé changée : le secret est à ressaisir


# ---------------------------------------------------------------------------
# E-mail : les 4 services d'envoi au choix (Resend, ZeptoMail, Brevo, SMTP)
# ---------------------------------------------------------------------------
# Resend, ZeptoMail et Brevo passent par HTTPS (port 443) ; le SMTP utilise les
# ports 25/465/587, BLOQUÉS sur les services Render gratuits (offre payante requise).
FOURNISSEURS_API = ("resend", "zeptomail", "brevo")
FOURNISSEURS = FOURNISSEURS_API + ("smtp",)
NOMS_FOURNISSEURS = {"resend": "Resend", "zeptomail": "ZeptoMail", "brevo": "Brevo", "smtp": "SMTP"}
RESEND_URL = "https://api.resend.com/emails"
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
ZEPTOMAIL_URL = "https://{hote}/v1.1/email"
ZEPTOMAIL_HOTES = ("api.zeptomail.com", "api.zeptomail.eu", "api.zeptomail.in")
PREFIXE_ZEPTOMAIL = "Zoho-enczapikey"
DOC_EMAIL = "smtp"  # document historique de parametres_plateforme, gardé pour la compatibilité


class ErreurEnvoi(RuntimeError):
    """Échec d'un envoi, avec le message du fournisseur (jamais la clé)."""


def nettoyer_nom(nom: Optional[str], defaut: str = "adLyn") -> str:
    """Nom affiché : sans < > ni retour à la ligne, 60 caractères au plus."""
    propre = " ".join(str(nom or "").replace("<", "").replace(">", "").split())[:60].strip()
    return propre or defaut


def hote_zeptomail(hote: Optional[str]) -> str:
    """Région ZeptoMail : .com (défaut), .eu ou .in ; toute autre valeur revient au défaut."""
    hote = (hote or "").strip().lower()
    return hote if hote in ZEPTOMAIL_HOTES else ZEPTOMAIL_HOTES[0]


def _jeton_zeptomail(cle: str) -> str:
    """En-tête ZeptoMail : « Zoho-enczapikey <clé> », sans doubler le préfixe s'il est déjà collé."""
    cle = cle.strip()
    if cle.lower().startswith(PREFIXE_ZEPTOMAIL.lower()):
        return PREFIXE_ZEPTOMAIL + " " + cle[len(PREFIXE_ZEPTOMAIL):].strip()
    return f"{PREFIXE_ZEPTOMAIL} {cle}"


def _message_erreur(fournisseur: str, r: httpx.Response, cle: str) -> str:
    """« <Fournisseur> <code HTTP> : <message du fournisseur> », tronqué à 250 caractères, sans la clé."""
    try:
        doc = r.json()
    except ValueError:
        doc = None
    detail = ""
    if isinstance(doc, dict):
        if fournisseur == "zeptomail" and isinstance(doc.get("error"), dict):
            # ZeptoMail : {"error": {"message": ..., "details": [{"message": ...}]}}
            err = doc["error"]
            morceaux = [err.get("message")] + [d.get("message") for d in err.get("details") or [] if isinstance(d, dict)]
            detail = " : ".join(str(m) for m in morceaux if m)
        else:
            # Resend : {"message": ...} ; Brevo : {"code": ..., "message": ...}
            detail = str(doc.get("message") or "")
    detail = detail or (r.text or "")
    if cle:
        detail = detail.replace(cle, "***")  # par précaution : la clé ne sort jamais
    return f"{NOMS_FOURNISSEURS[fournisseur]} {r.status_code} : {detail}"[:250]


async def envoyer_par_api(fournisseur: str, cle: str, expediteur: str, nom: str, destinataire: str,
                          sujet: str, corps: str, reponse_a: Optional[str] = None,
                          zeptomail_hote: Optional[str] = None) -> None:
    """Envoie un e-mail texte par l'API HTTPS du fournisseur ; lève ErreurEnvoi en cas d'échec.
    `nom` : nom affiché ; `reponse_a` : adresse qui recevra les réponses (facultative)."""
    from email.utils import formataddr
    nom = nettoyer_nom(nom)
    # Requête propre à chaque fournisseur (URL, en-têtes, forme du JSON)
    if fournisseur == "resend":
        url, entetes = RESEND_URL, {"Authorization": f"Bearer {cle}"}
        charge: dict = {"from": formataddr((nom, expediteur)), "to": [destinataire], "subject": sujet, "text": corps}
        if reponse_a:
            charge["reply_to"] = reponse_a
    elif fournisseur == "brevo":
        url, entetes = BREVO_URL, {"api-key": cle, "accept": "application/json"}
        charge = {"sender": {"name": nom, "email": expediteur}, "to": [{"email": destinataire}],
                  "subject": sujet, "textContent": corps}
        if reponse_a:
            charge["replyTo"] = {"email": reponse_a}
    elif fournisseur == "zeptomail":
        url = ZEPTOMAIL_URL.format(hote=hote_zeptomail(zeptomail_hote))
        entetes = {"Authorization": _jeton_zeptomail(cle), "Accept": "application/json"}
        charge = {"from": {"address": expediteur, "name": nom}, "to": [{"email_address": {"address": destinataire}}],
                  "subject": sujet, "textbody": corps}
        if reponse_a:
            charge["reply_to"] = [{"address": reponse_a}]
    else:
        raise ErreurEnvoi(f"Service d'envoi inconnu : {fournisseur}")
    # Appel HTTPS (20 s au plus) ; une coupure réseau est rapportée sans la clé
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=charge, headers=entetes)
    except httpx.HTTPError as exc:
        raise ErreurEnvoi(f"{NOMS_FOURNISSEURS[fournisseur]} : connexion impossible ({type(exc).__name__})") from None
    if r.status_code >= 300:
        raise ErreurEnvoi(_message_erreur(fournisseur, r, cle))


def envoyer_smtp(sujet: str, corps: str, destinataire: str, c: Optional[dict] = None,
                 reponse_a: Optional[str] = None) -> None:
    """Envoi SYNCHRONE par SMTP (à appeler dans un thread) ; lève une exception en cas d'échec.
    `c` : réglages SMTP (config_smtp) ; à défaut, variables d'environnement."""
    if c is None:
        c = _smtp_env()
    from email.utils import formataddr
    msg = EmailMessage()
    msg["Subject"], msg["To"] = sujet, destinataire
    msg["From"] = formataddr((nettoyer_nom(c.get("nom_expediteur")), c.get("expediteur") or c.get("utilisateur") or ""))
    if reponse_a:
        msg["Reply-To"] = reponse_a
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


# ---------------------------------------------------------------------------
# E-mail : réglages de la PLATEFORME (écran Plateforme > Paramètres)
# ---------------------------------------------------------------------------
# Document parametres_plateforme {_id: "smtp"} : fournisseur, actif, expediteur,
# nom_expediteur, zeptomail_hote, cles_chiffrees {resend, zeptomail, brevo} et les
# champs SMTP historiques (hote, port, ssl, utilisateur, mot_de_passe_chiffre).
# Un ancien document sans « fournisseur » mais avec un hôte vaut « smtp ».
def _smtp_env() -> dict:
    """Serveur SMTP de repli (PLATEFORME_SMTP_* ou SMTP_*)."""
    s = get_settings()
    return {"hote": s.plateforme_smtp_hote or "", "port": s.plateforme_smtp_port, "utilisateur": s.plateforme_smtp_utilisateur or "",
            "mot_de_passe": s.plateforme_smtp_mot_de_passe or "",
            "expediteur": s.plateforme_expediteur or s.email_expediteur or "",
            "nom_expediteur": "adLyn", "ssl": s.plateforme_smtp_ssl}


def _smtp_doc(doc: dict) -> dict:
    """Serveur SMTP réglé dans l'écran (mot de passe déchiffré)."""
    return {"hote": doc.get("hote") or "", "port": int(doc.get("port") or 587), "utilisateur": doc.get("utilisateur", ""),
            "mot_de_passe": dechiffrer(doc.get("mot_de_passe_chiffre", "")),
            "expediteur": doc.get("expediteur", ""), "nom_expediteur": doc.get("nom_expediteur") or "adLyn",
            "ssl": bool(doc.get("ssl"))}


async def config_smtp() -> dict:
    """Réglages SMTP en vigueur : ceux de l'administration, sinon les variables d'environnement."""
    from db import db
    doc = await db.parametres_plateforme.find_one({"_id": DOC_EMAIL}) or {}
    if doc.get("hote"):
        return {**_smtp_doc(doc), "actif": doc.get("actif", True), "source": "administration"}
    return {**_smtp_env(), "actif": bool(get_settings().plateforme_smtp_hote), "source": "variables d'environnement"}


def resend_configure() -> bool:
    """Vrai si Resend est réglé par les variables d'environnement (clé ET adresse d'envoi)."""
    s = get_settings()
    return bool(s.resend_api_key and (s.resend_expediteur or s.email_expediteur))


def cle_env(fournisseur: str) -> str:
    """Clé API de repli d'un fournisseur, lue dans les variables d'environnement."""
    s = get_settings()
    return {"resend": s.resend_api_key, "brevo": s.brevo_api_key, "zeptomail": s.zeptomail_api_key}.get(fournisseur) or ""


def config_env() -> dict:
    """Repli quand rien n'est réglé dans l'écran, par ordre de priorité :
    1. RESEND_API_KEY + RESEND_EXPEDITEUR ; 2. PLATEFORME_SMTP_* / SMTP_* ;
    puis BREVO_API_KEY et ZEPTOMAIL_API_KEY (+ ZEPTOMAIL_HOTE), avec EMAIL_EXPEDITEUR."""
    s = get_settings()
    commun = (s.email_expediteur or "").strip()
    smtp = _smtp_env()
    base = {"actif": True, "nom_expediteur": "adLyn", "source": "variables d'environnement",
            "zeptomail_hote": hote_zeptomail(s.zeptomail_hote), "smtp": smtp, "cle": ""}
    if resend_configure():
        return {**base, "fournisseur": "resend", "cle": s.resend_api_key, "expediteur": (s.resend_expediteur or commun).strip()}
    if smtp["hote"]:
        return {**base, "fournisseur": "smtp", "expediteur": smtp["expediteur"]}
    if s.brevo_api_key and commun:
        return {**base, "fournisseur": "brevo", "cle": s.brevo_api_key, "expediteur": commun}
    if s.zeptomail_api_key and commun:
        return {**base, "fournisseur": "zeptomail", "cle": s.zeptomail_api_key, "expediteur": commun}
    return {**base, "fournisseur": "", "actif": False, "expediteur": commun, "source": ""}


def fournisseur_choisi(doc: dict) -> str:
    """Choix enregistré dans l'écran ; ancien document sans « fournisseur » avec un hôte -> « smtp »."""
    return doc.get("fournisseur") or ("smtp" if doc.get("hote") else "")


async def lire_reglages_email() -> dict:
    """Document brut des réglages e-mail de la plateforme (secrets chiffrés)."""
    from db import db
    return await db.parametres_plateforme.find_one({"_id": DOC_EMAIL}) or {}


async def config_email() -> dict:
    """Service d'envoi en vigueur pour la plateforme (secrets déchiffrés, usage serveur seulement)."""
    doc = await lire_reglages_email()
    choix = fournisseur_choisi(doc)
    # Rien de réglé dans l'écran -> variables d'environnement.
    # Transition : un ancien réglage SMTP (sans « fournisseur ») ne prend pas le pas sur
    # Resend réglé dans Render, comme avant cette version ; il redevient actif dès que
    # Resend n'est plus réglé, ou après un enregistrement dans l'écran.
    if not choix or (not doc.get("fournisseur") and resend_configure()):
        return config_env()
    smtp = _smtp_doc(doc)
    c = {"fournisseur": choix, "actif": bool(doc.get("actif", True)) and choix != "desactive",
         "expediteur": doc.get("expediteur") or "", "nom_expediteur": doc.get("nom_expediteur") or "adLyn",
         "zeptomail_hote": hote_zeptomail(doc.get("zeptomail_hote")), "smtp": smtp, "cle": "",
         "source": "administration"}
    if choix in FOURNISSEURS_API:
        # Clé saisie dans l'écran ; à défaut, celle des variables d'environnement du même fournisseur
        c["cle"] = dechiffrer((doc.get("cles_chiffrees") or {}).get(choix, "")) or cle_env(choix)
    return c


def config_prete(c: dict) -> tuple[bool, str]:
    """(prêt, raison) : vérifie qu'un réglage permet réellement d'envoyer."""
    f = c.get("fournisseur")
    if f == "desactive" or (f and not c.get("actif")):
        return False, "Envoi des e-mails désactivé"
    if f not in FOURNISSEURS:
        return False, "Service d'envoi des e-mails non réglé (Plateforme > Paramètres)"
    if f == "smtp":
        if not (c.get("smtp") or {}).get("hote"):
            return False, "Serveur SMTP non renseigné"
    elif not c.get("cle"):
        return False, f"Clé API {NOMS_FOURNISSEURS[f]} manquante"
    if not (c.get("expediteur") or (f == "smtp" and (c.get("smtp") or {}).get("utilisateur"))):
        return False, "Adresse d'expéditeur manquante"
    return True, ""


async def envoyer_selon(c: dict, sujet: str, corps: str, destinataire: str,
                        nom: Optional[str] = None, reponse_a: Optional[str] = None) -> None:
    """Envoie avec le réglage `c` (config_email ou celui d'une boutique) ; lève une exception en cas d'échec.
    `nom` : nom affiché (sinon celui du réglage) ; `reponse_a` : adresse des réponses."""
    nom = nettoyer_nom(nom or c.get("nom_expediteur"))
    if c["fournisseur"] in FOURNISSEURS_API:
        await envoyer_par_api(c["fournisseur"], c["cle"], c["expediteur"], nom, destinataire, sujet, corps,
                              reponse_a=reponse_a, zeptomail_hote=c.get("zeptomail_hote"))
        return
    smtp = {**c["smtp"], "expediteur": c.get("expediteur") or c["smtp"].get("expediteur"), "nom_expediteur": nom}
    await asyncio.to_thread(envoyer_smtp, sujet, corps, destinataire, smtp, reponse_a)


async def email_pret() -> bool:
    """Vrai si la plateforme peut envoyer des e-mails (affiché dans l'écran des sauvegardes)."""
    return config_prete(await config_email())[0]


async def journaliser_reglage(par: dict, fournisseur: str, cible: str = "plateforme",
                              boutique_id: Optional[str] = None) -> None:
    """Journal des modifications du service d'envoi : qui, quand, quel fournisseur (jamais la clé)."""
    from db import db
    from utils import new_id, now_iso
    await db.journal_reglages_email.insert_one({
        "id": new_id(), "date": now_iso(), "cible": cible, "boutique_id": boutique_id,
        "par": (par or {}).get("email", ""), "par_id": (par or {}).get("id", ""), "fournisseur": fournisseur})


async def envoyer_email(sujet: str, corps: str, destinataire: str) -> tuple[str, str]:
    """E-mail de la plateforme -> (statut, erreur). Ne lève jamais d'exception."""
    if not destinataire:
        return "NON_CONFIGURE", "Aucune adresse e-mail"
    c = await config_email()
    pret, raison = config_prete(c)
    if not pret:
        return "NON_CONFIGURE", raison
    try:
        await envoyer_selon(c, sujet, corps, destinataire)
        return "ENVOYE", ""
    except Exception as exc:  # noqa: BLE001 — l'échec est rapporté, pas propagé
        logger.warning("E-mail plateforme (%s) vers %s en échec : %s", c["fournisseur"], destinataire, exc)
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
