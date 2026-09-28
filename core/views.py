"""
Pages du back-office : tableau de bord et documents imprimables.

@staff_member_required : seules les personnes ayant accès à
l'administration (case « Statut équipe » cochée) peuvent ouvrir ces pages.
"""

from datetime import timedelta

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from catalogue.models import Produit
from maintenance.models import DossierMaintenance
from messagerie.models import Conversation
from ventes.models import Commande, Document, LigneDocument


@staff_member_required
def tableau_de_bord(request):
    """Indicateurs clés de l'activité, en une page."""
    aujourd_hui = timezone.localdate()
    debut_mois = aujourd_hui.replace(day=1)

    # Chiffre d'affaires HT du mois : somme (quantité x prix x (1 - remise)) des factures validées.
    # Calcul fait par la base de données (une seule requête), pas en Python.
    lignes_mois = LigneDocument.objects.filter(
        document__type_document="FAC", document__statut="VALIDE", document__date__gte=debut_mois
    )
    ca_mois = lignes_mois.aggregate(
        total=Sum(F("quantite") * F("prix_unitaire") * (100 - F("remise_pct")) / 100)
    )["total"] or 0

    contexte = {
        # Variables de l'administration (titre du site, liens utilisateur...) pour
        # que le tableau de bord ait exactement le même en-tête que l'admin
        **admin.site.each_context(request),
        "ca_mois": ca_mois,
        "nb_factures_mois": Document.objects.filter(
            type_document="FAC", statut="VALIDE", date__gte=debut_mois
        ).count(),
        "brouillons": Document.objects.filter(type_document="FAC", statut="BROUILLON").count(),
        "commandes_a_traiter": Commande.objects.filter(statut__in=["RECUE", "CONFIRMEE", "PREPARATION"])
        .select_related("client")[:10],
        "dossiers_en_cours": DossierMaintenance.objects.exclude(statut="RESTITUE")
        .select_related("client").order_by("date_prevue")[:10],
        "dossiers_en_retard": DossierMaintenance.objects.exclude(statut__in=["RESTITUE", "PRET", "IRREPARABLE"])
        .filter(date_prevue__lt=aujourd_hui).count(),
        "produits_alerte": Produit.objects.filter(actif=True, stock__lte=F("stock_alerte"))
        .exclude(type_produit="SER").order_by("stock")[:15],
        "conversations_attente": Conversation.objects.filter(statut="ATTENTE")[:10],
        "dossiers_semaine": DossierMaintenance.objects.filter(
            date_depot__date__gte=aujourd_hui - timedelta(days=7)
        ).count(),
    }
    return render(request, "gestion/tableau_de_bord.html", contexte)


@staff_member_required
def imprimer_document(request, pk):
    """Facture ou proforma au format A4 (Ctrl+P -> « Enregistrer en PDF »)."""
    document = get_object_or_404(
        Document.objects.select_related("client").prefetch_related("lignes", "reglements"), pk=pk
    )
    return render(request, "gestion/document_imprimable.html", {"doc": document})


@staff_member_required
def imprimer_depot(request, pk):
    """Bon de dépôt remis au client avec son numéro de dossier et son code de suivi."""
    dossier = get_object_or_404(DossierMaintenance.objects.select_related("client"), pk=pk)
    return render(request, "gestion/bon_depot.html", {"dossier": dossier})
