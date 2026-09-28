"""
Envoi des notifications (e-mails) selon le paramétrage fait par l'admin.

Point d'entrée unique : notifier(code, destinataire, contexte).
Le reste du code n'a jamais à connaître le serveur SMTP ni le texte des
messages : tout est lu en base au moment de l'envoi.
"""

import logging

from django.core.mail import EmailMessage, get_connection
from django.template import Context, Template

from core.models import Entreprise

from .models import JournalEnvoi, ModeleMessage, ParametresMessagerie

logger = logging.getLogger(__name__)

# Textes proposés par défaut (créés automatiquement au premier besoin,
# puis librement modifiables par l'admin dans "Modèles de messages").
MODELES_PAR_DEFAUT = {
    "CMD_RECUE": (
        "Votre commande {{ commande.numero }} a bien été reçue",
        "Bonjour {{ client.nom }},\n\n"
        "Nous avons bien reçu votre commande {{ commande.numero }} "
        "d'un montant de {{ commande.total }} {{ entreprise.devise }}.\n"
        "Nous vous contacterons très vite pour la confirmer.\n\n"
        "Suivez-la ici : {{ lien }}\n\n{{ entreprise.nom }}",
    ),
    "CMD_STATUT": (
        "Commande {{ commande.numero }} : {{ commande.get_statut_display }}",
        "Bonjour {{ client.nom }},\n\n"
        "Votre commande {{ commande.numero }} est désormais : "
        "« {{ commande.get_statut_display }} ».\n\nSuivi : {{ lien }}\n\n{{ entreprise.nom }}",
    ),
    "MAINT_DEPOT": (
        "Dépôt de votre appareil — dossier {{ dossier.numero }}",
        "Bonjour {{ client.nom }},\n\n"
        "Votre {{ dossier.marque }} {{ dossier.modele }} a été enregistré sous le "
        "dossier {{ dossier.numero }} (code de suivi : {{ dossier.code_suivi }}).\n"
        "Suivez la réparation ici : {{ lien }}\n\n{{ entreprise.nom }}",
    ),
    "MAINT_STATUT": (
        "Dossier {{ dossier.numero }} : {{ dossier.get_statut_display }}",
        "Bonjour {{ client.nom }},\n\n"
        "Le statut de votre dossier {{ dossier.numero }} "
        "({{ dossier.marque }} {{ dossier.modele }}) est maintenant : "
        "« {{ dossier.get_statut_display }} ».\n\nSuivi : {{ lien }}\n\n{{ entreprise.nom }}",
    ),
    "CONSEIL_REPONSE": (
        "Réponse à votre question : {{ conversation.sujet }}",
        "Bonjour {{ conversation.nom }},\n\n"
        "Notre équipe a répondu à votre demande « {{ conversation.sujet }} » :\n\n"
        "{{ message.texte }}\n\nPour répondre : {{ lien }}\n\n{{ entreprise.nom }}",
    ),
    "EQUIPE_CMD": (
        "Nouvelle commande en ligne {{ commande.numero }}",
        "Nouvelle commande de {{ client.nom }} ({{ client.telephone }}) : "
        "{{ commande.total }} {{ entreprise.devise }}.",
    ),
    "EQUIPE_CONSEIL": (
        "Nouvelle demande de conseil : {{ conversation.sujet }}",
        "{{ conversation.nom }} ({{ conversation.telephone }}) a écrit :\n\n{{ message.texte }}",
    ),
}


def assurer_modeles_par_defaut():
    """Crée les modèles de messages manquants (ne modifie jamais ceux existants)."""
    for code, (sujet, corps) in MODELES_PAR_DEFAUT.items():
        ModeleMessage.objects.get_or_create(code=code, defaults={"sujet": sujet, "corps": corps})


