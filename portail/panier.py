"""
Panier d'achat stocké dans la SESSION du visiteur (aucun compte nécessaire).

La session est un petit espace mémoire propre à chaque navigateur, conservé
côté serveur. On y range un dictionnaire {id_produit: quantité}.
"""

from decimal import Decimal

from catalogue.models import Produit

CLE_SESSION = "panier"


class Panier:
    def __init__(self, request):
        self.session = request.session
        # Les clés JSON de session sont des textes : on garde les id en texte
        self.contenu = self.session.setdefault(CLE_SESSION, {})

    def _sauver(self):
        self.session.modified = True  # indique à Django que la session a changé

    def ajouter(self, produit: Produit, quantite: int = 1, remplacer: bool = False):
        cle = str(produit.pk)
        nouvelle = quantite if remplacer else self.contenu.get(cle, 0) + quantite
        # On ne propose jamais plus que le stock disponible
        if produit.est_stockable:
            nouvelle = min(nouvelle, produit.stock)
        if nouvelle <= 0:
            self.contenu.pop(cle, None)
        else:
            self.contenu[cle] = nouvelle
        self._sauver()

    def retirer(self, produit_id):
        self.contenu.pop(str(produit_id), None)
        self._sauver()

    def vider(self):
        self.session[CLE_SESSION] = {}
        self.contenu = self.session[CLE_SESSION]
        self._sauver()

    def lignes(self):
        """Liste des lignes du panier avec produit, quantité et sous-total."""
        produits = Produit.objects.filter(pk__in=self.contenu.keys(), actif=True, visible_portail=True)
        resultat = []
        for p in produits:
            qte = self.contenu[str(p.pk)]
            resultat.append({"produit": p, "quantite": qte, "sous_total": p.prix_vente * qte})
        return resultat

    @property
    def total(self):
        return sum((l["sous_total"] for l in self.lignes()), Decimal(0))

    def __len__(self):
        return sum(self.contenu.values())
