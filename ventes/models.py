"""
Ventes : factures et proformas multi-lignes, règlements, commandes du portail.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from catalogue.models import Produit
from core.models import Compteur, Entreprise
from core.utils import montant_en_lettres
from tiers.models import Client


def arrondi(valeur) -> Decimal:
    """Arrondi à l'unité (le FCFA n'a pas de centimes)."""
    return Decimal(valeur).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


# ======================================================================
#  FACTURES ET PROFORMAS
# ======================================================================
class Document(models.Model):
    """
    Document commercial : PROFORMA (devis) ou FACTURE.
    Les deux partagent la même structure (en-tête + lignes de détail),
    seul leur cycle de vie diffère :

    - Proforma : numérotée dès sa création (PRO-2026-00001), sans effet sur
      le stock. Elle peut être « convertie » en facture en un clic.
    - Facture  : reste en BROUILLON (modifiable, sans numéro) jusqu'à sa
      VALIDATION. La validation lui attribue son numéro définitif
      (FAC-2026-00001, sans trou dans la numérotation) et fait sortir du
      stock les articles vendus. Une facture validée n'est plus modifiable :
      on l'annule (le stock est alors réintégré).
    """

    TYPE_CHOIX = [("PRO", "Proforma"), ("FAC", "Facture")]
    STATUT_CHOIX = [("BROUILLON", "Brouillon"), ("VALIDE", "Validé"), ("ANNULE", "Annulé")]

    type_document = models.CharField("Type", max_length=3, choices=TYPE_CHOIX, default="FAC")
    numero = models.CharField("N°", max_length=30, unique=True, null=True, blank=True, editable=False)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="documents")
    date = models.DateField(default=timezone.localdate)
    date_echeance = models.DateField(
        "Échéance / validité", null=True, blank=True,
        help_text="Date limite de paiement (facture) ou de validité (proforma).",
    )
    statut = models.CharField(max_length=10, choices=STATUT_CHOIX, default="BROUILLON", editable=False)
    objet = models.CharField(max_length=200, blank=True)
    notes = models.TextField("Notes (imprimées sur le document)", blank=True)
    # Traçabilité : proforma d'origine, commande en ligne d'origine
    proforma_origine = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, editable=False,
        related_name="factures_generees",
    )
    commande_origine = models.ForeignKey(
        "Commande", on_delete=models.SET_NULL, null=True, blank=True, editable=False,
        related_name="factures",
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, editable=False
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "Facture / Proforma"
        verbose_name_plural = "Factures & Proformas"

    def __str__(self):
        return f"{self.get_type_document_display()} {self.numero or '(brouillon)'} — {self.client.nom}"

    def save(self, *args, **kwargs):
        # Une proforma reçoit son numéro dès la création ; une facture, à la validation.
        if not self.numero and self.type_document == "PRO":
            self.numero = Compteur.prochain_numero("PRO")
        # Date de validité par défaut d'une proforma, selon la fiche entreprise
        if self.type_document == "PRO" and not self.date_echeance:
            self.date_echeance = self.date + timedelta(
                days=Entreprise.get().validite_proforma_jours
            )
        super().save(*args, **kwargs)

    def get_impression_url(self):
        return reverse("core:imprimer_document", args=[self.pk])

    # ----- Totaux (calculés à partir des lignes, jamais saisis) -----
    @property
    def total_ht(self):
        return sum((l.montant_ht for l in self.lignes.all()), Decimal(0))

    @property
    def total_tva(self):
        return sum((l.montant_tva for l in self.lignes.all()), Decimal(0))

    @property
    def total_ttc(self):
        return sum((l.montant_ttc for l in self.lignes.all()), Decimal(0))

    @property
    def total_regle(self):
        return sum((r.montant for r in self.reglements.all()), Decimal(0))

    @property
    def reste_a_payer(self):
        return max(self.total_ttc - self.total_regle, Decimal(0))

    @property
    def statut_paiement(self) -> str:
        if self.type_document != "FAC":
            return "—"
        if self.total_regle <= 0:
            return "Non payée"
        if self.reste_a_payer > 0:
            return "Partiellement payée"
        return "Payée"

    @property
    def total_en_lettres(self) -> str:
        return montant_en_lettres(self.total_ttc, Entreprise.get().devise)

    @property
    def modifiable(self) -> bool:
        """Seuls les brouillons de facture et les proformas actives se modifient."""
        if self.type_document == "FAC":
            return self.statut == "BROUILLON"
        return self.statut != "ANNULE"

    # ----- Actions métier -----
    def valider(self, utilisateur=None):
        """
        Valide une facture : contrôle du stock, attribution du numéro
        définitif, puis une sortie de stock par ligne d'article stockable.
        Tout se fait dans UNE transaction : en cas d'erreur, rien n'est enregistré.
        """
        from stock.models import MouvementStock  # import local (évite une boucle d'imports)

        if self.type_document != "FAC":
            raise ValidationError("Seule une facture peut être validée.")
        if self.statut != "BROUILLON":
            raise ValidationError(f"La facture {self} n'est pas un brouillon.")
        lignes = list(self.lignes.select_related("produit"))
        if not lignes:
            raise ValidationError("Impossible de valider une facture sans ligne.")

        with transaction.atomic():
            # 1) Vérification du stock (verrouillage des produits concernés)
            besoins = {}
            for l in lignes:
                if l.produit and l.produit.est_stockable:
                    besoins[l.produit_id] = besoins.get(l.produit_id, 0) + l.quantite
            produits = Produit.objects.select_for_update().in_bulk(list(besoins))
            manquants = [
                f"{produits[pid].nom} (dispo {produits[pid].stock}, demandé {qte})"
                for pid, qte in besoins.items()
                if produits[pid].stock < qte
            ]
            if manquants:
                raise ValidationError("Stock insuffisant : " + " ; ".join(manquants))

            # 2) Numéro définitif + statut
            self.numero = Compteur.prochain_numero("FAC")
            self.statut = "VALIDE"
            self.date_validation = timezone.now()
            self.save(update_fields=["numero", "statut", "date_validation"])

            # 3) Sorties de stock
            for l in lignes:
                if l.produit and l.produit.est_stockable:
                    MouvementStock.objects.create(
                        produit=l.produit, type_mouvement="S", motif="VENTE",
                        quantite=l.quantite, reference=self.numero,
                        commentaire=f"Client : {self.client.nom}", utilisateur=utilisateur,
                    )

    def annuler(self, utilisateur=None):
        """Annule le document ; pour une facture validée, réintègre le stock."""
        from stock.models import MouvementStock

        if self.statut == "ANNULE":
            raise ValidationError("Document déjà annulé.")
        with transaction.atomic():
            if self.type_document == "FAC" and self.statut == "VALIDE":
                for l in self.lignes.select_related("produit"):
                    if l.produit and l.produit.est_stockable:
                        MouvementStock.objects.create(
                            produit=l.produit, type_mouvement="E", motif="RETOUR",
                            quantite=l.quantite, reference=self.numero,
                            commentaire="Annulation de facture", utilisateur=utilisateur,
                        )
            self.statut = "ANNULE"
            self.save(update_fields=["statut"])

    def convertir_en_facture(self, utilisateur=None) -> "Document":
        """Crée une facture BROUILLON reprenant toutes les lignes de la proforma."""
        if self.type_document != "PRO":
            raise ValidationError("Seule une proforma peut être convertie en facture.")
        if self.statut == "ANNULE":
            raise ValidationError("Cette proforma est annulée.")
        with transaction.atomic():
            facture = Document.objects.create(
                type_document="FAC", client=self.client, objet=self.objet,
                notes=self.notes, proforma_origine=self, cree_par=utilisateur,
            )
            for l in self.lignes.all():
                l.pk = None          # pk=None -> Django créera une NOUVELLE ligne (copie)
                l.document = facture
                l.save()
            # La proforma est marquée "validée" = acceptée par le client
            self.statut = "VALIDE"
            self.save(update_fields=["statut"])
        return facture


class LigneDocument(models.Model):
    """
    Ligne de détail d'une facture/proforma.
    Le produit est facultatif : on peut saisir une ligne libre
    (ex : « Frais de livraison », « Configuration du téléphone »).
    """

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, null=True, blank=True)
    designation = models.CharField("Désignation", max_length=255, blank=True)
    quantite = models.PositiveIntegerField("Qté", default=1)
    prix_unitaire = models.DecimalField("P.U. HT", max_digits=12, decimal_places=0, null=True, blank=True)
    remise_pct = models.DecimalField("Remise %", max_digits=5, decimal_places=2, default=0)
    taux_tva = models.DecimalField("TVA %", max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Ligne"

    def __str__(self):
        return f"{self.quantite} x {self.designation}"

    def save(self, *args, **kwargs):
        # Valeurs par défaut reprises du produit et de la fiche entreprise,
        # pour ne saisir que le produit et la quantité dans la majorité des cas.
        if self.produit:
            if not self.designation:
                self.designation = self.produit.nom
            if self.prix_unitaire is None:
                self.prix_unitaire = self.produit.prix_vente
        if self.prix_unitaire is None:
            self.prix_unitaire = 0
        if self.taux_tva is None:
            self.taux_tva = Entreprise.get().taux_tva_defaut
        super().save(*args, **kwargs)

    def clean(self):
        if not self.produit and not self.designation:
            raise ValidationError("Choisissez un produit ou saisissez une désignation.")

    @property
    def montant_ht(self):
        brut = (self.prix_unitaire or 0) * (self.quantite or 0)
        return arrondi(brut * (1 - (self.remise_pct or 0) / Decimal(100)))

    @property
    def montant_tva(self):
        return arrondi(self.montant_ht * (self.taux_tva or 0) / Decimal(100))

    @property
    def montant_ttc(self):
        return self.montant_ht + self.montant_tva


class Reglement(models.Model):
    """Paiement (total ou partiel) reçu pour une facture."""

    MODE_CHOIX = [
        ("ESP", "Espèces"),
        ("OM", "Orange Money"),
        ("MOOV", "Moov Money"),
        ("CB", "Carte bancaire"),
        ("VIR", "Virement"),
        ("CHQ", "Chèque"),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="reglements")
    date = models.DateField(default=timezone.localdate)
    montant = models.DecimalField(max_digits=12, decimal_places=0)
    mode = models.CharField(max_length=4, choices=MODE_CHOIX, default="ESP")
    reference = models.CharField("Réf. transaction", max_length=60, blank=True)

    class Meta:
        verbose_name = "Règlement"

    def __str__(self):
        return f"{self.montant} ({self.get_mode_display()})"


# ======================================================================
#  COMMANDES PASSÉES SUR LE PORTAIL PUBLIC
# ======================================================================
class Commande(models.Model):
    """
    Commande passée par un client sur le site public.
    Le client la suit avec son numéro (CMD-2026-00001) et son téléphone.
    Quand elle est prête, le personnel génère la facture en un clic.
    """

    STATUT_CHOIX = [
        ("RECUE", "Reçue"),
        ("CONFIRMEE", "Confirmée"),
        ("PREPARATION", "En préparation"),
        ("PRETE", "Prête (retrait / expédition)"),
        ("LIVREE", "Livrée"),
        ("ANNULEE", "Annulée"),
    ]
    LIVRAISON_CHOIX = [("RETRAIT", "Retrait en boutique"), ("LIVRAISON", "Livraison à domicile")]

    numero = models.CharField("N° commande", max_length=30, unique=True, blank=True, editable=False)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="commandes")
    date = models.DateTimeField(default=timezone.now)
    statut = models.CharField(max_length=12, choices=STATUT_CHOIX, default="RECUE")
    mode_livraison = models.CharField(max_length=10, choices=LIVRAISON_CHOIX, default="RETRAIT")
    adresse_livraison = models.TextField(blank=True)
    message_client = models.TextField("Message du client", blank=True)
    note_interne = models.TextField(blank=True)
    date_maj = models.DateTimeField("Dernière mise à jour", auto_now=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Commande en ligne"
        verbose_name_plural = "Commandes en ligne"

    def __str__(self):
        return f"{self.numero} — {self.client.nom}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Statut au chargement : sert à détecter un changement pour prévenir le client
        self._statut_initial = self.statut

    def save(self, *args, **kwargs):
        nouveau = self.pk is None
        if not self.numero:
            self.numero = Compteur.prochain_numero("CMD")
        super().save(*args, **kwargs)
        if not nouveau and self.statut != self._statut_initial:
            from messagerie.services import notifier
            notifier("CMD_STATUT", self.client, {"commande": self})
        self._statut_initial = self.statut

    @property
    def total(self):
        return sum((l.montant for l in self.lignes.all()), Decimal(0))

    @property
    def etape(self) -> int:
        """Position dans le suivi (pour la barre de progression du portail)."""
        ordre = ["RECUE", "CONFIRMEE", "PREPARATION", "PRETE", "LIVREE"]
        return ordre.index(self.statut) + 1 if self.statut in ordre else 0

    def generer_facture(self, utilisateur=None) -> Document:
        """Crée une facture BROUILLON avec les lignes de la commande."""
        if self.factures.exclude(statut="ANNULE").exists():
            raise ValidationError(f"La commande {self.numero} a déjà une facture.")
        with transaction.atomic():
            facture = Document.objects.create(
                type_document="FAC", client=self.client, commande_origine=self,
                objet=f"Commande en ligne {self.numero}", cree_par=utilisateur,
            )
            for l in self.lignes.select_related("produit"):
                LigneDocument.objects.create(
                    document=facture, produit=l.produit, designation=l.produit.nom,
                    quantite=l.quantite, prix_unitaire=l.prix_unitaire,
                )
        return facture


class LigneCommande(models.Model):
    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, related_name="lignes")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT)
    quantite = models.PositiveIntegerField(default=1)
    # Prix figé au moment de la commande (le prix catalogue peut changer ensuite)
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=0)

    class Meta:
        verbose_name = "Ligne de commande"

    def __str__(self):
        return f"{self.quantite} x {self.produit.nom}"

    @property
    def montant(self):
        return (self.prix_unitaire or 0) * (self.quantite or 0)
