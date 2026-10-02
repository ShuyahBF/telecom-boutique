"""Centre de messagerie : e-mails automatiques paramétrés PAR BOUTIQUE.

Chaque gérant règle dans l'écran « Paramètres > Messagerie » de SA boutique :
serveur SMTP, expéditeur, e-mail de l'équipe, et les textes des messages.
Si Resend est configuré pour la plateforme (RESEND_API_KEY), les e-mails des
boutiques passent par Resend : nom affiché = la boutique, réponses vers
l'adresse d'expéditeur de la boutique (le SMTP est bloqué depuis Render).
Point d'entrée unique : `notifier(ctx_boutique, code, destinataire, contexte)`.
Un souci d'envoi ne bloque JAMAIS l'action en cours (commande, dossier...) :
l'erreur est notée dans le journal des envois, consultable par le gérant.
"""
from __future__ import annotations

import asyncio
import logging
import re
import smtplib
from email.message import EmailMessage
from typing import Any, Optional
from urllib.parse import urlencode

import envois_plateforme
from config import get_settings
from db import TenantDB
from utils import new_id, now_iso

logger = logging.getLogger(__name__)

# Textes proposés par défaut, créés au premier besoin puis modifiables.
# Variables disponibles entre doubles accolades : {{ client.nom }},
# {{ commande.numero }}, {{ dossier.numero }}, {{ dossier.statut_libelle }},
# {{ dossier.code_suivi }}, {{ boutique.nom }}, {{ lien }}...
MODELES_PAR_DEFAUT: dict[str, tuple[str, str, str]] = {
    "CMD_RECUE": (
        "Client — confirmation de commande",
        "Votre commande {{ commande.numero }} a bien été reçue",
        "Bonjour {{ client.nom }},\n\nNous avons bien reçu votre commande {{ commande.numero }} "
        "d'un montant de {{ commande.total }} {{ boutique.devise }}.\nNous vous contacterons très vite "
        "pour la confirmer.\n\nSuivez-la ici : {{ lien }}\n\n{{ boutique.nom }}",
    ),
    "CMD_STATUT": (
        "Client — changement de statut de commande",
        "Commande {{ commande.numero }} : {{ commande.statut_libelle }}",
        "Bonjour {{ client.nom }},\n\nVotre commande {{ commande.numero }} est désormais : "
        "« {{ commande.statut_libelle }} ».\n\nSuivi : {{ lien }}\n\n{{ boutique.nom }}",
    ),
    "CMD_PAYEE": (
        "Client — paiement Mobile Money reçu",
        "Paiement reçu pour la commande {{ commande.numero }}",
        "Bonjour {{ client.nom }},\n\nNous avons bien reçu votre paiement de {{ commande.total }} "
        "{{ boutique.devise }} pour la commande {{ commande.numero }}. Merci !\n\nSuivi : {{ lien }}\n\n{{ boutique.nom }}",
    ),
    "MAINT_DEPOT": (
        "Client — dépôt d'un appareil en maintenance",
        "Dépôt de votre appareil — dossier {{ dossier.numero }}",
        "Bonjour {{ client.nom }},\n\nVotre {{ dossier.marque }} {{ dossier.modele }} a été enregistré "
        "sous le dossier {{ dossier.numero }} (code de suivi : {{ dossier.code_suivi }}).\n"
        "Suivez la réparation ici : {{ lien }}\n\n{{ boutique.nom }}",
    ),
    "MAINT_STATUT": (
        "Client — changement de statut de maintenance",
        "Dossier {{ dossier.numero }} : {{ dossier.statut_libelle }}",
        "Bonjour {{ client.nom }},\n\nLe statut de votre dossier {{ dossier.numero }} "
        "({{ dossier.marque }} {{ dossier.modele }}) est maintenant : « {{ dossier.statut_libelle }} ».\n\n"
        "Suivi : {{ lien }}\n\n{{ boutique.nom }}",
    ),
    "CONSEIL_REPONSE": (
        "Client — réponse à une demande de conseil",
        "Réponse à votre question : {{ conversation.sujet }}",
        "Bonjour {{ conversation.nom }},\n\nNotre équipe a répondu à votre demande « {{ conversation.sujet }} » :\n\n"
        "{{ message.texte }}\n\nPour répondre : {{ lien }}\n\n{{ boutique.nom }}",
    ),
    "EQUIPE_CMD": (
        "Équipe — nouvelle commande en ligne",
        "Nouvelle commande en ligne {{ commande.numero }}",
        "Nouvelle commande de {{ client.nom }} ({{ client.telephone }}) : {{ commande.total }} {{ boutique.devise }}.",
    ),
    "EQUIPE_CONSEIL": (
        "Équipe — nouvelle demande de conseil",
        "Nouvelle demande de conseil : {{ conversation.sujet }}",
        "{{ conversation.nom }} ({{ conversation.telephone }}) a écrit :\n\n{{ message.texte }}",
    ),
}

