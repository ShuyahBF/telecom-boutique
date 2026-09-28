import { useEffect, useState } from "react";
import { Link, Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";
import { aLeRole, useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";
import { ROLES } from "@/lib/statuts";

// Menu du back-office : chaque entrée indique les rôles qui peuvent la voir.
const MENU = [
  { to: "/gestion", label: "Tableau de bord", icone: "📊", roles: ["gerant", "vendeur", "technicien"], end: true },
  { to: "/gestion/documents", label: "Factures & proformas", icone: "🧾", roles: ["gerant", "vendeur"] },
  { to: "/gestion/commandes", label: "Commandes en ligne", icone: "📦", roles: ["gerant", "vendeur"] },
  { to: "/gestion/maintenance", label: "Maintenance (SAV)", icone: "🔧", roles: ["gerant", "vendeur", "technicien"] },
  { to: "/gestion/produits", label: "Catalogue", icone: "📱", roles: ["gerant", "vendeur", "technicien"] },
  { to: "/gestion/catalogue-public", label: "Catalogue public", icone: "🌍", roles: ["gerant", "vendeur", "technicien"] },
  { to: "/gestion/stock", label: "Stock", icone: "🏷️", roles: ["gerant", "vendeur"] },
  { to: "/gestion/clients", label: "Clients", icone: "👥", roles: ["gerant", "vendeur", "technicien"] },
  { to: "/gestion/fournisseurs", label: "Fournisseurs", icone: "🚚", roles: ["gerant", "vendeur"] },
  { to: "/gestion/messagerie", label: "Messagerie", icone: "💬", roles: ["gerant", "vendeur"], compteur: true },
  { to: "/gestion/parametres", label: "Paramètres", icone: "⚙️", roles: ["gerant"] },
];

// Mise en page du back-office : barre latérale (menu), barre du haut, contenu.
export default function GestionLayout() {
  const { user, boutique, deconnexion } = useAuth();
  const navigate = useNavigate();
  const [menuMobile, setMenuMobile] = useState(false);
  const [nonLues, setNonLues] = useState(0);

  // Nombre de demandes de conseil en attente (rafraîchi chaque minute)
  useEffect(() => {
    if (!boutique || !aLeRole(user, "gerant", "vendeur")) return undefined;
    const charger = () => apiClient.get("/conversations/non-lues").then(({ data }) => setNonLues(data.non_lues)).catch(() => {});
    charger();
    const t = setInterval(charger, 60000);
    return () => clearInterval(t);
  }, [boutique, user]);

  // Super-admin sans boutique choisie : retour à l'écran de la plateforme
  if (user?.role === "super_admin" && !boutique) return <Navigate to="/plateforme" replace />;
  if (!boutique) return null;

  const entrees = MENU.filter((m) => aLeRole(user, ...m.roles));
  const classeLien = ({ isActive }) =>
    `flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold ${isActive ? "bg-primary text-white" : "text-gray-700 hover:bg-gray-100"}`;

  const menu = (
    <nav className="flex flex-col gap-1">
      {entrees.map((m) => (
        <NavLink key={m.to} to={m.to} end={m.end} className={classeLien} onClick={() => setMenuMobile(false)}>
          <span>{m.icone}</span>
          <span className="flex-1">{m.label}</span>
          {m.compteur && nonLues > 0 && <span className="rounded-full bg-accent px-2 text-xs text-white">{nonLues}</span>}
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
              <button type="button" className="btn-outline btn-sm" onClick={() => { deconnexion(); navigate("/connexion"); }}>Déconnexion</button>
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
