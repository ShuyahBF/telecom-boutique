"""Adresses du back-office (réservé au personnel connecté)."""

from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.tableau_de_bord, name="tableau_de_bord"),
    path("documents/<int:pk>/imprimer/", views.imprimer_document, name="imprimer_document"),
    path("maintenance/<int:pk>/bon-de-depot/", views.imprimer_depot, name="imprimer_depot"),
]
