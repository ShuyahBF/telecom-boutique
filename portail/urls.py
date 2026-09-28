"""Adresses du portail public."""

from django.urls import path

from . import views

app_name = "portail"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("catalogue/", views.catalogue, name="catalogue"),
    path("produit/<slug:slug>/", views.produit, name="produit"),
    path("panier/", views.panier, name="panier"),
    path("panier/ajouter/<int:pk>/", views.panier_ajouter, name="panier_ajouter"),
    path("panier/modifier/<int:pk>/", views.panier_modifier, name="panier_modifier"),
    path("panier/retirer/<int:pk>/", views.panier_retirer, name="panier_retirer"),
    path("commander/", views.commander, name="commander"),
    path("commander/merci/", views.commande_confirmee, name="commande_confirmee"),
    path("suivi/commande/", views.suivi_commande, name="suivi_commande"),
    path("suivi/maintenance/", views.suivi_maintenance, name="suivi_maintenance"),
    path("conseil/", views.conseil, name="conseil"),
    path("conseil/<str:jeton>/", views.conversation, name="conversation"),
]
