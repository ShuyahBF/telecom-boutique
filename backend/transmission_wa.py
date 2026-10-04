"""Transmission WA : point d'envoi UNIQUE des messages WhatsApp d'adLyn.

Règle du propriétaire — chaque plateforme envoie avec SES PROPRES paramètres WABA
s'ils existent. Ordre de priorité appliqué ici :
  1. paramètres WABA de la BOUTIQUE concernée (champ « whatsapp_waba » de la fiche
     boutique : phone_number_id + access_token CHIFFRÉ, saisis par le gérant dans
     Paramètres > WhatsApp) ;
  2. paramètres WABA de la PLATEFORME adLyn (WHATSAPP_ACCESS_TOKEN,
     WHATSAPP_PHONE_NUMBER_ID) ;
  3. À DÉFAUT, « Transmission WA Universelle Liluvine » : appel HTTP signé (HMAC)
     vers SAWALI, qui envoie le message avec son propre compte WhatsApp
     (variables LILUVINE_WA_URL, LILUVINE_WA_HMAC, LILUVINE_WA_EMETTEUR).

Protocole v3 (complète la v2, rétrocompatible) :
  - MÉDIAS : `media` = {"type": document|image|video|audio, "url" OU "contenu" (octets),
    "nom_fichier", "mime", "legende"} ; 10 Mo au plus (refus local, sans appel) ;
  - REPLI : si le WABA propre (boutique ou plateforme) échoue pour une autre raison
    qu'un numéro invalide (fenêtre de 24 h, modèle requis, panne…) et que Liluvine est
    configurée, le même message (et le même média) repart par Liluvine,
    canal « liluvine_repli » ;
  - DÉSINSCRIPTION : SAWALI répond 409 quand le destinataire a écrit STOP : échec
    définitif, sans nouvel essai, tracé dans `liluvine_retours` ;
  - RETOURS : SAWALI rappelle adLyn (POST /api/webhooks/liluvine-retour, signé avec la
    même clé) pour les statuts, les réponses du client et les désinscriptions ;
    voir verifier_signature() et enregistrer_retour().

Résultat toujours uniforme, jamais d'exception :
  {"ok", "canal": "waba_boutique"|"waba_plateforme"|"liluvine"|"liluvine_repli"|None,
   "message_id", "erreur", "statut": "ENVOYE"|"ECHEC"|"NON_CONFIGURE"}
  (+ "media_mode", "desinscrit", "erreur_waba" quand ils ont un sens).
Sécurité : la clé HMAC, les jetons et le texte complet du message ne sont jamais journalisés.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from typing import Optional, Union

import httpx

import envois_plateforme as envois
from config import get_settings

logger = logging.getLogger(__name__)

DELAI_LILUVINE = 15  # secondes (protocole v2)
LONGUEUR_MAX = 4096  # caractères au plus acceptés par SAWALI
FENETRE_SIGNATURE = 300  # secondes : horodatage accepté à ± 5 minutes (retours de SAWALI)

# Médias (protocole v3)
TYPES_MEDIA = ("document", "image", "video", "audio")
MEDIA_MAX_OCTETS = 10 * 1024 * 1024  # 10 Mo avant encodage
LEGENDE_MAX = 1024  # longueur maximale d'une légende chez WhatsApp

# Repli WABA -> Liluvine (protocole v3, section 4)
# Codes Meta « fenêtre de 24 h / modèle requis » : documentés ici, le repli s'applique
# de toute façon à tout échec qui ne vient pas du numéro lui-même.
CODES_FENETRE_24H = {"131047", "131026", "470"}
# Codes Meta « numéro invalide » : PAS de repli (Liluvine échouerait de la même façon)
CODES_NUMERO_INVALIDE = {"131030", "131021", "1013"}
MOTS_NUMERO_INVALIDE = ("invalid phone", "phone number is invalid", "not a valid phone", "invalid_recipient",
                        "recipient phone number not", "numéro de téléphone absent ou invalide", "numéro invalide")


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


def canal_prevu(boutique: Optional[dict]) -> Optional[str]:
    """Canal qu'utiliserait un envoi pour cette boutique (affichage, sans envoyer)."""
    if waba_boutique(boutique):
        return "waba_boutique"
    if envois.whatsapp_configure():
        return "waba_plateforme"
    return "liluvine" if liluvine_configure() else None