def _connexion_smtp(p: ParametresMessagerie):
    """Ouvre une connexion SMTP avec les réglages saisis par l'admin."""
    return get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=p.smtp_hote,
        port=p.smtp_port,
        username=p.smtp_utilisateur or None,
        password=p.smtp_mot_de_passe or None,
        use_tls=p.smtp_tls and not p.smtp_ssl,  # TLS et SSL sont exclusifs
        use_ssl=p.smtp_ssl,
        timeout=15,
    )


def envoyer_email(destinataire: str, sujet: str, corps: str, code: str = "") -> JournalEnvoi:
    """
    Envoie un e-mail (ou le journalise seulement si l'envoi est désactivé).
    Ne lève JAMAIS d'exception : un souci de messagerie ne doit pas bloquer
    l'enregistrement d'une commande ou d'un dossier. L'erreur est notée
    dans le journal, consultable par l'admin.
    """
    p = ParametresMessagerie.get()
    journal = JournalEnvoi(code=code, destinataire=destinataire, sujet=sujet, corps=corps)
    if not (p.email_actif and p.smtp_hote):
        journal.statut = "NON_ENVOYE"
    else:
        try:
            expediteur = f"{p.expediteur_nom} <{p.expediteur_email or p.smtp_utilisateur}>"
            EmailMessage(sujet, corps, expediteur, [destinataire], connection=_connexion_smtp(p)).send()
            journal.statut = "ENVOYE"
        except Exception as exc:  # noqa: BLE001 — on veut tout capter et journaliser
            logger.exception("Échec d'envoi d'e-mail à %s", destinataire)
            journal.statut = "ECHEC"
            journal.erreur = str(exc)
    journal.save()
    return journal


def notifier(code: str, destinataire, contexte: dict, lien: str = ""):
    """
    Envoie la notification « code » à un client (objet Client), une adresse
    e-mail (texte) ou à l'équipe (destinataire=None -> e-mail de l'équipe).

    Le texte provient du ModeleMessage correspondant, où les variables
    {{ ... }} sont remplacées par les valeurs du contexte.
    """
    assurer_modeles_par_defaut()
    modele = ModeleMessage.objects.get(code=code)
    if not modele.actif:
        return None

    p = ParametresMessagerie.get()
    # Détermination de l'adresse e-mail du destinataire
    if destinataire is None:
        adresse = p.email_equipe
    elif isinstance(destinataire, str):
        adresse = destinataire
    else:
        adresse = getattr(destinataire, "email", "")
        contexte.setdefault("client", destinataire)
    if not adresse:
        return None  # pas d'e-mail connu : rien à envoyer

    # Lien de suivi par défaut, construit à partir de l'objet concerné
    if not lien:
        objet = contexte.get("dossier") or contexte.get("commande") or contexte.get("conversation")
        chemin = _chemin_suivi(objet)
        lien = f"{p.url_site.rstrip('/')}{chemin}" if chemin else p.url_site
    contexte = {**contexte, "entreprise": Entreprise.get(), "lien": lien}

    # Remplacement des variables {{ ... }} avec le moteur de gabarits Django
    sujet = Template(modele.sujet).render(Context(contexte, autoescape=False)).strip()
    corps = Template(modele.corps).render(Context(contexte, autoescape=False))
    return envoyer_email(adresse, sujet.replace("\n", " "), corps, code)


def _chemin_suivi(objet) -> str:
    """Adresse de suivi sur le portail pour un dossier, une commande ou une conversation."""
    from django.urls import reverse
    from urllib.parse import urlencode

    if objet is None:
        return ""
    nom_classe = objet.__class__.__name__
    if nom_classe == "DossierMaintenance":
        return reverse("portail:suivi_maintenance") + "?" + urlencode(
            {"numero": objet.numero, "code": objet.code_suivi}
        )
    if nom_classe == "Commande":
        return reverse("portail:suivi_commande") + "?" + urlencode(
            {"numero": objet.numero, "telephone": objet.client.telephone}
        )
    if nom_classe == "Conversation":
        return objet.get_absolute_url()
    return ""
