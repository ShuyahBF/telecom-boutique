"""
Modèles transverses : fiche entreprise et compteurs de numérotation.
"""

from django.db import models, transaction
from django.utils import timezone


class Entreprise(models.Model):
    """
    Fiche d'identité de l'entreprise (UNE SEULE ligne en base).
    Ces informations apparaissent sur les factures, proformas, bons de dépôt
    et dans l'en-tête / pied de page du portail public.
    """

    nom = models.CharField("Raison sociale", max_length=150, default="TelecomPro")
    slogan = models.CharField(max_length=200, blank=True)
    adresse = models.TextField(blank=True)
    telephone = models.CharField("Téléphone", max_length=50, blank=True)
    email = models.EmailField("E-mail", blank=True)
    ifu = models.CharField("N° IFU / NIF", max_length=50, blank=True)
    rccm = models.CharField("N° RCCM", max_length=50, blank=True)
    logo = models.ImageField(upload_to="entreprise/", blank=True)
    devise = models.CharField(max_length=10, default="FCFA")
    taux_tva_defaut = models.DecimalField(
        "Taux TVA par défaut (%)", max_digits=5, decimal_places=2, default=18
    )
    conditions_facture = models.TextField(
        "Mentions en pied de facture",
        blank=True,
        default="Les marchandises vendues ne sont ni reprises ni échangées.",
    )
    validite_proforma_jours = models.PositiveIntegerField(
        "Validité des proformas (jours)", default=15
    )

    class Meta:
        verbose_name = "Fiche entreprise"
        verbose_name_plural = "Fiche entreprise"

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        # On force toujours l'identifiant 1 : il ne peut exister qu'une fiche.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls) -> "Entreprise":
        """Renvoie la fiche entreprise, en la créant si elle n'existe pas encore."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Compteur(models.Model):
    """
    Compteur de numérotation automatique, un par préfixe ET par année.
    Exemple : préfixe "FAC" en 2026 -> FAC-2026-00001, FAC-2026-00002...
    La numérotation repart à 1 chaque nouvelle année.
    """

    prefixe = models.CharField(max_length=10)
    annee = models.PositiveIntegerField()
    dernier_numero = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("prefixe", "annee")
        verbose_name = "Compteur de numérotation"
        verbose_name_plural = "Compteurs de numérotation"

    def __str__(self):
        return f"{self.prefixe}-{self.annee} : {self.dernier_numero}"

    @classmethod
    def prochain_numero(cls, prefixe: str) -> str:
        """
        Réserve et renvoie le prochain numéro pour ce préfixe.

        select_for_update() verrouille la ligne du compteur le temps de la
        transaction : deux ventes enregistrées au même instant ne peuvent donc
        JAMAIS obtenir le même numéro (équivalent d'un blocage d'enregistrement
        HFSQL pendant l'incrémentation).
        """
        annee = timezone.localdate().year
        with transaction.atomic():
            compteur, _ = cls.objects.select_for_update().get_or_create(
                prefixe=prefixe, annee=annee
            )
            compteur.dernier_numero += 1
            compteur.save(update_fields=["dernier_numero"])
            return f"{prefixe}-{annee}-{compteur.dernier_numero:05d}"
