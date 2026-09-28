from django.apps import AppConfig


class TiersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tiers"
    # Titre de la section dans l'administration
    verbose_name = "Clients & fournisseurs"
