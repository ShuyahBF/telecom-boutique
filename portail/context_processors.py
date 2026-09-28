"""Nombre d'articles du panier, affiché dans l'en-tête de toutes les pages publiques."""

from .panier import CLE_SESSION


def panier(request):
    contenu = request.session.get(CLE_SESSION, {}) if hasattr(request, "session") else {}
    return {"panier_nb": sum(contenu.values())}