def source_par_defaut(boutique: Optional[dict]) -> str:
    """Libellé affiché au destinataire : « adLyn — <boutique> » ou « adLyn »."""
    nom = ((boutique or {}).get("nom") or "").strip()
    return f"adLyn — {nom}" if nom else "adLyn"


# ---------------------------------------------------------------------------
# Médias : contrôle local avant tout appel (protocole v3, section 1)
# ---------------------------------------------------------------------------
def normaliser_media(media: Optional[dict]) -> tuple[Optional[dict], Optional[str]]:
    """Contrôle la pièce jointe -> (média normalisé, None) ou (None, message d'erreur).
    Média normalisé : {"type", "url" OU "contenu" (octets), "nom_fichier", "mime", "legende"}.
    Exactement UN des deux : adresse https OU contenu (octets, ou texte base64 déjà encodé).
    Au-delà de 10 Mo, refus local : aucun appel réseau n'est fait."""
    if not media:
        return None, None
    if not isinstance(media, dict):
        return None, "Média invalide"
    type_media = str(media.get("type") or "").strip().lower()
    if type_media not in TYPES_MEDIA:
        return None, "Type de média invalide (document, image, video ou audio)"
    url = str(media.get("url") or "").strip()
    contenu = media.get("contenu")
    # Contenu déjà encodé en base64 : décodé pour mesurer sa taille réelle
    if contenu is None and media.get("contenu_base64"):
        try:
            contenu = base64.b64decode(str(media["contenu_base64"]), validate=True)
        except (binascii.Error, ValueError):
            return None, "Contenu du média illisible (base64 invalide)"
    if bool(url) == (contenu is not None):
        return None, "Indiquez soit l'adresse du média, soit son contenu (exactement un des deux)"
    if url and not url.lower().startswith("https://"):
        return None, "L'adresse du média doit commencer par https://"
    if contenu is not None:
        if not isinstance(contenu, (bytes, bytearray)):
            return None, "Le contenu du média doit être fourni en octets"
        if len(contenu) > MEDIA_MAX_OCTETS:
            return None, "Média trop lourd : 10 Mo au maximum"
        if not contenu:
            return None, "Média vide"
    propre = {"type": type_media, "nom_fichier": str(media.get("nom_fichier") or "")[:150] or None,
              "mime": str(media.get("mime") or "")[:100] or None,
              "legende": str(media.get("legende") or "")[:LEGENDE_MAX] or None}
    if url:
        propre["url"] = url
    else:
        propre["contenu"] = bytes(contenu)
    return propre, None


def _media_pour_liluvine(media: dict) -> dict:
    """Champ « media » du corps signé envoyé à SAWALI (octets encodés en base64)."""
    corps = {"type": media["type"]}
    if media.get("url"):
        corps["url"] = media["url"]
    else:
        corps["contenu_base64"] = base64.b64encode(media["contenu"]).decode("ascii")
    for cle in ("nom_fichier", "mime", "legende"):
        if media.get(cle):
            corps[cle] = media[cle]
    return corps


# ---------------------------------------------------------------------------
# Repli WABA -> Liluvine : l'erreur vient-elle du numéro lui-même ?
# ---------------------------------------------------------------------------
def codes_meta(erreur: str) -> set[str]:
    """Codes d'erreur Meta présents dans le message (« "code":131047 »)."""
    return set(re.findall(r'"code"\s*:\s*"?(\d+)', erreur or ""))


def erreur_numero(erreur: str) -> bool:
    """Vrai si l'échec vient d'un numéro invalide (aucun repli dans ce cas)."""
    texte = (erreur or "").lower()
    return bool(codes_meta(erreur) & CODES_NUMERO_INVALIDE) or any(m in texte for m in MOTS_NUMERO_INVALIDE)


def repli_autorise(erreur: str) -> bool:
    """Repli par Liluvine : fenêtre de 24 h / modèle requis (131047, 131026, 470, « 24 »,
    « re-engagement », « outside »…) OU tout autre échec, sauf un numéro invalide."""
    return not erreur_numero(erreur)


# ---------------------------------------------------------------------------
# Traces en base (jamais bloquantes)
# ---------------------------------------------------------------------------
async def _journaliser_envoi(ligne: dict) -> None:
    """Journal des envois par Liluvine (collection transmissions_wa) : sert à relier
    les retours de SAWALI (statut, réponse du client) à l'envoi d'origine et à sa boutique."""
    try:
        from db import db

        await db.transmissions_wa.insert_one(dict(ligne))
    except Exception as exc:  # noqa: BLE001 — une trace manquée ne doit pas casser l'envoi
        logger.warning("Journal de la transmission WA impossible : %s", type(exc).__name__)


