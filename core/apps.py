from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    # Titre de la section dans l'administration
    verbose_name = "Paramètres généraux"