_VARIABLE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def remplir(modele: str, contexte: dict) -> str:
    """Remplace {{ a.b }} par la valeur correspondante du contexte.
    Volontairement simple (pas de moteur de gabarits complet) : un texte
    saisi par un gérant ne peut rien exécuter, seulement lire des valeurs."""

    def _valeur(m: re.Match) -> str:
        valeur: Any = contexte
        for morceau in m.group(1).split("."):
            valeur = valeur.get(morceau) if isinstance(valeur, dict) else None
            if valeur is None:
                return ""
        return str(valeur)

    return _VARIABLE.sub(_valeur, modele)


async def modeles_de(tdb: TenantDB) -> list[dict]:
    """Modèles de la boutique ; ceux qui manquent sont créés avec le texte par défaut."""
    existants = {m["code"]: m async for m in tdb.modeles_messages.find({})}
    for code, (libelle, sujet, corps) in MODELES_PAR_DEFAUT.items():
        if code not in existants:
            doc = {"id": new_id(), "code": code, "libelle": libelle, "sujet": sujet, "corps": corps, "actif": True}
            await tdb.modeles_messages.insert_one(doc)
            existants[code] = doc
    return [existants[c] for c in MODELES_PAR_DEFAUT if c in existants]


def lien_suivi(boutique: dict, objet: str, donnees: dict) -> str:
    """Lien public de suivi (portail) pour une commande, un dossier ou une conversation."""
    base = f"{get_settings().public_site_url}/b/{boutique['slug']}"
    if objet == "dossier":
        return f"{base}/suivi-reparation?" + urlencode({"numero": donnees["numero"], "code": donnees["code_suivi"]})
    if objet == "commande":
        return f"{base}/suivi-commande?" + urlencode({"numero": donnees["numero"], "telephone": donnees["client"]["telephone"]})
    if objet == "conversation":
        return f"{base}/conseil/{donnees['jeton']}"
    return base


def _envoyer_smtp(p: dict, destinataire: str, sujet: str, corps: str) -> None:
    """Envoi réel (fonction bloquante, exécutée dans un fil séparé)."""
    msg = EmailMessage()
    msg["Subject"] = sujet
    msg["From"] = f"{p.get('expediteur_nom') or 'Boutique'} <{p.get('expediteur_email') or p.get('smtp_utilisateur')}>"
    msg["To"] = destinataire
    msg.set_content(corps)
    port = int(p.get("smtp_port") or 587)
    if p.get("smtp_ssl"):
        serveur = smtplib.SMTP_SSL(p["smtp_hote"], port, timeout=15)
    else:
        serveur = smtplib.SMTP(p["smtp_hote"], port, timeout=15)
        if p.get("smtp_tls", True):
            serveur.starttls()
    with serveur:
        if p.get("smtp_utilisateur"):
            serveur.login(p["smtp_utilisateur"], p.get("smtp_mot_de_passe") or "")
        serveur.send_message(msg)


