"""Lot B — codes à usage unique (OTP) envoyés par WhatsApp aux COMMERÇANTS :
inscription libre (« Créer ma boutique ») et connexion par téléphone.

Règles de sécurité (valeurs demandées par le propriétaire, à ne changer qu'ici) :
  - code à 6 chiffres, valable 10 minutes, un seul code actif par numéro et par objet ;
  - 5 essais au plus par code : au 5e mauvais code, le code est détruit
    (il faut en redemander un) ;
  - au plus 1 envoi par minute et 5 par heure, par NUMÉRO et par ADRESSE IP
    (mêmes compteurs que les codes du personnel : collection « limites_codes ») ;
  - 20 mauvais codes en 15 minutes depuis une même adresse IP -> blocage 15 minutes ;
  - le code n'est JAMAIS gardé en clair : seule son empreinte HMAC-SHA256
    (clé dérivée de JWT_SECRET) est en base. Le document s'efface tout seul à
    l'expiration (index TTL « expire_le »).

Collection « otp_whatsapp » (préfixée « tlb_ » comme les autres) :
  {id, telephone (E.164), objet ("INSCRIPTION" | "CONNEXION"), empreinte, essais,
   canal (WHATSAPP / SMS), cree_le, expire_iso, expire_le}

L'envoi passe par le mécanisme des messages de la PLATEFORME
(identifiants.envoyer_message) : WhatsApp d'abord (modèle « Authentication »
WHATSAPP_CODE_TEMPLATE s'il est configuré ; WABA de la plateforme, sinon Liluvine
via SAWALI), SMS de la plateforme en repli.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import get_settings
from db import SANS_ID, db
from utils import new_id, now_iso

# --- Règles (voir l'en-tête) ---
CODE_VALIDITE = timedelta(minutes=10)
MAX_ESSAIS_CODE = 5
MAX_ESSAIS_IP = 20

# Objets d'un code (un code d'inscription ne sert pas à se connecter, et inversement)
INSCRIPTION, CONNEXION = "INSCRIPTION", "CONNEXION"

# Résultats possibles de la vérification d'un code
CODE_BON, CODE_FAUX, CODE_EXPIRE, CODE_EPUISE = "BON", "FAUX", "EXPIRE", "EPUISE"


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _empreinte(telephone: str, objet: str, code: str) -> str:
    """Empreinte HMAC-SHA256 du code : la base ne contient jamais le code lui-même."""
    cle = ("adlyn-otp-whatsapp|" + get_settings().jwt_secret).encode()
    return hmac.new(cle, f"{telephone}|{objet}|{code}".encode(), hashlib.sha256).hexdigest()


async def creer_code(telephone: str, objet: str) -> str:
    """Nouveau code à 6 chiffres pour ce numéro (remplace le précédent du même objet).
    Le code en clair est renvoyé UNIQUEMENT pour être envoyé, jamais enregistré."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    expire = _maintenant() + CODE_VALIDITE
    await db.otp_whatsapp.delete_many({"telephone": telephone, "objet": objet})
    await db.otp_whatsapp.insert_one({
        "id": new_id(), "telephone": telephone, "objet": objet, "empreinte": _empreinte(telephone, objet, code),
        "essais": 0, "canal": "", "cree_le": now_iso(), "expire_iso": expire.isoformat(),
        "expire_le": expire})  # date réelle : MongoDB efface le document à cette heure (index TTL)
    return code


async def noter_canal(telephone: str, objet: str, canal: Optional[str]) -> None:
    """Canal par lequel le code est parti (WHATSAPP / SMS), pour le suivi."""
    await db.otp_whatsapp.update_one({"telephone": telephone, "objet": objet}, {"$set": {"canal": canal or ""}})


async def annuler_code(telephone: str, objet: str) -> None:
    await db.otp_whatsapp.delete_many({"telephone": telephone, "objet": objet})


async def verifier_code(telephone: str, objet: str, code: str, *, consommer: bool = True) -> str:
    """Contrôle le code saisi -> CODE_BON, CODE_FAUX, CODE_EXPIRE ou CODE_EPUISE.
    Un mauvais code compte un essai ; au 5e, le code est détruit (CODE_EPUISE).
    Un bon code est consommé (usage unique) sauf si `consommer` est faux."""
    doc = await db.otp_whatsapp.find_one({"telephone": telephone, "objet": objet}, SANS_ID)
    if not doc or doc.get("expire_iso", "") <= _maintenant().isoformat():
        await annuler_code(telephone, objet)
        return CODE_EXPIRE
    saisi = re.sub(r"\D", "", code or "")
    if len(saisi) == 6 and hmac.compare_digest(doc["empreinte"], _empreinte(telephone, objet, saisi)):
        if consommer:
            await annuler_code(telephone, objet)
        return CODE_BON
    essais = int(doc.get("essais", 0)) + 1
    if essais >= MAX_ESSAIS_CODE:
        await annuler_code(telephone, objet)
        return CODE_EPUISE
    await db.otp_whatsapp.update_one({"telephone": telephone, "objet": objet}, {"$set": {"essais": essais}})
    return CODE_FAUX


def message_erreur_code(resultat: str) -> str:
    """Phrase affichée au commerçant pour un code refusé (aucune information sensible)."""
    return {
        CODE_FAUX: "Code incorrect. Vérifiez le code reçu par WhatsApp et réessayez.",
        CODE_EXPIRE: "Code expiré ou inconnu : demandez un nouveau code.",
        CODE_EPUISE: "Trop d'essais pour ce code : demandez un nouveau code.",
    }.get(resultat, "Code refusé")


def texte_message(code: str, objet: str) -> tuple[str, str]:
    """(sujet, texte) du message qui porte le code (texte simple, compatible SMS)."""
    import identifiants

    return identifiants.texte_code(code, objet)


async def envoyer_code(telephone: str, objet: str, code: str) -> dict:
    """Envoie le code au numéro : WhatsApp (plateforme) puis SMS en repli.
    Renvoie le résultat de identifiants.envoyer_message (canal, statut, erreur…)."""
    import identifiants

    sujet, texte = texte_message(code, objet)
    resultat = await identifiants.envoyer_message(telephone=telephone, sujet=sujet, texte=texte, code=code)
    await noter_canal(telephone, objet, resultat.get("canal"))
    return resultat
