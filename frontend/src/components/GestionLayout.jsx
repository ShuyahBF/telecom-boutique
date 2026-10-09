import { useEffect, useState } from "react";
import { Link, Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";
import { peut, useAuth } from "@/context/AuthContext";
import { apiClient, EN_ARRIERE_PLAN } from "@/lib/api";
import { optionActive } from "@/lib/options";
import { ROLES } from "@/lib/statuts";
import { IconeAdlyn, LogoAdlyn } from "@/components/Marque";
import Abonnement from "@/pages/gestion/Abonnement";
import { BandeauGrace, useCoupureProgrammee } from "@/components/AbonnementGrace";
import DernieresSauvegardes from "@/components/DernieresSauvegardes";
import VersionApp from "@/components/VersionApp";
import SupportSawali from "@/components/SupportSawali"; // SAWALI lot 90 : pictogramme d'assistance

// Menu du back-office : chaque entrée indique
//  - la permission nécessaire pour la voir (table PERMISSIONS de backend/auth.py,
//    reçue à la connexion) ;
//  - l'option de la barre latérale correspondante, activée boutique par boutique
//    par l'administrateur adLyn (backend/options_sidebar.py). « Tableau de bord »
//    et « Caisse Aizenta » sont toujours actives.
// Il faut les DEUX : option activée ET rôle autorisé.
const MENU = [
  { to: "/gestion", label: "Tableau de bord", icone: "📊", permission: "tableau_de_bord", option: "tableau_de_bord", end: true },
  { to: "/gestion/caisse-aizenta", label: "Caisse Aizenta", icone: "🧮", permission: "caisse_aizenta", option: "caisse_aizenta" },
  { to: "/gestion/documents", label: "Factures & proformas", icone: "🧾", permission: "facturation", option: "documents" },
  { to: "/gestion/paiements", label: "Historique des paiements", icone: "💳", permission: "paiements.historique", option: "paiements" },
  { to: "/gestion/reversements", label: "Reversements PawaPay", icone: "💸", permission: "paiements.historique", option: "reversements" },
  { to: "/gestion/commandes", label: "Commandes en ligne", icone: "📦", permission: "commandes", option: "commandes" },
  { to: "/gestion/maintenance", label: "Maintenance (SAV)", icone: "🔧", permission: "maintenance", option: "maintenance" },
  { to: "/gestion/maintenance-equipements", label: "Maintenance équipements", icone: "🛠️", permission: "maintenance", option: "maintenance_equipements" },
  { to: "/gestion/produits", label: "Catalogue", icone: "📱", permission: "catalogue.lecture", option: "produits", compteur: "nouveautes" },
  { to: "/gestion/catalogue-public", label: "Catalogue public", icone: "🌍", permission: "catalogue.lecture", option: "catalogue_public" },
  { to: "/gestion/stock", label: "Stock", icone: "🏷️", permission: "stock", option: "stock" },
  { to: "/gestion/clients", label: "Clients", icone: "👥", permission: "clients", option: "clients" },
  { to: "/gestion/fournisseurs", label: "Fournisseurs", icone: "🚚", permission: "fournisseurs", option: "fournisseurs" },
  { to: "/gestion/messagerie", label: "Messagerie", icone: "💬", permission: "messagerie", option: "messagerie", compteur: "conversations" },
  { to: "/gestion/sms", label: "SMS", icone: "📨", permission: "messagerie", option: "sms" },
  { to: "/gestion/carrousel", label: "Carrousel WhatsApp", icone: "🎠", permission: "messagerie", option: "carrousel" },
  { to: "/gestion/parametres", label: "Paramètres", icone: "⚙️", permission: "parametres", option: "parametres" },
  { to: "/gestion/abonnement", label: "Abonnement adLyn", icone: "💰", permission: "parametres", option: "abonnement" },
  { to: "/gestion/parrainage", label: "Parrainage", icone: "🤝", permission: "parametres", option: "parrainage" },
];

/** Jours entre aujourd'hui et l'échéance de l'abonnement (négatif = dépassée). */
function joursAvantEcheance(abonnement) {
  if (!abonnement?.echeance) return null;
  const jour = new Date(); jour.setHours(0, 0, 0, 0);
  return Math.round((new Date(`${abonnement.echeance}T00:00:00`) - jour) / 86400000);
}

// Bandeau d'abonnement (visible par le DG) : essai en cours, échéance proche ou dépassée
function BandeauAbonnement({ boutique }) {
  const ab = boutique.abonnement;
  const jours = joursAvantEcheance(ab);
  if (jours === null || (!ab.en_essai && jours >= 3)) return null;
  const retard = jours < 0;
  const texte = retard
    ? `Votre abonnement adLyn a expiré depuis ${-jours} jour(s). Réglez-le pour éviter la suspension de votre boutique.`
    : ab.en_essai
      ? `Essai gratuit : ${jours + 1} jour(s) restant(s). Choisissez votre abonnement pour continuer sans interruption.`
      : `Votre abonnement expire ${jours === 0 ? "ce soir" : `dans ${jours + 1} jour(s)`}. Pensez à le renouveler.`;
  return (
    <div className={`no-print flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm ${retard ? "bg-red-600 text-white" : ab.en_essai ? "bg-purple-50 text-purple-900" : "bg-amber-50 text-amber-900"}`}>
      <span>{retard ? "⚠️" : "💡"} {texte}</span>
      <Link to="/gestion/abonnement" className={`font-semibold underline ${retard ? "text-white" : ""}`}>Voir mon abonnement →</Link>
    </div>
  );
}

// SAWALI lot 90 — vrai sur grand écran (barre latérale visible, classe Tailwind « lg » = 1024 px).
// Sert à n'afficher QU'UN SEUL pictogramme d'assistance (barre latérale sur grand
// écran, barre du haut sur téléphone) : une seule lecture périodique du fil.
function useGrandEcran() {
  const requete = "(min-width: 1024px)";
  const [grand, setGrand] = useState(() => typeof window !== "undefined" && window.matchMedia?.(requete).matches);
  useEffect(() => {
    const mq = window.matchMedia?.(requete);
    if (!mq) return undefined;
    const suivre = (e) => setGrand(e.matches);
    mq.addEventListener?.("change", suivre);
    return () => mq.removeEventListener?.("change", suivre);
  }, []);
  return !!grand;
}

// Mise en page du back-office : barre latérale (menu), barre du haut, contenu.
export default function GestionLayout() {
  const { user, boutique, deconnexion, rafraichir } = useAuth();
  const navigate = useNavigate();
  const [menuMobile, setMenuMobile] = useState(false);
  const [compteurs, setCompteurs] = useState({ conversations: 0, nouveautes: 0 });
  const grandEcran = useGrandEcran(); // emplacement du pictogramme d'assistance (SAWALI lot 90)
  // Fin de la période de grâce : la session est relue à l'heure exacte de la coupure
  useCoupureProgrammee(boutique?.abonnement_grace, rafraichir);

  // Pastilles du menu (rafraîchies chaque minute) : demandes de conseil en
  // attente et nouveaux modèles reçus du catalogue public
  useEffect(() => {
    if (!boutique) return undefined;
    const charger = async () => {
      const suivants = { conversations: 0, nouveautes: 0 };
      // Pas d'appel vers une option désactivée (le serveur la refuserait)
      if (peut(user, "messagerie") && optionActive(boutique, "messagerie")) {
        suivants.conversations = (await apiClient.get("/conversations/non-lues", EN_ARRIERE_PLAN).catch(() => ({ data: {} }))).data.non_lues || 0;
      }
      if (optionActive(boutique, "produits")) {
        suivants.nouveautes = (await apiClient.get("/produits", { ...EN_ARRIERE_PLAN, params: { nouveau: true } }).catch(() => ({ data: [] }))).data.length || 0;
      }
      setCompteurs(suivants);
    };
    charger();
    const t = setInterval(charger, 60000);
    return () => clearInterval(t);
  }, [boutique, user]);

  // Super-admin sans boutique choisie : retour à l'écran de la plateforme
  if (user?.role === "super_admin" && !boutique) return <Navigate to="/plateforme" replace />;
  if (!boutique) return null;

  // Boutique suspendue, ou abonnement expiré après la période de grâce : le DG ne
  // voit que sa page Abonnement (pour payer et retrouver l'accès) ; les autres
  // membres voient un simple message, sans aucune donnée de la boutique
  const expire = boutique.actif !== false && !!boutique.abonnement_grace?.coupe;
  if ((boutique.actif === false || expire) && user.role !== "super_admin") {
    return (
      <div className="min-h-screen bg-papier">
        <header className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3">
          <span className="font-extrabold">{boutique.nom}</span>
          <button type="button" className="btn-outline btn-sm ml-auto" onClick={async () => { await deconnexion(); navigate("/connexion"); }}>Déconnexion</button>
        </header>
        <main className="mx-auto max-w-5xl p-4 sm:p-6">
          {user.role === "dg" ? <Abonnement /> : (
            <div className="card mx-auto max-w-lg text-center">
              <p className="text-4xl">🔒</p>
              <h1 className="mt-2 text-xl font-extrabold">{expire ? "Abonnement expiré — renouveler" : "Accès à la boutique suspendu"}</h1>
              <p className="mt-2 text-gray-600">
                {expire
                  ? "L'abonnement adLyn de la boutique a expiré et la période de grâce est terminée. Prévenez votre DG : l'accès reviendra dès le renouvellement."
                  : boutique.suspension?.motif === "IMPAYE"
                  ? "L'abonnement adLyn de la boutique n'a pas été renouvelé. Prévenez votre DG : l'accès reviendra dès le paiement."
                  : "La boutique a été suspendue par l'administrateur de la plateforme. Prévenez votre DG."}
              </p>
            </div>
          )}
          {/* Version et lot, même sur l'écran de suspension */}
          <VersionApp className="mt-6 text-center text-gray-400" />
        </main>
      </div>
    );
  }

  const entrees = MENU.filter((m) => peut(user, m.permission) && optionActive(boutique, m.option));
  // Lien du menu. Refonte « Ondes & comptoir » : l'entrée active n'est plus un
  // bloc bleu plein, mais une ligne éclairée avec une barre « signal » bleu ciel
  // à gauche (pseudo-élément before:) — plus calme, et l'œil la trouve aussitôt.
  const classeLien = ({ isActive }) =>
    `relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition before:absolute before:inset-y-1.5 before:left-0 before:w-[3px] before:rounded-full ${isActive ? "bg-white/[0.08] text-white before:bg-primary-clair" : "text-gray-400 before:bg-transparent hover:bg-white/[0.04] hover:text-white"}`;

  const menu = (
    <nav className="flex flex-col gap-0.5">
      {entrees.map((m) => (
        <NavLink key={m.to} to={m.to} end={m.end} className={classeLien} onClick={() => setMenuMobile(false)}>
          <span>{m.icone}</span>
          <span className="flex-1">{m.label}</span>
          {m.compteur && compteurs[m.compteur] > 0 && (
            <span className="rounded-full bg-accent px-2 text-xs font-semibold text-white" title={m.compteur === "nouveautes" ? "Nouveautés du catalogue public" : "Demandes en attente"}>
              {compteurs[m.compteur]}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen bg-papier">
      {user.role === "super_admin" && (
        <div className="no-print flex items-center justify-between gap-2 bg-ink px-4 py-2 text-sm text-white">
          <span>Vous consultez la boutique <b>{boutique.nom}</b> en tant qu'administrateur de la plateforme.</span>
          <Link to="/plateforme" className="font-semibold underline">Changer de boutique</Link>
        </div>
      )}
      <div className="flex">
        {/* Barre latérale bleu nuit ; le motif « ondes » éclaire discrètement le haut (fond-ondes, origine en haut à droite) */}
        <aside className="fond-ondes no-print sticky top-0 hidden h-screen w-64 shrink-0 flex-col gap-5 overflow-y-auto p-4 lg:flex [--ondes-x:110%] [--ondes-y:-6%]">
          <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.04] p-2.5">
            {boutique.logo_url
              ? <img src={boutique.logo_url} alt="" className="h-9 w-9 rounded-lg object-contain" />
              : <IconeAdlyn clair className="h-9 w-9" />}
            <div className="min-w-0">
              <p className="truncate font-display font-bold text-white">{boutique.nom}</p>
              <p className="font-mono text-[11px] tracking-[0.15em] text-primary-clair">{boutique.code_marchand}</p>
            </div>
          </div>
          {menu}
          {/* Signature de la plateforme en bas du menu, avec la version et le lot déployés */}
          <div className="mt-auto space-y-2 border-t border-white/10 pt-4">
            {/* SAWALI lot 90 — petit pictogramme d'assistance : discussion avec le support SAWALI */}
            {grandEcran && <SupportSawali clair libelle="Assistance" />}
            <LogoAdlyn clair className="h-6 opacity-70" />
            <VersionApp className="px-1 text-gray-400" />
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="no-print sticky top-0 z-30 flex items-center gap-3 border-b border-gray-200/80 bg-papier/85 px-4 py-3 backdrop-blur sm:px-6">
            <button type="button" className="rounded-lg border border-gray-300 bg-white px-2.5 py-1 lg:hidden" onClick={() => setMenuMobile(!menuMobile)} aria-label="Menu">☰</button>
            <span className="truncate font-display font-bold lg:hidden">{boutique.nom}</span>
            <div className="ml-auto flex items-center gap-3 text-sm">
              <a href={`/b/${boutique.slug}`} target="_blank" rel="noreferrer" className="hidden font-semibold text-primary sm:inline">Voir ma vitrine ↗</a>
              <span className="hidden text-gray-600 sm:inline"><b className="font-semibold text-ink">{user.nom}</b> · {ROLES[user.role]}</span>
              {/* SAWALI lot 90 — sur téléphone, le pictogramme d'assistance passe dans la barre du haut */}
              {!grandEcran && <SupportSawali />}
              {/* Mon compte : e-mail / téléphone de connexion et mot de passe */}
              <Link to="/mon-compte" className="text-gray-500 hover:text-primary" title="Mon compte : identifiants et mot de passe">👤</Link>
              <button type="button" className="btn-outline btn-sm" onClick={async () => { await deconnexion(); navigate("/connexion"); }}>Déconnexion</button>
            </div>
          </header>
          {boutique.abonnement_grace?.en_grace
            ? <BandeauGrace grace={boutique.abonnement_grace} dg={user.role === "dg"} />
            : user.role === "dg" && <BandeauAbonnement boutique={boutique} />}
          {menuMobile && <div className="no-print border-b border-white/5 bg-nuit-900 p-3 lg:hidden">{menu}</div>}
          {/* Contenu de la page (largeur maximale, marges plus généreuses sur grand écran) */}
          <main className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">
            <Outlet />
            {/* Dates des dernières sauvegardes, en pied de page discret */}
            <DernieresSauvegardes compact />
            {/* Version et lot en pied de page sur petit écran (barre latérale masquée) */}
            <VersionApp className="no-print mt-4 text-center text-gray-400 lg:hidden" />
          </main>
        </div>
      </div>
    </div>
  );
}
