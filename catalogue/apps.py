from django.apps import AppConfig


class CatalogueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalogue"
    # Titre de la section dans l'administration
    verbose_name = "Catalogue"
