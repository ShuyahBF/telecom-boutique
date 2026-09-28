from django.apps import AppConfig


class PortailConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "portail"
    # Titre de la section dans l'administration
    verbose_name = "Portail public"
