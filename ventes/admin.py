"""
Écrans d'administration des ventes : factures/proformas multi-lignes,
règlements et commandes du portail.

Les boutons « Valider », « Convertir en facture », « Annuler » et
« Imprimer » apparaissent en haut à droite de la fiche d'un document
(gabarit templates/admin/ventes/document/change_form.html).
"""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html

from .models import Commande, Document, LigneCommande, LigneDocument, Reglement


class LigneDocumentInline(admin.TabularInline):
    """Tableau des lignes de détail, saisi directement dans la fiche du document."""

    model = LigneDocument
    extra = 3
    autocomplete_fields = ("produit",)
    fields = ("produit", "designation", "quantite", "prix_unitaire", "remise_pct", "taux_tva", "total_ligne")
    readonly_fields = ("total_ligne",)

    @admin.display(description="Total TTC")
    def total_ligne(self, obj):
        return f"{obj.montant_ttc:,.0f}".replace(",", " ") if obj.pk else "—"

    # Lignes verrouillées dès que le document n'est plus modifiable (facture validée...)
    def has_add_permission(self, request, obj=None):
        return obj is None or obj.modifiable

    def has_change_permission(self, request, obj=None):
        return obj is None or obj.modifiable

    def has_delete_permission(self, request, obj=None):
        return obj is None or obj.modifiable


class ReglementInline(admin.TabularInline):
    model = Reglement
    extra = 1


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "numero_affiche", "type_document", "date", "client", "total_ttc_affiche",
        "statut", "paiement", "lien_impression",
    )
    list_filter = ("type_document", "statut", "date")
    search_fields = ("numero", "client__nom", "client__telephone", "objet")
    autocomplete_fields = ("client",)
    date_hierarchy = "date"
    inlines = [LigneDocumentInline, ReglementInline]
    readonly_fields = (
        "numero", "statut", "totaux", "proforma_origine", "commande_origine",
        "cree_par", "date_validation",
    )
    fieldsets = (
        (None, {"fields": ("type_document", "numero", "statut", "client", "date", "date_echeance", "objet")}),
        ("Totaux", {"fields": ("totaux",)}),
        ("Informations", {"fields": ("notes", "proforma_origine", "commande_origine", "cree_par", "date_validation"),
                          "classes": ("collapse",)}),
    )

    # ----- Colonnes calculées -----
    @admin.display(description="N°", ordering="numero")
    def numero_affiche(self, obj):
        return obj.numero or "(brouillon)"

    @admin.display(description="Total TTC")
    def total_ttc_affiche(self, obj):
        return f"{obj.total_ttc:,.0f}".replace(",", " ")

    @admin.display(description="Paiement")
    def paiement(self, obj):
        return obj.statut_paiement

    @admin.display(description="")
    def lien_impression(self, obj):
        return format_html('<a href="{}" target="_blank">🖨 Imprimer</a>', obj.get_impression_url())

    @admin.display(description="Totaux")
    def totaux(self, obj):
        if not obj.pk:
            return "Calculés après enregistrement des lignes."
        f = lambda v: f"{v:,.0f}".replace(",", " ")  # noqa: E731 — format 125 000
        return format_html(
            "HT : <b>{}</b> — TVA : <b>{}</b> — TTC : <b>{}</b><br>Réglé : {} — Reste : <b>{}</b><br><i>{}</i>",
            f(obj.total_ht), f(obj.total_tva), f(obj.total_ttc),
            f(obj.total_regle), f(obj.reste_a_payer), obj.total_en_lettres,
        )

    def get_readonly_fields(self, request, obj=None):
        # Document verrouillé : tous les champs d'en-tête passent en lecture seule
        champs = list(self.readonly_fields)
        if obj and not obj.modifiable:
            champs += ["type_document", "client", "date", "date_echeance", "objet", "notes"]
        elif obj:
            champs.append("type_document")  # on ne change pas le type après création
        return champs

    def has_delete_permission(self, request, obj=None):
        # Une facture validée ne se supprime JAMAIS (obligation légale de
        # numérotation continue) : on l'annule. Seuls les brouillons se suppriment.
        if obj is not None and obj.type_document == "FAC" and obj.statut != "BROUILLON":
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        # On retire la suppression en masse, qui contournerait le contrôle ci-dessus
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def save_model(self, request, obj, form, change):
        if not change:
            obj.cree_par = request.user
        super().save_model(request, obj, form, change)

    # ----- Boutons d'action sur la fiche (URL dédiées) -----
    def get_urls(self):
        propres = [
            path("<int:pk>/valider/", self.admin_site.admin_view(self.action_valider), name="ventes_document_valider"),
            path("<int:pk>/annuler/", self.admin_site.admin_view(self.action_annuler), name="ventes_document_annuler"),
            path("<int:pk>/convertir/", self.admin_site.admin_view(self.action_convertir), name="ventes_document_convertir"),
        ]
        return propres + super().get_urls()

    def _executer(self, request, pk, fonction, message_ok):
        """Exécute une action métier et affiche le résultat (succès ou erreur)."""
        doc = get_object_or_404(Document, pk=pk)
        if request.method != "POST":
            return redirect(reverse("admin:ventes_document_change", args=[pk]))
        try:
            resultat = fonction(doc, request.user)
            self.message_user(request, message_ok(doc, resultat), messages.SUCCESS)
            if isinstance(resultat, Document):
                return redirect(reverse("admin:ventes_document_change", args=[resultat.pk]))
        except ValidationError as e:
            self.message_user(request, " ".join(e.messages), messages.ERROR)
        return redirect(reverse("admin:ventes_document_change", args=[pk]))

    def action_valider(self, request, pk):
        return self._executer(request, pk, lambda d, u: d.valider(u),
                              lambda d, r: f"Facture validée sous le n° {d.numero}. Stock mis à jour.")

    def action_annuler(self, request, pk):
        return self._executer(request, pk, lambda d, u: d.annuler(u), lambda d, r: f"{d} annulé.")

    def action_convertir(self, request, pk):
        return self._executer(request, pk, lambda d, u: d.convertir_en_facture(u),
                              lambda d, r: "Facture brouillon créée à partir de la proforma. Vérifiez-la puis validez-la.")


class LigneCommandeInline(admin.TabularInline):
    model = LigneCommande
    extra = 0
    autocomplete_fields = ("produit",)


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ("numero", "date", "client", "total_affiche", "mode_livraison", "statut", "factures_liees")
    list_filter = ("statut", "mode_livraison", "date")
    list_editable = ("statut",)
    search_fields = ("numero", "client__nom", "client__telephone")
    autocomplete_fields = ("client",)
    readonly_fields = ("numero", "date_maj")
    inlines = [LigneCommandeInline]
    actions = ["generer_factures"]

    @admin.display(description="Total")
    def total_affiche(self, obj):
        return f"{obj.total:,.0f}".replace(",", " ")

    @admin.display(description="Facture")
    def factures_liees(self, obj):
        f = obj.factures.exclude(statut="ANNULE").first()
        if not f:
            return "—"
        url = reverse("admin:ventes_document_change", args=[f.pk])
        return format_html('<a href="{}">{}</a>', url, f.numero or "brouillon")

    @admin.action(description="Générer la facture (brouillon)")
    def generer_factures(self, request, queryset):
        for cmd in queryset:
            try:
                cmd.generer_facture(request.user)
                self.message_user(request, f"Facture brouillon créée pour {cmd.numero}.")
            except ValidationError as e:
                self.message_user(request, " ".join(e.messages), messages.WARNING)
