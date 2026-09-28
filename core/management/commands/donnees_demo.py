"""
Commande : python manage.py donnees_demo

Remplit la base avec des données d'exemple (catégories, marques, produits,
fournisseur, stock initial, clients, un dossier de maintenance) pour
découvrir la plateforme. Peut être relancée sans créer de doublons.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from catalogue.models import Categorie, Marque, Produit
from core.models import Entreprise
from maintenance.models import DossierMaintenance
from messagerie.services import assurer_modeles_par_defaut
from stock.models import BonEntree, LigneBonEntree
from tiers.models import Client, Fournisseur

# (référence, nom, type, catégorie, marque, prix achat, prix vente, quantité initiale, caractéristiques)
PRODUITS = [
    ("SAM-A15", "Samsung Galaxy A15 128 Go", "TEL", "Smartphones", "Samsung", 85000, 110000, 8,
     "Écran : 6,5 pouces\nStockage : 128 Go\nRAM : 4 Go\nBatterie : 5000 mAh"),
    ("TEC-SP20", "Tecno Spark 20 256 Go", "TEL", "Smartphones", "Tecno", 70000, 92000, 12,
     "Écran : 6,6 pouces\nStockage : 256 Go\nRAM : 8 Go\nDouble SIM"),
    ("INF-HOT40", "Infinix Hot 40i", "TEL", "Smartphones", "Infinix", 60000, 79000, 5,
     "Écran : 6,56 pouces\nStockage : 128 Go\nBatterie : 5000 mAh"),
    ("IPH-13", "Apple iPhone 13 128 Go", "TEL", "Smartphones", "Apple", 330000, 395000, 2,
     "Écran : 6,1 pouces\nPuce : A15 Bionic\nFace ID"),
    ("NOK-105", "Nokia 105 (téléphone basique)", "TEL", "Téléphones basiques", "Nokia", 9000, 13500, 20,
     "Double SIM\nRadio FM\nAutonomie : 12 jours"),
    ("ACC-CHG25", "Chargeur rapide 25 W USB-C", "ACC", "Chargeurs & câbles", "Samsung", 6000, 10000, 30, ""),
    ("ACC-CAB1M", "Câble USB-C 1 m", "ACC", "Chargeurs & câbles", None, 1000, 2500, 50, ""),
    ("ACC-ECO", "Écouteurs Bluetooth", "ACC", "Audio", "Oraimo", 8000, 15000, 15, "Autonomie : 30 h\nBluetooth 5.3"),
    ("ACC-COQ-A15", "Coque silicone Galaxy A15", "ACC", "Coques & protections", None, 800, 2500, 25, ""),
    ("ACC-VERRE", "Verre trempé universel", "ACC", "Coques & protections", None, 300, 1500, 60, ""),
    ("PIE-ECR-A15", "Écran de remplacement Galaxy A15", "PIE", "Pièces détachées", "Samsung", 18000, 30000, 3, ""),
    ("PIE-BAT-TEC", "Batterie Tecno (BL-49)", "PIE", "Pièces détachées", "Tecno", 4000, 8000, 6, ""),
    ("SER-MO", "Main d'œuvre réparation", "SER", "Services", None, 0, 5000, 0, ""),
]


class Command(BaseCommand):
    help = "Crée des données de démonstration (sans doublons)."

    @transaction.atomic
    def handle(self, *args, **options):
        # Fiche entreprise d'exemple (modifiable ensuite dans l'administration)
        ent = Entreprise.get()
        if ent.nom == "TelecomPro" and not ent.adresse:
            ent.slogan = "Téléphones, accessoires et réparation"
            ent.adresse = "Avenue Kwame Nkrumah\nOuagadougou, Burkina Faso"
            ent.telephone = "+226 25 00 00 00"
            ent.email = "contact@telecompro.example"
            ent.save()

        assurer_modeles_par_defaut()

        fournisseur, _ = Fournisseur.objects.get_or_create(
            nom="Global Phone Distribution", defaults={"telephone": "+22670000000", "pays": "Burkina Faso"}
        )
        bon = None
        for ordre, (ref, nom, typ, cat, marque, pa, pv, qte, carac) in enumerate(PRODUITS):
            categorie, _ = Categorie.objects.get_or_create(nom=cat, defaults={"ordre": ordre})
            m = Marque.objects.get_or_create(nom=marque)[0] if marque else None
            produit, cree = Produit.objects.get_or_create(
                reference=ref,
                defaults=dict(nom=nom, type_produit=typ, categorie=categorie, marque=m,
                              prix_achat=pa, prix_vente=pv, caracteristiques=carac,
                              garantie_mois=12 if typ == "TEL" else 0,
                              visible_portail=typ in ("TEL", "ACC")),
            )
            # Stock initial passé par un bon d'entrée (pour garder l'historique)
            if cree and qte and produit.est_stockable:
                if bon is None:
                    bon = BonEntree.objects.create(fournisseur=fournisseur, reference_fournisseur="STOCK-INITIAL")
                LigneBonEntree.objects.create(bon=bon, produit=produit, quantite=qte, prix_achat=pa)
        if bon:
            bon.valider()

        client, _ = Client.objects.get_or_create(
            telephone="70112233", defaults={"nom": "Awa Ouédraogo", "email": ""}
        )
        Client.objects.get_or_create(
            telephone="76445566", defaults={"nom": "Société Faso Services", "type_client": "ENTR"}
        )
        if not DossierMaintenance.objects.exists():
            d = DossierMaintenance.objects.create(
                client=client, marque="Tecno", modele="Camon 20", imei="356789012345678",
                accessoires_deposes="Coque", panne_declaree="L'appareil ne charge plus.",
            )
            self.stdout.write(f"Dossier de maintenance d'exemple : {d.numero} (code {d.code_suivi}, tél {client.telephone})")

        self.stdout.write(self.style.SUCCESS("Données de démonstration prêtes."))
