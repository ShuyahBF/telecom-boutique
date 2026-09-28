import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { ToastProvider } from "@/components/Toast";
import RouteProtegee from "@/components/RouteProtegee";
import BoutiqueLayout from "@/components/BoutiqueLayout";
import GestionLayout from "@/components/GestionLayout";
import Connexion from "@/pages/Connexion";
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
// --- Plateforme (super-administrateur) ---
import Plateforme from "@/pages/plateforme/Plateforme";
import CatalogueAdmin from "@/pages/plateforme/CatalogueAdmin";

// Raccourcis de rôles
const VENTES = ["gerant", "vendeur"];
const ATELIER = ["gerant", "vendeur", "technicien"];

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            {/* Portail public : annuaire des boutiques, puis espace de chaque boutique */}
            <Route path="/" element={<Accueil />} />
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

            {/* Documents imprimables : pleine page, sans menu */}
            <Route path="/gestion/documents/:id/imprimer" element={<RouteProtegee roles={VENTES}><DocumentImprimable /></RouteProtegee>} />
            <Route path="/gestion/maintenance/:id/bon-de-depot" element={<RouteProtegee roles={ATELIER}><BonDepot /></RouteProtegee>} />

            {/* Back-office des boutiques */}
            <Route path="/gestion" element={<RouteProtegee><GestionLayout /></RouteProtegee>}>
              <Route index element={<TableauDeBord />} />
              <Route path="documents" element={<RouteProtegee roles={VENTES}><Documents /></RouteProtegee>} />
              <Route path="documents/nouveau" element={<RouteProtegee roles={VENTES}><DocumentEditeur /></RouteProtegee>} />
              <Route path="documents/:id" element={<RouteProtegee roles={VENTES}><DocumentEditeur /></RouteProtegee>} />
              <Route path="commandes" element={<RouteProtegee roles={VENTES}><Commandes /></RouteProtegee>} />
              <Route path="commandes/:id" element={<RouteProtegee roles={VENTES}><CommandeFiche /></RouteProtegee>} />
              <Route path="clients" element={<Clients />} />
              <Route path="clients/:id" element={<ClientFiche />} />
              <Route path="messagerie" element={<RouteProtegee roles={VENTES}><Messagerie /></RouteProtegee>} />
              <Route path="produits" element={<Produits />} />
              <Route path="produits/nouveau" element={<RouteProtegee roles={VENTES}><ProduitForm /></RouteProtegee>} />
              <Route path="produits/:id" element={<ProduitForm />} />
              <Route path="stock" element={<RouteProtegee roles={VENTES}><Stock /></RouteProtegee>} />
              <Route path="stock/bons" element={<RouteProtegee roles={VENTES}><BonsEntree /></RouteProtegee>} />
              <Route path="stock/bons/nouveau" element={<RouteProtegee roles={VENTES}><BonEntreeForm /></RouteProtegee>} />
              <Route path="stock/bons/:id" element={<RouteProtegee roles={VENTES}><BonEntreeForm /></RouteProtegee>} />
              <Route path="fournisseurs" element={<RouteProtegee roles={VENTES}><Fournisseurs /></RouteProtegee>} />
              <Route path="maintenance" element={<Maintenance />} />
              <Route path="maintenance/nouveau" element={<DossierFiche />} />
              <Route path="maintenance/:id" element={<DossierFiche />} />
              <Route path="parametres" element={<RouteProtegee roles={["gerant"]}><Parametres /></RouteProtegee>} />
            </Route>

            {/* Administration de la plateforme */}
            <Route path="/plateforme" element={<RouteProtegee roles={["super_admin"]}><Plateforme /></RouteProtegee>} />
            <Route path="/plateforme/catalogue" element={<RouteProtegee roles={["super_admin"]}><CatalogueAdmin /></RouteProtegee>} />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  );
}
