"""Écrans d'administration du catalogue."""

from django.contrib import admin
from django.utils.html import format_html

from .models import Categorie, Marque, Produit


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ("nom", "ordre")
    list_editable = ("ordre",)
    prepopulated_fields = {"slug": ("nom",)}


@admin.register(Marque)
class MarqueAdmin(admin.ModelAdmin):
    search_fields = ("nom",)


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = (
        "reference", "nom", "type_produit", "categorie", "marque",
        "prix_vente", "stock_affiche", "visible_portail", "actif",
    )
    list_filter = ("type_produit", "categorie", "marque", "visible_portail", "actif")
    search_fields = ("reference", "nom", "description")
    list_editable = ("prix_vente", "visible_portail")
    autocomplete_fields = ("marque",)
    readonly_fields = ("stock",)
    fieldsets = (
        (None, {"fields": ("reference", "nom", "slug", "type_produit", "categorie", "marque")}),
        ("Vitrine", {"fields": ("image", "description", "caracteristiques", "visible_portail", "actif")}),
        ("Prix et stock", {"fields": ("prix_achat", "prix_vente", "garantie_mois", "stock", "stock_alerte")}),
    )
    prepopulated_fields = {"slug": ("nom", "reference")}

    @admin.display(description="Stock", ordering="stock")
    def stock_affiche(self, obj):
        """Affiche le stock en rouge quand il atteint le seuil d'alerte."""
        if not obj.est_stockable:
            return "—"
        couleur = "#c0392b" if obj.en_alerte else "#1e8449"
        return format_html('<b style="color:{}">{}</b>', couleur, obj.stock)
