import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { ToastProvider } from "@/components/Toast";
import RouteProtegee from "@/components/RouteProtegee";
import BoutiqueLayout from "@/components/BoutiqueLayout";
import GestionLayout from "@/components/GestionLayout";
import Abonnement from "@/pages/gestion/Abonnement";
import Abonnements from "@/pages/plateforme/Abonnements";
import Sms from "@/pages/gestion/Sms";
import Carrousel from "@/pages/gestion/Carrousel";
import Reversements from "@/pages/gestion/Reversements";
import ReversementsPlateforme from "@/pages/plateforme/Reversements";
import ChangerMotDePasse from "@/pages/ChangerMotDePasse";
import Connexion from "@/pages/Connexion";
import MotDePasseOublie from "@/pages/MotDePasseOublie";
import MonCompte from "@/pages/MonCompte";
// --- Portail public ---
import Accueil from "@/pages/public/Accueil";
import Vitrine from "@/pages/public/Vitrine";
import Produit from "@/pages/public/Produit";
import Panier from "@/pages/public/Panier";
import Commander from "@/pages/public/Commander";
import CommandeConfirmee from "@/pages/public/CommandeConfirmee";
import RetourPaiement from "@/pages/public/RetourPaiement";
import SuiviCommande from "@/pages/public/SuiviCommande";
import SuiviReparation from "@/pages/public/SuiviReparation";
import Conseil from "@/pages/public/Conseil";
import Conversation from "@/pages/public/Conversation";
import OuvrirBoutique from "@/pages/public/OuvrirBoutique";
// --- Pages légales publiques ---
import Confidentialite from "@/pages/public/Confidentialite";
import Conditions from "@/pages/public/Conditions";
// --- Back-office : ventes et relation client ---
import TableauDeBord from "@/pages/gestion/TableauDeBord";
import Documents from "@/pages/gestion/Documents";
import DocumentEditeur from "@/pages/gestion/DocumentEditeur";
import DocumentImprimable from "@/pages/gestion/DocumentImprimable";
import Commandes from "@/pages/gestion/Commandes";
import CommandeFiche from "@/pages/gestion/CommandeFiche";
import Clients from "@/pages/gestion/Clients";
import ClientFiche from "@/pages/gestion/ClientFiche";
import Messagerie from "@/pages/gestion/Messagerie";
// --- Back-office : catalogue, stock, atelier, paramètres ---
import Produits from "@/pages/gestion/Produits";
import ProduitForm from "@/pages/gestion/ProduitForm";
import Stock from "@/pages/gestion/Stock";
import BonsEntree from "@/pages/gestion/BonsEntree";
import BonEntreeForm from "@/pages/gestion/BonEntreeForm";
import Fournisseurs from "@/pages/gestion/Fournisseurs";
import Maintenance from "@/pages/gestion/Maintenance";
import DossierFiche from "@/pages/gestion/DossierFiche";
import BonDepot from "@/pages/gestion/BonDepot";
import Parametres from "@/pages/gestion/Parametres";
import CataloguePublic from "@/pages/gestion/CataloguePublic";
import Paiements from "@/pages/gestion/Paiements";
import Parrainage from "@/pages/gestion/Parrainage";
import MaintenanceEquipements from "@/pages/gestion/MaintenanceEquipements";
import FicheMaintenanceImprimable from "@/pages/gestion/FicheMaintenanceImprimable";
import CaisseAizenta from "@/pages/gestion/CaisseAizenta";
// --- Plateforme (super-administrateur) ---
import Plateforme from "@/pages/plateforme/Plateforme";
import CatalogueAdmin from "@/pages/plateforme/CatalogueAdmin";
import Sauvegardes from "@/pages/plateforme/Sauvegardes";
import ParametresPlateforme from "@/pages/plateforme/Parametres";
import Referentiel from "@/pages/plateforme/Referentiel";
import MaintenanceEquipementsPlateforme from "@/pages/plateforme/MaintenanceEquipements";
import PaiementMaintenance from "@/pages/public/PaiementMaintenance";
// Déconnexion programmée de tous les utilisateurs (maintenance de la plateforme)
import SurveillanceMaintenance from "@/components/MaintenancePlateforme";
import DeconnexionInactivite from "@/components/DeconnexionInactivite";

