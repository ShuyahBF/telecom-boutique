import { useEffect, useState } from "react";
import { Link, Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";
import { peut, useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";
import { ROLES } from "@/lib/statuts";

// Menu du back-office : chaque entrée indique la permission nécessaire pour la
// voir (table PERMISSIONS de backend/auth.py, reçue à la connexion).
const MENU = [
  { to: "/gestion", label: "Tableau de bord", icone: "📊", permission: "tableau_de_bord", end: true },
  { to: "/gestion/documents", label: "Factures & proformas", icone: "🧾", permission: "facturation" },
  { to: "/gestion/paiements", label: "Historique des paiements", icone: "💳", permission: "paiements.historique" },
  { to: "/gestion/commandes", label: "Commandes en ligne", icone: "📦", permission: "commandes" },
  { to: "/gestion/maintenance", label: "Maintenance (SAV)", icone: "🔧", permission: "maintenance" },
  { to: "/gestion/produits", label: "Catalogue", icone: "📱", permission: "catalogue.lecture", compteur: "nouveautes" },
  { to: "/gestion/catalogue-public", label: "Catalogue public", icone: "🌍", permission: "catalogue.lecture" },
  { to: "/gestion/stock", label: "Stock", icone: "🏷️", permission: "stock" },
  { to: "/gestion/clients", label: "Clients", icone: "👥", permission: "clients" },
  { to: "/gestion/fournisseurs", label: "Fournisseurs", icone: "🚚", permission: "fournisseurs" },
  { to: "/gestion/messagerie", label: "Messagerie", icone: "💬", permission: "messagerie", compteur: "conversations" },
  { to: "/gestion/parametres", label: "Paramètres", icone: "⚙️", permission: "parametres" },
];

// Mise en page du back-office : barre latérale (menu), barre du haut, contenu.
export default function GestionLayout() {
  const { user, boutique, deconnexion } = useAuth();
  const navigate = useNavigate();
  const [menuMobile, setMenuMobile] = useState(false);
  const [compteurs, setCompteurs] = useState({ conversations: 0, nouveautes: 0 });

  // Pastilles du menu (rafraîchies chaque minute) : demandes de conseil en
  // attente et nouveaux modèles reçus du catalogue public
  useEffect(() => {
    if (!boutique) return undefined;
    const charger = async () => {
      const suivants = { conversations: 0, nouveautes: 0 };
      if (peut(user, "messagerie")) {
        suivants.conversations = (await apiClient.get("/conversations/non-lues").catch(() => ({ data: {} }))).data.non_lues || 0;
      }
      suivants.nouveautes = (await apiClient.get("/produits", { params: { nouveau: true } }).catch(() => ({ data: [] }))).data.length || 0;
      setCompteurs(suivants);
    };
    charger();
    const t = setInterval(charger, 60000);
    return () => clearInterval(t);
  }, [boutique, user]);

  // Super-admin sans boutique choisie : retour à l'écran de la plateforme
  if (user?.role === "super_admin" && !boutique) return <Navigate to="/plateforme" replace />;
  if (!boutique) return null;

  const entrees = MENU.filter((m) => peut(user, m.permission));
  const classeLien = ({ isActive }) =>
    `flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold ${isActive ? "bg-primary text-white" : "text-gray-700 hover:bg-gray-100"}`;

  const menu = (
    <nav className="flex flex-col gap-1">
      {entrees.map((m) => (
        <NavLink key={m.to} to={m.to} end={m.end} className={classeLien} onClick={() => setMenuMobile(false)}>
          <span>{m.icone}</span>
          <span className="flex-1">{m.label}</span>
          {m.compteur && compteurs[m.compteur] > 0 && (
            <span className="rounded-full bg-accent px-2 text-xs text-white" title={m.compteur === "nouveautes" ? "Nouveautés du catalogue public" : "Demandes en attente"}>
              {compteurs[m.compteur]}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      {user.role === "super_admin" && (
        <div className="no-print flex items-center justify-between gap-2 bg-ink px-4 py-2 text-sm text-white">
          <span>Vous consultez la boutique <b>{boutique.nom}</b> en tant qu'administrateur de la plateforme.</span>
          <Link to="/plateforme" className="font-semibold underline">Changer de boutique</Link>
        </div>
      )}
      <div className="flex">
        <aside className="no-print sticky top-0 hidden h-screen w-64 shrink-0 flex-col gap-4 overflow-y-auto border-r border-gray-200 bg-white p-4 lg:flex">
          <div className="flex items-center gap-2 px-2">
            {boutique.logo_url
              ? <img src={boutique.logo_url} alt="" className="h-9 w-9 rounded-lg object-contain" />
              : <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-white">📱</span>}
            <div className="min-w-0">
              <p className="truncate font-extrabold">{boutique.nom}</p>
              <p className="text-xs text-gray-500">Code {boutique.code_marchand}</p>
            </div>
          </div>
          {menu}
        </aside>

        <div className="min-w-0 flex-1">
          <header className="no-print sticky top-0 z-30 flex items-center gap-3 border-b border-gray-200 bg-white/90 px-4 py-3 backdrop-blur">
            <button type="button" className="rounded-lg border px-2 py-1 lg:hidden" onClick={() => setMenuMobile(!menuMobile)} aria-label="Menu">☰</button>
            <span className="font-bold lg:hidden">{boutique.nom}</span>
            <div className="ml-auto flex items-center gap-3 text-sm">
              <a href={`/b/${boutique.slug}`} target="_blank" rel="noreferrer" className="hidden font-semibold text-primary sm:inline">Voir ma vitrine ↗</a>
              <span className="hidden text-gray-600 sm:inline">{user.nom} · {ROLES[user.role]}</span>
              {/* Changer son propre mot de passe */}
              <Link to="/mot-de-passe" className="text-gray-500 hover:text-primary" title="Changer mon mot de passe">🔑</Link>
              <button type="button" className="btn-outline btn-sm" onClick={async () => { await deconnexion(); navigate("/connexion"); }}>Déconnexion</button>
            </div>
          </header>
          {menuMobile && <div className="no-print border-b border-gray-200 bg-white p-3 lg:hidden">{menu}</div>}
          <main className="mx-auto max-w-7xl p-4 sm:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
