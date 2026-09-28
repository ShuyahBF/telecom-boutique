"""
Gestion de stock : entrées, sorties et ajustements.

Principe (comme un journal comptable) : on n'écrit JAMAIS directement le
stock d'un produit. Chaque variation est un MouvementStock ; le stock du
produit est mis à jour automatiquement à l'enregistrement du mouvement.
On garde ainsi l'historique complet de qui a fait entrer/sortir quoi, quand
et pourquoi.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone

from catalogue.models import Produit
from core.models import Compteur
from tiers.models import Fournisseur


class MouvementStock(models.Model):
    TYPE_CHOIX = [
        ("E", "Entrée"),
        ("S", "Sortie"),
    ]
    MOTIF_CHOIX = [
        ("ACHAT", "Réception fournisseur"),
        ("VENTE", "Vente / facture"),
        ("MAINT", "Pièce utilisée en maintenance"),
        ("RETOUR", "Retour client"),
        ("CASSE", "Casse / perte"),
        ("INVENT", "Ajustement d'inventaire"),
        ("AUTRE", "Autre"),
    ]

    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="mouvements")
    type_mouvement = models.CharField("Sens", max_length=1, choices=TYPE_CHOIX)
    motif = models.CharField(max_length=6, choices=MOTIF_CHOIX, default="AUTRE")
    quantite = models.PositiveIntegerField("Quantité")
    date = models.DateTimeField(default=timezone.now)
    reference = models.CharField(
        "Document lié", max_length=40, blank=True,
        help_text="N° de facture, de bon d'entrée, de dossier de maintenance...",
    )
    commentaire = models.CharField(max_length=255, blank=True)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"

    def __str__(self):
        signe = "+" if self.type_mouvement == "E" else "-"
        return f"{self.date:%d/%m/%Y} {signe}{self.quantite} {self.produit.nom}"

    @property
    def variation(self) -> int:
        """Quantité signée : positive pour une entrée, négative pour une sortie."""
        return self.quantite if self.type_mouvement == "E" else -self.quantite

    def clean(self):
        # Contrôle de saisie : on refuse une sortie supérieure au stock disponible.
        if self.pk is None and self.type_mouvement == "S" and self.produit_id:
            stock = Produit.objects.get(pk=self.produit_id).stock
            if self.quantite > stock:
                raise ValidationError(
                    f"Stock insuffisant pour « {self.produit.nom} » : "
                    f"{stock} disponible(s), {self.quantite} demandé(s)."
                )

    def save(self, *args, **kwargs):
        """
        À la CRÉATION du mouvement, on répercute la quantité sur le stock du
        produit. F("stock") fait le calcul directement dans la base de données
        (UPDATE produit SET stock = stock + x), ce qui évite les erreurs si deux
        vendeurs enregistrent un mouvement en même temps.
        Un mouvement déjà enregistré ne peut pas être modifié (voir admin) :
        pour corriger, on saisit un mouvement inverse.
        """
        nouveau = self.pk is None
        with transaction.atomic():
            super().save(*args, **kwargs)
            if nouveau:
                Produit.objects.filter(pk=self.produit_id).update(
                    stock=F("stock") + self.variation
                )

    def delete(self, *args, **kwargs):
        """Supprimer un mouvement annule son effet sur le stock."""
        with transaction.atomic():
            Produit.objects.filter(pk=self.produit_id).update(
                stock=F("stock") - self.variation
            )
            return super().delete(*args, **kwargs)


class BonEntree(models.Model):
    """
    Bon de réception fournisseur (plusieurs lignes de produits).
    Tant qu'il n'est pas VALIDÉ, il n'a aucun effet sur le stock ; la
    validation crée un mouvement d'entrée par ligne.
    """

    numero = models.CharField("N° bon", max_length=30, unique=True, blank=True, editable=False)
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.PROTECT, related_name="bons_entree")
    date = models.DateField(default=timezone.localdate)
    reference_fournisseur = models.CharField(
        "Réf. bon de livraison / facture fournisseur", max_length=60, blank=True
    )
    commentaire = models.TextField(blank=True)
    valide = models.BooleanField("Validé (stock mis à jour)", default=False, editable=False)
    date_validation = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "Bon d'entrée (réception)"
        verbose_name_plural = "Bons d'entrée (réceptions)"

    def __str__(self):
        return f"{self.numero} — {self.fournisseur}"

    def save(self, *args, **kwargs):
        # Numéro automatique à la première sauvegarde : BE-2026-00001
        if not self.numero:
            self.numero = Compteur.prochain_numero("BE")
        super().save(*args, **kwargs)

    @property
    def montant_total(self):
        return sum((l.montant for l in self.lignes.all()), 0)

    def valider(self, utilisateur=None):
        """Fait entrer en stock toutes les lignes du bon (une seule fois)."""
        if self.valide:
            raise ValidationError(f"Le bon {self.numero} est déjà validé.")
        with transaction.atomic():
            for ligne in self.lignes.select_related("produit"):
                MouvementStock.objects.create(
                    produit=ligne.produit,
                    type_mouvement="E",
                    motif="ACHAT",
                    quantite=ligne.quantite,
                    reference=self.numero,
                    commentaire=f"Fournisseur : {self.fournisseur.nom}",
                    utilisateur=utilisateur,
                )
                # On mémorise le dernier prix d'achat sur la fiche produit
                if ligne.prix_achat:
                    Produit.objects.filter(pk=ligne.produit_id).update(prix_achat=ligne.prix_achat)
            self.valide = True
            self.date_validation = timezone.now()
            self.save(update_fields=["valide", "date_validation"])


class LigneBonEntree(models.Model):
    bon = models.ForeignKey(BonEntree, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT)
    quantite = models.PositiveIntegerField("Quantité", default=1)
    prix_achat = models.DecimalField("Prix d'achat unitaire", max_digits=12, decimal_places=0, default=0)

    class Meta:
        verbose_name = "Ligne"

    def __str__(self):
        return f"{self.quantite} x {self.produit.nom}"

    @property
    def montant(self):
        return (self.prix_achat or 0) * (self.quantite or 0)