async def envoyer_email(boutique: dict, destinataire: str, sujet: str, corps: str, code: str = "") -> dict:
    p = boutique.get("messagerie") or {}
    journal = {"id": new_id(), "date": now_iso(), "code": code, "destinataire": destinataire,
               "sujet": sujet, "corps": corps, "erreur": ""}
    if boutique.get("test"):
        # Boutique interne (coordonnées imaginaires) : aucun e-mail ne part
        journal.update({"statut": "NON_ENVOYE", "erreur": "Boutique interne : envoi désactivé"})
    elif p.get("email_actif") and envois_plateforme.resend_configure():
        # Envoi par Resend (adresse du domaine validé de la plateforme), au nom de la boutique
        try:
            await envois_plateforme.envoyer_resend(
                sujet, corps, destinataire,
                nom_expediteur=p.get("expediteur_nom") or boutique.get("nom") or "Boutique",
                reponse_a=p.get("expediteur_email") or boutique.get("email") or None)
            journal["statut"] = "ENVOYE"
        except Exception as exc:  # noqa: BLE001 — tout est capté et journalisé
            logger.warning("Échec d'envoi d'e-mail (Resend) à %s : %s", destinataire, exc)
            journal["statut"] = "ECHEC"
            journal["erreur"] = str(exc)[:500]
    elif not (p.get("email_actif") and p.get("smtp_hote")):
        journal["statut"] = "NON_ENVOYE"
    else:
        try:
            await asyncio.to_thread(_envoyer_smtp, p, destinataire, sujet, corps)
            journal["statut"] = "ENVOYE"
        except Exception as exc:  # noqa: BLE001 — tout est capté et journalisé
            logger.warning("Échec d'envoi d'e-mail à %s : %s", destinataire, exc)
            journal["statut"] = "ECHEC"
            journal["erreur"] = str(exc)[:500]
    await TenantDB(boutique["id"]).journal_envois.insert_one(journal)
    return journal


async def notifier(boutique: dict, code: str, destinataire: Optional[str], contexte: dict,
                   lien: str = "") -> Optional[dict]:
    """Envoie la notification `code`. destinataire=None -> e-mail de l'équipe
    de la boutique. Rien n'est envoyé si l'adresse est inconnue ou si le
    modèle est désactivé par le gérant."""
    tdb = TenantDB(boutique["id"])
    modeles = {m["code"]: m for m in await modeles_de(tdb)}
    modele = modeles.get(code)
    if not modele or not modele.get("actif", True):
        return None
    adresse = destinataire if destinataire is not None else (boutique.get("messagerie") or {}).get("email_equipe")
    if not adresse:
        return None
    boutique_publique = {k: boutique.get(k) for k in ("nom", "telephone", "adresse", "devise", "slug", "email")}
    ctx = {**contexte, "boutique": boutique_publique, "lien": lien or f"{get_settings().public_site_url}/b/{boutique['slug']}"}
    sujet = remplir(modele["sujet"], ctx).replace("\n", " ").strip()
    corps = remplir(modele["corps"], ctx)
    return await envoyer_email(boutique, adresse, sujet, corps, code)


def notifier_en_fond(boutique: dict, code: str, destinataire: Optional[str], contexte: dict, lien: str = "") -> None:
    """Même chose que notifier(), sans faire attendre la réponse HTTP."""

    async def _run():
        try:
            await notifier(boutique, code, destinataire, contexte, lien)
        except Exception:  # noqa: BLE001
            logger.exception("Notification %s impossible", code)

    asyncio.create_task(_run())


def notifier_client_en_fond(boutique: dict, code: str, client: dict, contexte: dict, lien: str = "") -> None:
    """Notification d'un CLIENT : par e-mail s'il en a un, et par SMS si la
    boutique a le service SMS actif et que le client a un numéro."""
    import sms_boutiques

    if (client or {}).get("email"):
        notifier_en_fond(boutique, code, client["email"], contexte, lien)
    if (client or {}).get("telephone"):
        sms_boutiques.notifier_en_fond(boutique, code, client, contexte, lien)
