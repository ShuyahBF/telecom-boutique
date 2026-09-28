"""Écrans d'administration des clients et fournisseurs."""

from django.contrib import admin

from .models import Client, Fournisseur


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    # Colonnes de la liste, filtres à droite et champs de la barre de recherche
    list_display = ("nom", "telephone", "email", "type_client", "date_creation")
    list_filter = ("type_client",)
    search_fields = ("nom", "telephone", "email")


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ("nom", "contact", "telephone", "email", "pays", "actif")
    list_filter = ("actif", "pays")
    search_fields = ("nom", "contact", "telephone", "email")
