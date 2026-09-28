from django.apps import AppConfig


class MaintenanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "maintenance"
    # Titre de la section dans l'administration
    verbose_name = "Maintenance (SAV)"
