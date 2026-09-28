"""
Tests automatiques des règles métier principales.
Lancement : python manage.py test
(Django crée une base de test vide et temporaire : vos données ne sont jamais touchées.)
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalogue.models import Categorie, Produit
from core.utils import montant_en_lettres, nombre_en_lettres
from maintenance.models import DossierMaintenance, PieceUtilisee
from messagerie.models import Conversation, JournalEnvoi
from stock.models import BonEntree, LigneBonEntree, MouvementStock
from tiers.models import Client, Fournisseur
from ventes.models import Commande, Document, LigneDocument


class BaseTest(TestCase):
    """Jeu de données minimal commun à tous les tests."""

    def setUp(self):
        self.cat = Categorie.objects.create(nom="Smartphones")
        self.tel = Produit.objects.create(reference="T1", nom="Téléphone test", categorie=self.cat, prix_vente=100000)
        self.service = Produit.objects.create(reference="S1", nom="Main d'œuvre", categorie=self.cat,
                                              prix_vente=5000, type_produit="SER")
        self.client_ = Client.objects.create(nom="Client Test", telephone="70 11 22 33", email="c@test.bf")
        MouvementStock.objects.create(produit=self.tel, type_mouvement="E", quantite=5)
        self.tel.refresh_from_db()


class NumerotationTests(BaseTest):
    def test_numeros_sequentiels_par_prefixe(self):
        annee = timezone.localdate().year
        p1 = Document.objects.create(type_document="PRO", client=self.client_)
        p2 = Document.objects.create(type_document="PRO", client=self.client_)
        self.assertEqual(p1.numero, f"PRO-{annee}-00001")
        self.assertEqual(p2.numero, f"PRO-{annee}-00002")

    def test_facture_sans_numero_avant_validation(self):
        f = Document.objects.create(type_document="FAC", client=self.client_)
        self.assertIsNone(f.numero)

    def test_telephone_normalise(self):
        self.assertEqual(self.client_.telephone, "70112233")


class StockTests(BaseTest):
    def test_mouvements_mettent_a_jour_le_stock(self):
        self.assertEqual(self.tel.stock, 5)
        m = MouvementStock.objects.create(produit=self.tel, type_mouvement="S", quantite=2)
        self.tel.refresh_from_db()
        self.assertEqual(self.tel.stock, 3)
        m.delete()  # supprimer le mouvement annule son effet
        self.tel.refresh_from_db()
        self.assertEqual(self.tel.stock, 5)

    def test_sortie_superieure_au_stock_refusee(self):
        m = MouvementStock(produit=self.tel, type_mouvement="S", quantite=99)
        with self.assertRaises(ValidationError):
            m.full_clean()

    def test_bon_entree_valide_une_seule_fois(self):
        f = Fournisseur.objects.create(nom="Fourn")
        bon = BonEntree.objects.create(fournisseur=f)
        LigneBonEntree.objects.create(bon=bon, produit=self.tel, quantite=10, prix_achat=80000)
        bon.valider()
        self.tel.refresh_from_db()
        self.assertEqual(self.tel.stock, 15)
        self.assertEqual(self.tel.prix_achat, 80000)
        with self.assertRaises(ValidationError):
            bon.valider()


class FactureTests(BaseTest):
    def _facture(self, qte=2):
        f = Document.objects.create(type_document="FAC", client=self.client_)
        LigneDocument.objects.create(document=f, produit=self.tel, quantite=qte, remise_pct=10, taux_tva=18)
        LigneDocument.objects.create(document=f, designation="Configuration", quantite=1, prix_unitaire=2000, taux_tva=0)
        return f

    def test_totaux_multi_lignes(self):
        f = self._facture()
        # 2 x 100 000 - 10 % = 180 000 HT ; TVA 18 % = 32 400 ; + ligne libre 2 000
        self.assertEqual(f.total_ht, Decimal("182000"))
        self.assertEqual(f.total_tva, Decimal("32400"))
        self.assertEqual(f.total_ttc, Decimal("214400"))

    def test_validation_destocke_et_numerote(self):
        f = self._facture()
        f.valider()
        self.tel.refresh_from_db()
        self.assertEqual(self.tel.stock, 3)
        self.assertTrue(f.numero.startswith("FAC-"))
        self.assertFalse(f.modifiable)

    def test_validation_refusee_si_stock_insuffisant(self):
        f = self._facture(qte=50)
        with self.assertRaises(ValidationError):
            f.valider()
        f.refresh_from_db()
        self.assertEqual(f.statut, "BROUILLON")
        self.assertIsNone(f.numero)  # aucun numéro consommé

    def test_annulation_reintegre_le_stock(self):
        f = self._facture()
        f.valider()
        f.annuler()
        self.tel.refresh_from_db()
        self.assertEqual(self.tel.stock, 5)

    def test_conversion_proforma_en_facture(self):
        pro = Document.objects.create(type_document="PRO", client=self.client_)
        LigneDocument.objects.create(document=pro, produit=self.tel, quantite=1)
        LigneDocument.objects.create(document=pro, produit=self.service, quantite=1)
        fac = pro.convertir_en_facture()
        self.assertEqual(fac.lignes.count(), 2)
        self.assertEqual(fac.total_ttc, pro.total_ttc)
        self.assertEqual(fac.proforma_origine, pro)
        self.assertEqual(pro.lignes.count(), 2)  # la proforma garde ses lignes

    def test_paiement_partiel(self):
        f = self._facture(qte=1)
        f.reglements.create(montant=50000)
        self.assertEqual(f.statut_paiement, "Partiellement payée")


class MontantEnLettresTests(TestCase):
    def test_cas_classiques(self):
        self.assertEqual(nombre_en_lettres(71), "soixante et onze")
        self.assertEqual(nombre_en_lettres(80), "quatre-vingts")
        self.assertEqual(nombre_en_lettres(200), "deux cents")
        self.assertEqual(nombre_en_lettres(200000), "deux cent mille")
        self.assertEqual(nombre_en_lettres(80000), "quatre-vingt mille")
        self.assertEqual(nombre_en_lettres(1250500), "un million deux cent cinquante mille cinq cents")
        self.assertEqual(montant_en_lettres(214400), "Deux cent quatorze mille quatre cents FCFA")


class MaintenanceTests(BaseTest):
    def test_dossier_numero_historique_et_notification(self):
        d = DossierMaintenance.objects.create(client=self.client_, marque="Tecno", modele="X", panne_declaree="Écran")
        self.assertTrue(d.numero.startswith("MNT-"))
        self.assertEqual(len(d.code_suivi), 6)
        d.statut = "REPARATION"
        d.save()
        self.assertEqual(d.historique.count(), 2)
        # Dépôt + changement de statut => 2 notifications journalisées (e-mail désactivé par défaut)
        self.assertEqual(JournalEnvoi.objects.filter(destinataire="c@test.bf").count(), 2)

    def test_piece_utilisee_destocke(self):
        piece = Produit.objects.create(reference="P1", nom="Écran", categorie=self.cat, prix_vente=20000, type_produit="PIE")
        MouvementStock.objects.create(produit=piece, type_mouvement="E", quantite=3)
        d = DossierMaintenance.objects.create(client=self.client_, marque="A", modele="B", panne_declaree="x")
        pu = PieceUtilisee.objects.create(dossier=d, produit=piece, quantite=1)
        piece.refresh_from_db()
        self.assertEqual(piece.stock, 2)
        pu.delete()
        piece.refresh_from_db()
        self.assertEqual(piece.stock, 3)


class PortailTests(BaseTest):
    def test_pages_publiques(self):
        for nom in ["accueil", "catalogue", "panier", "suivi_commande", "suivi_maintenance", "conseil"]:
            self.assertEqual(self.client.get(reverse(f"portail:{nom}")).status_code, 200, nom)
        self.assertEqual(self.client.get(self.tel.get_absolute_url()).status_code, 200)

    def test_parcours_commande_et_suivi(self):
        self.client.post(reverse("portail:panier_ajouter", args=[self.tel.pk]), {"quantite": 2})
        r = self.client.post(reverse("portail:commander"), {
            "nom": "Nouveau", "telephone": "+226 71 00 00 01", "email": "", "mode_livraison": "RETRAIT",
        })
        self.assertRedirects(r, reverse("portail:commande_confirmee"))
        cmd = Commande.objects.get()
        self.assertEqual(cmd.total, 200000)
        self.assertEqual(cmd.client.telephone, "+22671000001")
        # Suivi : bon téléphone => trouvé ; mauvais téléphone => rien
        r = self.client.get(reverse("portail:suivi_commande"), {"numero": cmd.numero, "telephone": "+226 71 00 00 01"})
        self.assertContains(r, cmd.numero)
        r = self.client.get(reverse("portail:suivi_commande"), {"numero": cmd.numero, "telephone": "70000000"})
        self.assertContains(r, "Aucune commande")
        # Génération de la facture depuis la commande
        fac = cmd.generer_facture()
        self.assertEqual(fac.total_ht, 200000)

    def test_panier_limite_au_stock(self):
        self.client.post(reverse("portail:panier_ajouter", args=[self.tel.pk]), {"quantite": 99})
        self.assertEqual(self.client.session["panier"][str(self.tel.pk)], 5)

    def test_suivi_maintenance_par_telephone_ou_code(self):
        d = DossierMaintenance.objects.create(client=self.client_, marque="Tecno", modele="Z", panne_declaree="x")
        url = reverse("portail:suivi_maintenance")
        self.assertContains(self.client.get(url, {"numero": d.numero, "telephone": "70 11 22 33"}), "Historique")
        self.assertContains(self.client.get(url, {"numero": d.numero, "code": d.code_suivi}), "Historique")
        self.assertNotContains(self.client.get(url, {"numero": d.numero, "telephone": "123456789"}), "Historique")

    def test_demande_conseil_et_reponse(self):
        r = self.client.post(reverse("portail:conseil"), {
            "nom": "Ali", "telephone": "70998877", "sujet": "Quel téléphone ?", "texte": "Budget 100 000",
        })
        conv = Conversation.objects.get()
        self.assertRedirects(r, conv.get_absolute_url())
        self.client.post(conv.get_absolute_url(), {"texte": "Merci"})
        self.assertEqual(conv.messages.count(), 2)


class BackOfficeTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("admin", "a@a.bf", "motdepasse-test")
        self.client.force_login(self.admin)

    def test_tableau_de_bord_et_impressions(self):
        self.assertEqual(self.client.get(reverse("core:tableau_de_bord")).status_code, 200)
        f = Document.objects.create(type_document="FAC", client=self.client_)
        LigneDocument.objects.create(document=f, produit=self.tel, quantite=1)
        r = self.client.get(reverse("core:imprimer_document", args=[f.pk]))
        self.assertContains(r, "BROUILLON")
        d = DossierMaintenance.objects.create(client=self.client_, marque="A", modele="B", panne_declaree="x")
        self.assertContains(self.client.get(reverse("core:imprimer_depot", args=[d.pk])), d.code_suivi)

    def test_bouton_valider_facture(self):
        f = Document.objects.create(type_document="FAC", client=self.client_)
        LigneDocument.objects.create(document=f, produit=self.tel, quantite=1)
        self.client.post(reverse("admin:ventes_document_valider", args=[f.pk]))
        f.refresh_from_db()
        self.assertEqual(f.statut, "VALIDE")

    def test_ecrans_admin(self):
        for url in ["ventes_document", "ventes_commande", "maintenance_dossiermaintenance", "stock_bonentree",
                    "stock_mouvementstock", "messagerie_conversation", "messagerie_modelemessage", "catalogue_produit"]:
            self.assertEqual(self.client.get(reverse(f"admin:{url}_changelist")).status_code, 200, url)
            self.assertEqual(self.client.get(reverse(f"admin:{url}_add")).status_code, 200, url)

    def test_back_office_interdit_aux_visiteurs(self):
        self.client.logout()
        r = self.client.get(reverse("core:tableau_de_bord"))
        self.assertEqual(r.status_code, 302)
