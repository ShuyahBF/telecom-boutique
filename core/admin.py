"""Écran d'administration de la fiche entreprise."""

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from .models import Compteur, Entreprise


@admin.register(Entreprise)
class EntrepriseAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not Entreprise.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Fiche unique : on ouvre directement le formulaire
        return redirect(reverse("admin:core_entreprise_change", args=[Entreprise.get().pk]))


@admin.register(Compteur)
class CompteurAdmin(admin.ModelAdmin):
    """Consultation des compteurs (modification réservée au super-administrateur)."""

    list_display = ("prefixe", "annee", "dernier_numero")

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
