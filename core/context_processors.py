"""Variables injectées automatiquement dans toutes les pages HTML."""

from .models import Entreprise


def entreprise(request):
    # {{ entreprise.nom }}, {{ entreprise.devise }}... utilisables dans tous les gabarits
    return {"entreprise": Entreprise.get()}
