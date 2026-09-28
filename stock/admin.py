"""Écrans d'administration du stock (mouvements et bons d'entrée)."""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .models import BonEntree, LigneBonEntree, MouvementStock


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = ("date", "produit", "type_mouvement", "quantite", "motif", "reference", "utilisateur")
    list_filter = ("type_mouvement", "motif", "date")
    search_fields = ("produit__nom", "produit__reference", "reference", "commentaire")
    autocomplete_fields = ("produit",)
    date_hierarchy = "date"

    def get_readonly_fields(self, request, obj=None):
        # Un mouvement enregistré est figé : pour corriger, on saisit un mouvement inverse.
        if obj:
            return [f.name for f in self.model._meta.fields]
        return ("utilisateur",)

    def has_delete_permission(self, request, obj=None):
        # Supprimer un mouvement modifie le stock : réservé au super-administrateur.
        # Les autres utilisateurs saisissent un mouvement inverse pour corriger.
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        # On mémorise automatiquement l'utilisateur connecté
        if not change:
            obj.utilisateur = request.user
        super().save_model(request, obj, form, change)


class LigneBonEntreeInline(admin.TabularInline):
    model = LigneBonEntree
    extra = 3
    autocomplete_fields = ("produit",)

    # Une fois le bon validé, ses lignes ne sont plus modifiables
    def has_add_permission(self, request, obj=None):
        return not (obj and obj.valide)

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.valide)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.valide)


@admin.register(BonEntree)
class BonEntreeAdmin(admin.ModelAdmin):
    list_display = ("numero", "date", "fournisseur", "reference_fournisseur", "montant_total", "valide")
    list_filter = ("valide", "fournisseur")
    search_fields = ("numero", "reference_fournisseur", "fournisseur__nom")
    autocomplete_fields = ("fournisseur",)
    readonly_fields = ("numero", "valide", "date_validation")
    inlines = [LigneBonEntreeInline]
    actions = ["valider_bons"]

    @admin.action(description="Valider la réception (faire entrer en stock)")
    def valider_bons(self, request, queryset):
        for bon in queryset:
            try:
                bon.valider(request.user)
                self.message_user(request, f"{bon.numero} validé : stock mis à jour.")
            except ValidationError as e:
                self.message_user(request, "; ".join(e.messages), messages.ERROR)
