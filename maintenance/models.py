"""
Maintenance : dossiers de réparation des appareils déposés par les clients.

À chaque dépôt, la plateforme crée un numéro de dossier unique
(MNT-2026-00001) remis au client sur son bon de dépôt. Avec ce numéro et
son téléphone, le client suit l'avancement sur le portail public.
"""

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from catalogue.models import Produit
from core.models import Compteur
from tiers.models import Client


class DossierMaintenance(models.Model):
    STATUT_CHOIX = [
        ("RECU", "Appareil reçu"),
        ("DIAGNOSTIC", "Diagnostic en cours"),
        ("DEVIS", "Devis en attente d'accord"),
        ("ATTENTE_PIECE", "En attente de pièce"),
        ("REPARATION", "Réparation en cours"),
        ("PRET", "Réparé — prêt à être retiré"),
        ("IRREPARABLE", "Irréparable — à retirer"),
        ("RESTITUE", "Restitué au client"),
    ]
    # Ordre des étapes affiché dans la barre de progression du portail
    ETAPES = ["RECU", "DIAGNOSTIC", "REPARATION", "PRET", "RESTITUE"]

    numero = models.CharField("N° dossier", max_length=30, unique=True, blank=True, editable=False)
    # Code court et imprévisible imprimé sur le bon de dépôt : permet au client
    # de suivre son dossier sans compte (en plus du numéro de téléphone).
    code_suivi = models.CharField(max_length=12, unique=True, blank=True, editable=False)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="dossiers_maintenance")

    # --- Appareil déposé ---
    marque = models.CharField(max_length=60)
    modele = models.CharField("Modèle", max_length=100)
    imei = models.CharField("IMEI / N° de série", max_length=40, blank=True)
    couleur = models.CharField(max_length=40, blank=True)
    code_deverrouillage = models.CharField(
        "Code de déverrouillage", max_length=40, blank=True,
        help_text="Confidentiel : jamais affiché sur le portail public.",
    )
    accessoires_deposes = models.CharField(
        "Accessoires déposés", max_length=255, blank=True,
        help_text="Ex : chargeur, coque, carte SIM, carte mémoire...",
    )
    etat_visuel = models.TextField("État visuel à la réception", blank=True)
    panne_declaree = models.TextField("Panne déclarée par le client")

    # --- Suivi atelier ---
    statut = models.CharField(max_length=15, choices=STATUT_CHOIX, default="RECU")
    technicien = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dossiers_maintenance",
    )
    diagnostic = models.TextField(blank=True)
    travaux_effectues = models.TextField("Travaux effectués", blank=True)
    devis_montant = models.DecimalField("Montant du devis", max_digits=12, decimal_places=0, null=True, blank=True)
    devis_accepte = models.BooleanField("Devis accepté par le client", null=True, blank=True)
    acompte = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    sous_garantie = models.BooleanField(default=False)
    date_depot = models.DateTimeField("Date de dépôt", default=timezone.now)
    date_prevue = models.DateField("Date de retrait prévue", null=True, blank=True)
    date_restitution = models.DateTimeField(null=True, blank=True, editable=False)
    facture = models.ForeignKey(
        "ventes.Document", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dossiers_maintenance",
    )

    class Meta:
        ordering = ["-date_depot"]
        verbose_name = "Dossier de maintenance"
        verbose_name_plural = "Dossiers de maintenance"

    def __str__(self):
        return f"{self.numero} — {self.marque} {self.modele} ({self.client.nom})"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # On mémorise le statut au chargement pour détecter un CHANGEMENT
        # de statut à l'enregistrement (et l'historiser).
        self._statut_initial = self.statut

    def save(self, *args, **kwargs):
        nouveau = self.pk is None
        if not self.numero:
            self.numero = Compteur.prochain_numero("MNT")
        if not self.code_suivi:
            # 6 caractères faciles à lire (sans 0/O ni 1/I pour éviter les confusions)
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            self.code_suivi = "".join(secrets.choice(alphabet) for _ in range(6))
        if self.statut == "RESTITUE" and not self.date_restitution:
            self.date_restitution = timezone.now()
        super().save(*args, **kwargs)

        # Historique : une ligne à la création puis à chaque changement de statut
        if nouveau or self.statut != self._statut_initial:
            HistoriqueMaintenance.objects.create(dossier=self, statut=self.statut)
            # Notification du client (e-mail) selon le paramétrage de la messagerie :
            # accusé de dépôt à la création, puis avis à chaque changement de statut.
            from messagerie.services import notifier
            notifier("MAINT_DEPOT" if nouveau else "MAINT_STATUT", self.client, {"dossier": self})
            self._statut_initial = self.statut

    @property
    def etape(self) -> int:
        """Numéro d'étape pour la barre de progression (0 si hors parcours)."""
        correspondance = {"DEVIS": "DIAGNOSTIC", "ATTENTE_PIECE": "REPARATION", "IRREPARABLE": "PRET"}
        statut = correspondance.get(self.statut, self.statut)
        return self.ETAPES.index(statut) + 1 if statut in self.ETAPES else 0


class HistoriqueMaintenance(models.Model):
    """Journal des changements de statut (visible par le client sur le portail)."""

    dossier = models.ForeignKey(DossierMaintenance, on_delete=models.CASCADE, related_name="historique")
    date = models.DateTimeField(default=timezone.now)
    statut = models.CharField(max_length=15, choices=DossierMaintenance.STATUT_CHOIX)
    commentaire = models.CharField(
        "Commentaire (visible par le client)", max_length=255, blank=True
    )

    class Meta:
        ordering = ["date", "id"]
        verbose_name = "Étape de suivi"
        verbose_name_plural = "Historique de suivi"

    def __str__(self):
        return f"{self.date:%d/%m/%Y %H:%M} — {self.get_statut_display()}"


class PieceUtilisee(models.Model):
    """
    Pièce détachée consommée pendant la réparation.
    Son enregistrement fait automatiquement SORTIR la pièce du stock.
    """

    dossier = models.ForeignKey(DossierMaintenance, on_delete=models.CASCADE, related_name="pieces")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT)
    quantite = models.PositiveIntegerField(default=1)
    mouvement = models.OneToOneField(
        "stock.MouvementStock", on_delete=models.SET_NULL, null=True, blank=True, editable=False
    )

    class Meta:
        verbose_name = "Pièce utilisée"
        verbose_name_plural = "Pièces utilisées"

    def __str__(self):
        return f"{self.quantite} x {self.produit.nom}"

    def clean(self):
        # On refuse d'utiliser plus de pièces qu'il n'y en a en stock
        from django.core.exceptions import ValidationError

        if self.pk is None and self.produit_id and self.produit.est_stockable:
            if self.quantite > self.produit.stock:
                raise ValidationError(
                    f"Stock insuffisant pour « {self.produit.nom} » ({self.produit.stock} disponible(s))."
                )

    def save(self, *args, **kwargs):
        from stock.models import MouvementStock

        super().save(*args, **kwargs)
        if self.mouvement_id is None and self.produit.est_stockable:
            self.mouvement = MouvementStock.objects.create(
                produit=self.produit, type_mouvement="S", motif="MAINT",
                quantite=self.quantite, reference=self.dossier.numero,
            )
            super().save(update_fields=["mouvement"])

    def delete(self, *args, **kwargs):
        # Retirer la pièce du dossier = annuler la sortie de stock correspondante
        if self.mouvement:
            self.mouvement.delete()
        return super().delete(*args, **kwargs)
