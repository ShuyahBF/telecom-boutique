"""
Tiers de l'entreprise : clients et fournisseurs.
"""

from django.db import models

from core.utils import normaliser_telephone


class Client(models.Model):
    """Client (particulier ou entreprise), créé au comptoir ou via le portail."""

    TYPE_CHOIX = [("PART", "Particulier"), ("ENTR", "Entreprise")]

    type_client = models.CharField("Type", max_length=4, choices=TYPE_CHOIX, default="PART")
    nom = models.CharField("Nom / Raison sociale", max_length=150)
    telephone = models.CharField("Téléphone", max_length=30, db_index=True)
    email = models.EmailField("E-mail", blank=True)
    adresse = models.TextField(blank=True)
    ifu = models.CharField("N° IFU (entreprise)", max_length=50, blank=True)
    notes = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return f"{self.nom} ({self.telephone})"

    def save(self, *args, **kwargs):
        # Téléphone enregistré sans espaces ni tirets : indispensable pour
        # retrouver le client quand il suit sa commande depuis le portail.
        self.telephone = normaliser_telephone(self.telephone)
        super().save(*args, **kwargs)


class Fournisseur(models.Model):
    """Fournisseur d'appareils, d'accessoires ou de pièces détachées."""

    nom = models.CharField("Raison sociale", max_length=150)
    contact = models.CharField("Personne à contacter", max_length=100, blank=True)
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    email = models.EmailField("E-mail", blank=True)
    adresse = models.TextField(blank=True)
    pays = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom
