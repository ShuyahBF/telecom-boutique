"""
Table de routage principale (quelle adresse -> quelle page).

- /             : portail public (vitrine, panier, suivi commande/maintenance)
- /gestion/     : back-office du personnel (tableau de bord, impressions)
- /admin/       : administration Django (saisie de toutes les données)
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

# Personnalisation des titres de l'interface d'administration
admin.site.site_header = "TelecomPro — Back-office"
admin.site.site_title = "TelecomPro"
admin.site.index_title = "Gestion de l'entreprise"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("gestion/", include("core.urls")),
    path("", include("portail.urls")),
]

# En développement uniquement : Django sert lui-même les fichiers envoyés
# (photos produits, logo). En production, c'est le serveur web qui s'en charge.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
