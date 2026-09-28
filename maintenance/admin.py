"""Écrans d'administration des dossiers de maintenance."""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .models import DossierMaintenance, HistoriqueMaintenance, PieceUtilisee


class HistoriqueInline(admin.TabularInline):
    """Historique des statuts : lecture seule, sauf le commentaire visible par le client."""

    model = HistoriqueMaintenance
    extra = 0
    fields = ("date", "statut", "commentaire")
    readonly_fields = ("date", "statut")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False  # les lignes sont créées automatiquement à chaque changement de statut


class PieceInline(admin.TabularInline):
    model = PieceUtilisee
    extra = 1
    autocomplete_fields = ("produit",)

    def has_change_permission(self, request, obj=None):
        # Une pièce enregistrée a déjà été déstockée : on la supprime puis on la ressaisit
        return False


@admin.register(DossierMaintenance)
class DossierMaintenanceAdmin(admin.ModelAdmin):
    list_display = ("numero", "date_depot", "client", "marque", "modele", "statut", "technicien", "date_prevue")
    list_filter = ("statut", "technicien", "sous_garantie", "marque")
    search_fields = ("numero", "code_suivi", "imei", "client__nom", "client__telephone", "modele")
    autocomplete_fields = ("client", "facture")
    date_hierarchy = "date_depot"
    readonly_fields = ("numero", "code_suivi", "date_restitution")
    inlines = [PieceInline, HistoriqueInline]
    actions = ["generer_facture"]
    fieldsets = (
        ("Dossier", {"fields": ("numero", "code_suivi", "client", "date_depot", "date_prevue", "statut", "technicien")}),
        ("Appareil déposé", {"fields": (
            ("marque", "modele"), ("imei", "couleur"), "code_deverrouillage",
            "accessoires_deposes", "etat_visuel", "panne_declaree",
        )}),
        ("Atelier", {"fields": (
            "diagnostic", "travaux_effectues", ("devis_montant", "devis_accepte"),
            ("acompte", "sous_garantie"), "facture", "date_restitution",
        )}),
    )

    @admin.action(description="Générer la facture de réparation (brouillon)")
    def generer_facture(self, request, queryset):
        """Crée une facture avec le montant du devis + les pièces utilisées."""
        from ventes.models import Document, LigneDocument

        for dossier in queryset:
            if dossier.facture_id:
                self.message_user(request, f"{dossier.numero} a déjà une facture.", messages.WARNING)
                continue
            try:
                facture = Document.objects.create(
                    type_document="FAC", client=dossier.client, cree_par=request.user,
                    objet=f"Réparation {dossier.marque} {dossier.modele} — dossier {dossier.numero}",
                )
                if dossier.devis_montant:
                    LigneDocument.objects.create(
                        document=facture, designation=f"Main d'œuvre — {dossier.travaux_effectues or 'réparation'}"[:255],
                        quantite=1, prix_unitaire=dossier.devis_montant,
                    )
                # Les pièces sont déjà sorties du stock par le dossier : on les facture
                # en ligne LIBRE (sans produit) pour ne pas les déstocker une 2e fois.
                for piece in dossier.pieces.select_related("produit"):
                    LigneDocument.objects.create(
                        document=facture, designation=f"Pièce : {piece.produit.nom}",
                        quantite=piece.quantite, prix_unitaire=piece.produit.prix_vente,
                    )
                dossier.facture = facture
                dossier.save(update_fields=["facture"])
                self.message_user(request, f"Facture brouillon créée pour {dossier.numero}.")
            except ValidationError as e:
                self.message_user(request, " ".join(e.messages), messages.ERROR)
