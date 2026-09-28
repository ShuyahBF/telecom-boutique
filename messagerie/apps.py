from django.apps import AppConfig


class MessagerieConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "messagerie"
    # Titre de la section dans l'administration
    verbose_name = "Centre de messagerie"
