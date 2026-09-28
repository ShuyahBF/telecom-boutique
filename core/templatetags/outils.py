"""
Filtres de gabarits maison. Utilisation dans un .html :
    {% load outils %}
    {{ produit.prix_vente|montant }}   ->  125 000
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def montant(valeur):
    """Formate un nombre avec un espace comme séparateur de milliers, sans décimales."""
    try:
        n = Decimal(valeur or 0).quantize(Decimal("1"))
    except (InvalidOperation, TypeError, ValueError):
        return valeur
    # format(..., ",") met des virgules ; on les remplace par des espaces insécables
    return f"{n:,}".replace(",", " ")