// Une facture imprimable s'ouvre aussi depuis une commande ou un dossier de maintenance
const OPTIONS_FACTURE = ["documents", "commandes", "maintenance", "maintenance_equipements"];

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <BrowserRouter>
          <SurveillanceMaintenance />
          {/* Déconnexion après inactivité (durée réglée par l'administrateur et le DG) */}
          <DeconnexionInactivite />
          <Routes>
            {/* Portail public : annuaire des boutiques, puis espace de chaque boutique */}
            <Route path="/" element={<Accueil />} />
            {/* Pages légales : adresses françaises + alias anglais (revues TikTok, Meta…) */}
            <Route path="/confidentialite" element={<Confidentialite />} />
            <Route path="/privacy" element={<Confidentialite />} />
            <Route path="/privacy-policy" element={<Confidentialite />} />
            <Route path="/conditions" element={<Conditions />} />
            <Route path="/terms" element={<Conditions />} />
            <Route path="/terms-of-service" element={<Conditions />} />
            <Route path="/b/:slug" element={<BoutiqueLayout />}>
              <Route index element={<Vitrine />} />
              <Route path="produit/:produitSlug" element={<Produit />} />
              <Route path="panier" element={<Panier />} />
              <Route path="commander" element={<Commander />} />
              <Route path="merci" element={<CommandeConfirmee />} />
              <Route path="paiement" element={<RetourPaiement />} />
              <Route path="suivi-commande" element={<SuiviCommande />} />
              <Route path="suivi-reparation" element={<SuiviReparation />} />
              <Route path="conseil" element={<Conseil />} />
              <Route path="conseil/:jeton" element={<Conversation />} />
            </Route>

            <Route path="/connexion" element={<Connexion />} />
            <Route path="/mot-de-passe" element={<ChangerMotDePasse />} />
            {/* Mot de passe oublié : code reçu par WhatsApp, SMS ou e-mail */}
            <Route path="/mot-de-passe-oublie" element={<MotDePasseOublie />} />
            {/* Mon compte : e-mail / téléphone de connexion (changement confirmé par code) */}
            <Route path="/mon-compte" element={<MonCompte />} />
            {/* Lien de parrainage partagé par une boutique : demande d'ouverture d'une boutique */}
            <Route path="/ouvrir-ma-boutique" element={<OuvrirBoutique />} />
            {/* Lien de paiement Mobile Money d'une fiche de maintenance des équipements */}
            <Route path="/paiement/maintenance/:jeton" element={<PaiementMaintenance />} />

            {/* Documents imprimables : pleine page, sans menu */}
            <Route path="/gestion/documents/:id/imprimer" element={<RouteProtegee permission="facturation" option={OPTIONS_FACTURE}><DocumentImprimable /></RouteProtegee>} />
            <Route path="/gestion/maintenance/:id/bon-de-depot" element={<RouteProtegee permission="maintenance" option="maintenance"><BonDepot /></RouteProtegee>} />
            <Route path="/gestion/maintenance-equipements/:id/imprimer" element={<RouteProtegee permission="maintenance" option="maintenance_equipements"><FicheMaintenanceImprimable espace="boutique" /></RouteProtegee>} />
            <Route path="/plateforme/maintenance-equipements/:id/imprimer" element={<RouteProtegee roles={["super_admin"]}><FicheMaintenanceImprimable espace="plateforme" /></RouteProtegee>} />

            {/* Back-office des boutiques */}
            <Route path="/gestion" element={<RouteProtegee><GestionLayout /></RouteProtegee>}>
              <Route index element={<TableauDeBord />} />
              {/* Caisse Aizenta : toujours active (données reçues de Loois) */}
              <Route path="caisse-aizenta" element={<RouteProtegee permission="caisse_aizenta"><CaisseAizenta /></RouteProtegee>} />
              <Route path="documents" element={<RouteProtegee permission="facturation" option="documents"><Documents /></RouteProtegee>} />
              <Route path="documents/nouveau" element={<RouteProtegee permission="facturation" option="documents"><DocumentEditeur /></RouteProtegee>} />
              <Route path="documents/:id" element={<RouteProtegee permission="facturation" option="documents"><DocumentEditeur /></RouteProtegee>} />
              <Route path="commandes" element={<RouteProtegee permission="commandes" option="commandes"><Commandes /></RouteProtegee>} />
              <Route path="commandes/:id" element={<RouteProtegee permission="commandes" option="commandes"><CommandeFiche /></RouteProtegee>} />
              <Route path="clients" element={<RouteProtegee option="clients"><Clients /></RouteProtegee>} />
              <Route path="clients/:id" element={<RouteProtegee option="clients"><ClientFiche /></RouteProtegee>} />
              <Route path="messagerie" element={<RouteProtegee permission="messagerie" option="messagerie"><Messagerie /></RouteProtegee>} />
              <Route path="produits" element={<RouteProtegee option="produits"><Produits /></RouteProtegee>} />
              <Route path="catalogue-public" element={<RouteProtegee option="catalogue_public"><CataloguePublic /></RouteProtegee>} />
              <Route path="paiements" element={<RouteProtegee permission="paiements.historique" option="paiements"><Paiements /></RouteProtegee>} />
              <Route path="produits/nouveau" element={<RouteProtegee permission="catalogue.edition" option="produits"><ProduitForm /></RouteProtegee>} />
              <Route path="produits/:id" element={<RouteProtegee option="produits"><ProduitForm /></RouteProtegee>} />
              <Route path="stock" element={<RouteProtegee permission="stock" option="stock"><Stock /></RouteProtegee>} />
              <Route path="stock/bons" element={<RouteProtegee permission="stock" option="stock"><BonsEntree /></RouteProtegee>} />
              <Route path="stock/bons/nouveau" element={<RouteProtegee permission="stock" option="stock"><BonEntreeForm /></RouteProtegee>} />
              <Route path="stock/bons/:id" element={<RouteProtegee permission="stock" option="stock"><BonEntreeForm /></RouteProtegee>} />
              <Route path="fournisseurs" element={<RouteProtegee permission="fournisseurs" option="fournisseurs"><Fournisseurs /></RouteProtegee>} />
              <Route path="maintenance" element={<RouteProtegee permission="maintenance" option="maintenance"><Maintenance /></RouteProtegee>} />
              <Route path="maintenance/nouveau" element={<RouteProtegee permission="maintenance" option="maintenance"><DossierFiche /></RouteProtegee>} />
              <Route path="maintenance/:id" element={<RouteProtegee permission="maintenance" option="maintenance"><DossierFiche /></RouteProtegee>} />
              {/* Maintenance des équipements confiés (fonction activée par l'administrateur) */}
              <Route path="maintenance-equipements" element={<RouteProtegee permission="maintenance" option="maintenance_equipements"><MaintenanceEquipements espace="boutique" /></RouteProtegee>} />
              <Route path="parametres" element={<RouteProtegee permission="parametres" option="parametres"><Parametres /></RouteProtegee>} />
              <Route path="reversements" element={<RouteProtegee permission="paiements.historique" option="reversements"><Reversements /></RouteProtegee>} />
              <Route path="sms" element={<RouteProtegee permission="messagerie" option="sms"><Sms /></RouteProtegee>} />
              {/* Envoi de produits en carrousel photo par WhatsApp */}
              <Route path="carrousel" element={<RouteProtegee permission="messagerie" option="carrousel"><Carrousel /></RouteProtegee>} />
              {/* Abonnement : jamais bloqué par les options (la boutique doit toujours pouvoir payer) */}
              <Route path="abonnement" element={<RouteProtegee permission="parametres"><Abonnement /></RouteProtegee>} />
              <Route path="parrainage" element={<RouteProtegee permission="parametres" option="parrainage"><Parrainage /></RouteProtegee>} />
            </Route>

            {/* Administration de la plateforme */}
            <Route path="/plateforme" element={<RouteProtegee roles={["super_admin"]}><Plateforme /></RouteProtegee>} />
            <Route path="/plateforme/catalogue" element={<RouteProtegee roles={["super_admin"]}><CatalogueAdmin /></RouteProtegee>} />
            <Route path="/plateforme/referentiel" element={<RouteProtegee roles={["super_admin"]}><Referentiel /></RouteProtegee>} />
            <Route path="/plateforme/abonnements" element={<RouteProtegee roles={["super_admin"]}><Abonnements /></RouteProtegee>} />
            <Route path="/plateforme/reversements" element={<RouteProtegee roles={["super_admin"]}><ReversementsPlateforme /></RouteProtegee>} />
            <Route path="/plateforme/sauvegardes" element={<RouteProtegee roles={["super_admin"]}><Sauvegardes /></RouteProtegee>} />
            {/* Maintenance des équipements confiés par les boutiques */}
            <Route path="/plateforme/maintenance-equipements" element={<RouteProtegee roles={["super_admin"]}><MaintenanceEquipementsPlateforme /></RouteProtegee>} />
            {/* Paramètres généraux : serveur d'envoi des e-mails (SMTP) */}
            <Route path="/plateforme/parametres" element={<RouteProtegee roles={["super_admin"]}><ParametresPlateforme /></RouteProtegee>} />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  );
}
