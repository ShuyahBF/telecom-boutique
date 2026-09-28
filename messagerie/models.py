"""
Centre de messagerie.

1. ParametresMessagerie : réglages saisis par l'ADMINISTRATEUR (serveur
   SMTP, expéditeur, notifications actives...). Aucun redémarrage ni
   modification de code n'est nécessaire pour les changer.
2. ModeleMessage : textes des e-mails automatiques, modifiables par l'admin.
3. JournalEnvoi : trace de chaque e-mail envoyé (ou en échec).
4. Conversation / Message : demandes de conseil des clients et réponses
   du personnel (fil de discussion, comme une messagerie interne).
"""

import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from catalogue.models import Produit
from tiers.models import Client


class ParametresMessagerie(models.Model):
    """Réglages de la messagerie (UNE SEULE ligne en base, comme Entreprise)."""

    email_actif = models.BooleanField(
        "Envoi d'e-mails activé", default=False,
        help_text="Décoché : les notifications sont seulement enregistrées dans le journal.",
    )
    smtp_hote = models.CharField("Serveur SMTP", max_length=150, blank=True, help_text="Ex : smtp.gmail.com")
    smtp_port = models.PositiveIntegerField("Port SMTP", default=587)
    smtp_utilisateur = models.CharField("Utilisateur SMTP", max_length=150, blank=True)
    smtp_mot_de_passe = models.CharField(
        "Mot de passe SMTP", max_length=150, blank=True,
        help_text="Pour Gmail, utilisez un « mot de passe d'application ».",
    )
    smtp_tls = models.BooleanField("Utiliser STARTTLS (port 587)", default=True)
    smtp_ssl = models.BooleanField("Utiliser SSL (port 465)", default=False)
    expediteur_nom = models.CharField("Nom de l'expéditeur", max_length=100, default="TelecomPro")
    expediteur_email = models.EmailField("Adresse de l'expéditeur", blank=True)
    url_site = models.URLField(
        "Adresse publique du site", default="http://localhost:8000",
        help_text="Utilisée pour les liens de suivi insérés dans les e-mails.",
    )
    email_equipe = models.EmailField(
        "E-mail de l'équipe", blank=True,
        help_text="Reçoit les alertes internes : nouvelle commande, nouvelle demande de conseil.",
    )

    class Meta:
        verbose_name = "Paramètres de messagerie"
        verbose_name_plural = "Paramètres de messagerie"

    def __str__(self):
        return "Paramètres de messagerie"

    def save(self, *args, **kwargs):
        self.pk = 1  # fiche unique
        super().save(*args, **kwargs)

    @classmethod
    def get(cls) -> "ParametresMessagerie":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ModeleMessage(models.Model):
    """
    Texte d'un e-mail automatique. Le sujet et le corps acceptent des
    variables entre doubles accolades, remplacées à l'envoi, par exemple :
    {{ client.nom }}, {{ commande.numero }}, {{ dossier.numero }},
    {{ dossier.get_statut_display }}, {{ entreprise.nom }}, {{ lien }}.
    """

    CODE_CHOIX = [
        ("CMD_RECUE", "Client — confirmation de commande"),
        ("CMD_STATUT", "Client — changement de statut de commande"),
        ("MAINT_DEPOT", "Client — dépôt d'un appareil en maintenance"),
        ("MAINT_STATUT", "Client — changement de statut de maintenance"),
        ("CONSEIL_REPONSE", "Client — réponse à une demande de conseil"),
        ("EQUIPE_CMD", "Équipe — nouvelle commande en ligne"),
        ("EQUIPE_CONSEIL", "Équipe — nouvelle demande de conseil"),
    ]

    code = models.CharField(max_length=20, choices=CODE_CHOIX, unique=True)
    actif = models.BooleanField(default=True)
    sujet = models.CharField(max_length=200)
    corps = models.TextField()

    class Meta:
        ordering = ["code"]
        verbose_name = "Modèle de message"
        verbose_name_plural = "Modèles de messages"

    def __str__(self):
        return self.get_code_display()


class JournalEnvoi(models.Model):
    STATUT_CHOIX = [("ENVOYE", "Envoyé"), ("ECHEC", "Échec"), ("NON_ENVOYE", "Non envoyé (e-mail désactivé)")]

    date = models.DateTimeField(default=timezone.now)
    code = models.CharField(max_length=20, blank=True)
    destinataire = models.CharField(max_length=254)
    sujet = models.CharField(max_length=200)
    corps = models.TextField()
    statut = models.CharField(max_length=10, choices=STATUT_CHOIX)
    erreur = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Journal d'envoi"
        verbose_name_plural = "Journal des envois"

    def __str__(self):
        return f"{self.date:%d/%m/%Y %H:%M} → {self.destinataire} ({self.get_statut_display()})"


def _jeton():
    """Jeton secret de 32 caractères : sert de « clé » d'accès du client à sa conversation."""
    return secrets.token_urlsafe(24)


class Conversation(models.Model):
    """Fil de discussion ouvert par un client (demande de conseil, question...)."""

    STATUT_CHOIX = [
        ("ATTENTE", "En attente de réponse"),
        ("REPONDU", "Répondu"),
        ("CLOS", "Clos"),
    ]

    jeton = models.CharField(max_length=40, unique=True, default=_jeton, editable=False)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name="conversations")
    nom = models.CharField(max_length=150)
    telephone = models.CharField("Téléphone", max_length=30)
    email = models.EmailField("E-mail", blank=True)
    sujet = models.CharField(max_length=200)
    produit = models.ForeignKey(Produit, on_delete=models.SET_NULL, null=True, blank=True)
    statut = models.CharField(max_length=8, choices=STATUT_CHOIX, default="ATTENTE")
    date_creation = models.DateTimeField(default=timezone.now)
    date_maj = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-date_maj"]
        verbose_name = "Conversation (demande de conseil)"
        verbose_name_plural = "Conversations (demandes de conseil)"

    def __str__(self):
        return f"{self.sujet} — {self.nom}"

    def get_absolute_url(self):
        """Lien privé du client vers sa conversation sur le portail."""
        return reverse("portail:conversation", args=[self.jeton])

    @property
    def nb_non_lus(self) -> int:
        """Messages du client pas encore lus par l'équipe."""
        return self.messages.filter(auteur_type="CLIENT", lu=False).count()


class Message(models.Model):
    AUTEUR_CHOIX = [("CLIENT", "Client"), ("EQUIPE", "Équipe")]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    auteur_type = models.CharField(max_length=6, choices=AUTEUR_CHOIX)
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    texte = models.TextField()
    date = models.DateTimeField(default=timezone.now)
    lu = models.BooleanField(default=False)

    class Meta:
        ordering = ["date", "id"]

    def __str__(self):
        return f"{self.get_auteur_type_display()} — {self.date:%d/%m/%Y %H:%M}"
