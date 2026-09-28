"""
Catalogue : catégories, marques et produits (téléphones, accessoires, pièces).
"""

from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Categorie(models.Model):
    """Rayon du catalogue : Smartphones, Téléphones basiques, Chargeurs, Coques..."""

    nom = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    ordre = models.PositiveIntegerField("Ordre d'affichage", default=0)

    class Meta:
        ordering = ["ordre", "nom"]
        verbose_name = "Catégorie"

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        # Le "slug" est la version du nom utilisable dans une adresse web
        # (ex: "Coques & étuis" -> "coques-etuis"). Généré automatiquement.
        if not self.slug:
            self.slug = slugify(self.nom)
        super().save(*args, **kwargs)


class Marque(models.Model):
    nom = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Produit(models.Model):
    """
    Article vendu ou utilisé en réparation.
    Le champ "stock" n'est JAMAIS modifié à la main : il est tenu à jour
    automatiquement par les mouvements de stock (application "stock").
    """

    TYPE_CHOIX = [
        ("TEL", "Téléphone"),
        ("ACC", "Accessoire"),
        ("PIE", "Pièce détachée"),
        ("SER", "Service (main d'œuvre...)"),
    ]

    reference = models.CharField("Référence", max_length=50, unique=True)
    nom = models.CharField("Désignation", max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    type_produit = models.CharField("Type", max_length=3, choices=TYPE_CHOIX, default="TEL")
    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name="produits")
    marque = models.ForeignKey(Marque, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    caracteristiques = models.TextField(
        "Caractéristiques techniques",
        blank=True,
        help_text="Une caractéristique par ligne, ex : « Écran : 6,5 pouces »",
    )
    image = models.ImageField(upload_to="produits/", blank=True)
    prix_achat = models.DecimalField("Prix d'achat", max_digits=12, decimal_places=0, default=0)
    prix_vente = models.DecimalField("Prix de vente", max_digits=12, decimal_places=0)
    stock = models.IntegerField("Stock actuel", default=0, editable=False)
    stock_alerte = models.PositiveIntegerField("Seuil d'alerte", default=2)
    garantie_mois = models.PositiveIntegerField("Garantie (mois)", default=0)
    visible_portail = models.BooleanField("Visible sur le site public", default=True)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return f"{self.reference} — {self.nom}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.nom}-{self.reference}")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Adresse de la fiche produit sur le portail public."""
        return reverse("portail:produit", args=[self.slug])

    @property
    def est_stockable(self) -> bool:
        """Les services (main d'œuvre) ne se stockent pas."""
        return self.type_produit != "SER"

    @property
    def en_alerte(self) -> bool:
        """Vrai si le stock est descendu au seuil d'alerte (ou en dessous)."""
        return self.est_stockable and self.stock <= self.stock_alerte

    @property
    def disponible(self) -> bool:
        return not self.est_stockable or self.stock > 0

    def liste_caracteristiques(self):
        """Découpe le champ texte en liste (une ligne = une caractéristique)."""
        return [l.strip() for l in self.caracteristiques.splitlines() if l.strip()]