async def _tracer_desinscrit(id_message: str, numero: str, boutique_id: Optional[str]) -> None:
    """Refus 409 de SAWALI (destinataire désinscrit) : trace dans liluvine_retours."""
    try:
        from db import db
        from utils import new_id, now_iso

        await db.liluvine_retours.update_one(
            {"cle": f"refus_desinscrit|{id_message}"},
            {"$setOnInsert": {"id": new_id(), "cle": f"refus_desinscrit|{id_message}", "type": "refus_desinscrit",
                              "id_origine": id_message, "numero": numero, "boutique_id": boutique_id,
                              "statut": "desinscrit", "date": now_iso(), "recu_le": now_iso()}},
            upsert=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Trace de désinscription impossible : %s", type(exc).__name__)


# ---------------------------------------------------------------------------
# Transmission WA Universelle Liluvine (protocole v2 + v3)
# ---------------------------------------------------------------------------
def signer(cle: str, horodatage: str, corps_brut: bytes) -> str:
    """X-Signature = hex(HMAC-SHA256(clé, "<timestamp>.<corps brut>"))."""
    return hmac.new(cle.encode(), horodatage.encode() + b"." + corps_brut, hashlib.sha256).hexdigest()


async def envoyer_liluvine(numero: str, message: str, *, source: Optional[str] = None,
                           id_message: Optional[str] = None, media: Optional[dict] = None,
                           canal: str = "liluvine", boutique_id: Optional[str] = None) -> dict:
    """Appel signé vers SAWALI. Un seul nouvel essai (même id, nouvelle signature)
    sur erreur réseau ou réponse 5xx ; aucun nouvel essai sur 4xx (409 = destinataire
    désinscrit : échec définitif). `media` : voir normaliser_media()."""
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
                         erreur="Aucun texte à transmettre (le champ message est obligatoire, même avec un média)")
    # Média contrôlé localement : un fichier trop lourd n'est jamais envoyé
    media_propre, erreur_media = normaliser_media(media)
    if erreur_media:
        return _resultat(False, canal, erreur=erreur_media)
    # Corps sérialisé UNE SEULE FOIS : ce sont exactement ces octets qui sont signés et envoyés
    id_message = id_message or str(uuid.uuid4())
    corps = {"id": id_message, "to": "+" + chiffres, "message": texte[:LONGUEUR_MAX]}
    if source:
        corps["source"] = source[:120]
    if media_propre:
        corps["media"] = _media_pour_liluvine(media_propre)
    corps_brut = json.dumps(corps, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    url, cle = s.liluvine_wa_url.strip(), s.liluvine_wa_hmac.strip()

    resultat: Optional[dict] = None
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
                    resultat = _resultat(True, canal, message_id=donnees.get("message_id"))
                    if media_propre:
                        resultat["media_mode"] = donnees.get("media_mode")
                else:
                    resultat = _resultat(False, canal, erreur=str(donnees.get("detail") or "Envoi refusé")[:200])
                break
            if r.status_code == 409:
                # Destinataire désinscrit (STOP) : échec DÉFINITIF, aucun nouvel essai
                resultat = _resultat(False, canal, erreur="Destinataire désinscrit (il a répondu STOP) : "
                                                           "réinscription à faire dans SAWALI")
                resultat["desinscrit"] = True
                await _tracer_desinscrit(id_message, "+" + chiffres, boutique_id)
                break
            derniere_erreur = f"HTTP {r.status_code} {r.text[:150]}"
            logger.warning("Transmission Liluvine (essai %s) vers %s… : HTTP %s", essai, chiffres[:5], r.status_code)
            if r.status_code < 500:
                break  # 4xx : données ou signature refusées, inutile de réessayer
    if resultat is None:
        resultat = _resultat(False, canal, erreur=derniere_erreur[:300])
    # Journal de l'envoi (relie les retours de SAWALI à cet envoi), sans le texte du message
    from utils import now_iso

    await _journaliser_envoi({"id": id_message, "numero": "+" + chiffres, "canal": canal,
                              "boutique_id": boutique_id, "statut": resultat["statut"],
                              "message_id": resultat.get("message_id"), "erreur": resultat.get("erreur"),
                              "media": (media_propre or {}).get("type"), "date": now_iso()})
    return resultat


# ---------------------------------------------------------------------------
# Point d'entrée unique
# ---------------------------------------------------------------------------
async def _envoyer_waba(numero: str, message: str, identifiants: Optional[tuple[str, str]], *,
                        variables, modele, composants, media: Optional[dict]) -> tuple[str, str, Optional[str]]:
    """Envoi par un compte WABA (boutique si `identifiants`, sinon plateforme).
    Avec un média : message média (légende = légende du média, sinon le texte) ;
    sans média : modèle Meta puis texte libre, comme avant."""
    if media:
        return await envois.envoyer_media_waba(numero, media, media.get("legende") or message,
                                               identifiants=identifiants)
    return await envois.envoyer_whatsapp_waba(numero, variables or [], message, modele=modele,
                                              composants=composants, identifiants=identifiants)


async def envoyer_whatsapp(numero: str, message: str, *, boutique: Union[dict, str, None] = None,
                           source: Optional[str] = None, variables: Optional[list[str]] = None,
                           modele: Optional[str] = None, composants: Optional[list] = None,
                           media: Optional[dict] = None) -> dict:
    """Envoie un WhatsApp en appliquant l'ordre de priorité (voir en-tête du module).
    `boutique` : fiche ou identifiant de la boutique concernée (None = message de la
    plateforme). `variables` / `modele` / `composants` : modèle Meta, utilisés par les
    comptes WABA ; Liluvine envoie `message` (+ `media`).
    `media` : {"type", "url" | "contenu" (octets), "nom_fichier", "mime", "legende"}."""
    try:
        # Média contrôlé AVANT tout appel (10 Mo au plus, url https ou octets)
        media_propre, erreur_media = normaliser_media(media)
        if erreur_media:
            return _resultat(False, None, erreur=erreur_media)
        fiche = await _charger_boutique(boutique)
        boutique_id = (fiche or {}).get("id")
        source = source or source_par_defaut(fiche)

        # 1) Compte WABA propre à la boutique, sinon 2) celui de la plateforme adLyn
        identifiants = waba_boutique(fiche)
        canal = "waba_boutique" if identifiants else ("waba_plateforme" if envois.whatsapp_configure() else None)
        if canal:
            statut, erreur, mid = await _envoyer_waba(numero, message, identifiants, variables=variables,
                                                      modele=modele, composants=composants, media=media_propre)
            if statut == "ENVOYE":
                return _resultat(True, canal, message_id=mid, statut=statut)
            # Repli (section 4) : WABA en échec pour une autre raison qu'un numéro invalide
            if statut == "ECHEC" and liluvine_configure() and (message or "").strip() and repli_autorise(erreur):
                logger.info("WABA (%s) en échec, repli par Liluvine (codes Meta : %s)",
                            canal, ",".join(sorted(codes_meta(erreur))) or "-")
                repli = await envoyer_liluvine(numero, message, source=source, media=media_propre,
                                               canal="liluvine_repli", boutique_id=boutique_id)
                repli["erreur_waba"] = (erreur or "")[:300]
                return repli
            return _resultat(False, canal, message_id=mid, erreur=erreur or None, statut=statut)

        # 3) À défaut : Transmission WA Universelle Liluvine
        return await envoyer_liluvine(numero, message, source=source, media=media_propre, boutique_id=boutique_id)
    except Exception as exc:  # noqa: BLE001 — un envoi WhatsApp ne doit jamais casser l'appelant
        logger.warning("Transmission WA impossible : %s", type(exc).__name__)
        return _resultat(False, None, erreur="Erreur inattendue lors de l'envoi WhatsApp")


# ---------------------------------------------------------------------------
# Retours de SAWALI (protocole v3, section 2) : statuts, réponses, désinscriptions
# ---------------------------------------------------------------------------
TYPES_RETOUR = ("statut", "reponse", "desinscription")


def verifier_signature(horodatage: str, corps_brut: bytes, signature: str,
                       maintenant: Optional[float] = None) -> bool:
    """Signature d'un retour de SAWALI : même clé que les envois (LILUVINE_WA_HMAC),
    comparaison à temps constant, horodatage accepté à ± 5 minutes."""
    cle = (get_settings().liluvine_wa_hmac or "").strip()
    if not cle or not horodatage or not signature:
        return False
    try:
        ts = int(horodatage)
    except ValueError:
        return False
    if abs((maintenant or time.time()) - ts) > FENETRE_SIGNATURE:
        return False
    return hmac.compare_digest(signer(cle, horodatage, corps_brut), signature.strip().lower())


def cle_retour(doc: dict) -> str:
    """Clé d'idempotence : (type, id | message_id | numéro + date). Un même statut,
    une même réponse ou une même désinscription reçus deux fois ne font qu'une ligne."""
    t = doc.get("type")
    if t == "statut":
        return f"statut|{doc.get('id') or doc.get('message_id')}|{doc.get('statut')}"
    return f"{t}|{doc.get('de')}|{doc.get('date')}"


async def enregistrer_retour(doc: dict) -> tuple[bool, dict]:
    """Range un retour dans liluvine_retours -> (nouveau ?, ligne enregistrée).
    Un statut met aussi à jour l'envoi d'origine (transmissions_wa)."""
    from db import SANS_ID, db
    from utils import new_id, now_iso

    t = doc["type"]
    id_origine = str(doc.get("id") if t == "statut" else doc.get("id_origine") or "")[:80] or None
    # Envoi d'origine (s'il est connu) : donne la boutique concernée
    origine = await db.transmissions_wa.find_one({"id": id_origine}, SANS_ID) if id_origine else None
    media = doc.get("media") if isinstance(doc.get("media"), dict) else None
    ligne = {"id": new_id(), "cle": cle_retour(doc)[:300], "type": t, "id_origine": id_origine,
             "message_id": str(doc.get("message_id") or "")[:200] or None,
             "numero": str(doc.get("de") or (origine or {}).get("numero") or "")[:30] or None,
             "statut": str(doc.get("statut") or "")[:30] or None, "erreur": str(doc.get("erreur") or "")[:300] or None,
             "texte": str(doc.get("texte") or "")[:4096] or None,
             "media": {k: str(media.get(k) or "")[:500] for k in ("type", "url_temporaire", "mime", "nom_fichier")}
             if media else None,
             "date": str(doc.get("date") or "")[:40] or None, "recu_le": now_iso(),
             "boutique_id": (origine or {}).get("boutique_id")}
    r = await db.liluvine_retours.update_one({"cle": ligne["cle"]}, {"$setOnInsert": ligne}, upsert=True)
    nouveau = r.upserted_id is not None
    # Statut de livraison reporté sur l'envoi d'origine (sent -> delivered -> read / failed)
    if nouveau and t == "statut" and origine:
        await db.transmissions_wa.update_one({"id": id_origine}, {"$set": {
            "statut_livraison": ligne["statut"], "statut_livraison_le": ligne["recu_le"],
            "erreur_livraison": ligne["erreur"]}})
    ligne.pop("_id", None)
    return nouveau, ligne


async def signaler_reponse(ligne: dict) -> None:
    """Réponse d'un client : signalée aux super-administrateurs par e-mail (canal
    interne existant), jamais par un nouveau WhatsApp. N'échoue jamais."""
    try:
        from db import db

        s = get_settings()
        adresses = {u.get("email") for u in await db.users.find({"role": "super_admin"}, {"_id": 0, "email": 1})
                    .to_list(20) if u.get("email")}
        if s.super_admin_email:
            adresses.add(s.super_admin_email)
        boutique = ""
        if ligne.get("boutique_id"):
            b = await db.boutiques.find_one({"id": ligne["boutique_id"]}, {"_id": 0, "nom": 1})
            boutique = f" (boutique {b['nom']})" if b else ""
        corps = (f"Réponse WhatsApp reçue par la Transmission WA Universelle (Liluvine){boutique}.\n\n"
                 f"De : {ligne.get('numero') or '?'}\nDate : {ligne.get('date') or ligne.get('recu_le')}\n"
                 f"Texte : {ligne.get('texte') or '(média sans texte)'}\n"
                 + (f"Pièce jointe : {ligne['media'].get('type')} {ligne['media'].get('nom_fichier') or ''}\n"
                    if ligne.get("media") else "")
                 + "\nListe complète : Plateforme > Paramètres > Transmission WA.")
        for adresse in adresses:
            await envois.envoyer_email("adLyn — réponse WhatsApp d'un client", corps, adresse)
        logger.info("Réponse WhatsApp reçue par Liluvine, signalée à %s administrateur(s)", len(adresses))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Signalement de la réponse WhatsApp impossible : %s", type(exc).__name__)
