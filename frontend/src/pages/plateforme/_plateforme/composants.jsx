// Petits composants partagés par les écrans de la plateforme :
// en-tête commun, champ de formulaire, choix du pays, champs d'identification.
import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { lienCarte, PAYS_AFRIQUE_CENTRALE, PAYS_AFRIQUE_OUEST, PAYS_LISTE, STATUTS_KYC } from "./outils";
import { LogoAdlyn } from "@/components/Marque";
import VersionApp from "@/components/VersionApp";

// ---------------------------------------------------------------------------
// En-tête (bandeau sombre) commun aux pages de la plateforme, avec le menu :
// Boutiques / Référentiel mondial / Catalogue public / Abonnements / Reversements /
// Maintenance des équipements / KYC des DG / Cycle de vie / Usage / Sauvegardes / Paramètres.
// ---------------------------------------------------------------------------
const MENU_PLATEFORME = [
  { to: "/plateforme", label: "Boutiques", court: "Boutiques", icone: "🏪", end: true },
  { to: "/plateforme/referentiel", label: "Référentiel mondial", court: "Appareils", icone: "📚" },
  { to: "/plateforme/catalogue", label: "Catalogue public", court: "Catalogue", icone: "🌍" },
  { to: "/plateforme/abonnements", label: "Abonnements", court: "Abonnements", icone: "💰" },
  { to: "/plateforme/reversements", label: "Reversements", court: "Reversements", icone: "💸" },
  { to: "/plateforme/maintenance-equipements", label: "Maintenance", court: "Maintenance", icone: "🛠️" },
  { to: "/plateforme/kyc-dg", label: "KYC des DG", court: "KYC", icone: "🪪" },
  { to: "/plateforme/cycle-vie", label: "Cycle de vie", court: "Cycle", icone: "♻️" },
  // Lot 25 : historique des connexions, présence en ligne, blocage d'IP / de comptes
  { to: "/plateforme/usage", label: "Usage", court: "Usage", icone: "📈" },
  { to: "/plateforme/sauvegardes", label: "Sauvegardes", court: "Sauvegardes", icone: "💾" },
  { to: "/plateforme/parametres", label: "Paramètres", court: "Paramètres", icone: "⚙️" },
];

export function EnTetePlateforme() {
  const { user, deconnexion } = useAuth();
  const navigate = useNavigate();
  return (
    // Refonte « Ondes & comptoir » : bandeau bleu nuit au motif « ondes »
    // (origine à droite), onglet actif souligné d'une barre bleu ciel.
    <header className="fond-ondes sticky top-0 z-30 border-b border-white/10 text-white [--ondes-x:100%] [--ondes-y:0%]">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
        {/* Logo (+ version et lot déployés juste dessous) et nom de l'administrateur connecté */}
        <div className="shrink-0">
          <Link to="/plateforme" aria-label="adLyn, administration"><LogoAdlyn clair className="h-8" /></Link>
          <VersionApp className="mt-0.5 text-gray-400" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="hidden border-l border-white/15 pl-3 2xl:block">
          <p className="font-display text-sm font-bold text-primary-clair">Plateforme</p>
          <p className="truncate text-xs text-gray-300">Administration de la plateforme · {user?.nom}</p>
          </div>
        </div>

        {/* Menu : sur téléphone il passe sur une seconde ligne (order-last) qui
            défile horizontalement ; libellés courts sur les écrans moyens */}
        <nav className="order-last -mx-1 flex w-full gap-1 overflow-x-auto px-1 sm:order-none sm:w-auto">
          {MENU_PLATEFORME.map((m) => (
            <NavLink key={m.to} to={m.to} end={m.end}
              className={({ isActive }) => `whitespace-nowrap rounded-lg px-2 py-1.5 text-center text-xs font-semibold sm:px-3 sm:text-sm ${isActive ? "bg-white/[0.12] text-white shadow-[inset_0_-2px_0_#5cb0ff]" : "text-gray-300 hover:bg-white/[0.06] hover:text-white"}`}>
              <span className="mr-1">{m.icone}</span>
              <span className="2xl:hidden">{m.court}</span><span className="hidden 2xl:inline">{m.label}</span>
            </NavLink>
          ))}
        </nav>

        <a href="/" target="_blank" rel="noreferrer" className="hidden text-sm font-semibold text-gray-300 hover:text-white 2xl:inline">Portail public ↗</a>
        {/* Changer son propre mot de passe */}
        <Link to="/mot-de-passe" className="text-gray-300 hover:text-white" title="Changer mon mot de passe">🔑</Link>
        <button type="button" className="btn btn-sm border border-white/30 text-white hover:bg-white/10"
          onClick={async () => { await deconnexion(); navigate("/connexion"); }}>
          Déconnexion
        </button>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Champ de formulaire : libellé + contrôle + petite aide facultative
// ---------------------------------------------------------------------------
export function Champ({ label, aide, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="label">{label}</span>
      {children}
      {aide && <span className="mt-1 block text-xs text-gray-500">{aide}</span>}
    </label>
  );
}

// Titre d'une section de formulaire (trait de séparation au-dessus)
export function TitreSection({ children, premier = false }) {
  return (
    <p className={`font-bold text-gray-800 sm:col-span-2 ${premier ? "" : "mt-2 border-t border-gray-200 pt-4"}`}>{children}</p>
  );
}

// Badge du statut KYC (Non fourni / En attente / Vérifié / Rejeté)
export function BadgeKyc({ statut, prefixe = "KYC : " }) {
  const s = STATUTS_KYC[statut] || STATUTS_KYC.NON_FOURNI;
  return <span className={`badge ${s.classe}`}>{prefixe}{s.libelle}</span>;
}

// ---------------------------------------------------------------------------
// Choix du pays : liste Afrique de l'Ouest / Afrique centrale, puis « Autre »
// qui fait apparaître une zone de saisie libre.
// ---------------------------------------------------------------------------
const AUTRE = "__autre__";

export function ChoixPays({ valeur, onChange }) {
  // Mode « Autre » : pays hors liste (déjà saisi, ou choisi par l'utilisateur)
  const [autre, setAutre] = useState(!!valeur && !PAYS_LISTE.includes(valeur));
  return (
    <div className="space-y-2">
      <select className="input bg-white" value={autre ? AUTRE : valeur}
        onChange={(e) => {
          if (e.target.value === AUTRE) { setAutre(true); onChange(""); }
          else { setAutre(false); onChange(e.target.value); }
        }}>
        <optgroup label="Afrique de l'Ouest">
          {PAYS_AFRIQUE_OUEST.map((p) => <option key={p} value={p}>{p}</option>)}
        </optgroup>
        <optgroup label="Afrique centrale">
          {PAYS_AFRIQUE_CENTRALE.map((p) => <option key={p} value={p}>{p}</option>)}
        </optgroup>
        <option value={AUTRE}>Autre…</option>
      </select>
      {autre && (
        <input className="input" placeholder="Nom du pays" maxLength={60} required value={valeur}
          onChange={(e) => onChange(e.target.value)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Champs d'identification & localisation d'une boutique (création et dossier) :
// pays, ville, adresse, coordonnées GPS, IFU, CNSS, RCCM.
// `valeurs` = objet du formulaire ; `maj(champ, valeur)` modifie un champ.
// ---------------------------------------------------------------------------
export function ChampsIdentification({ valeurs, maj }) {
  const carte = lienCarte(valeurs.latitude, valeurs.longitude);
  return (
    <>
      <Champ label="Pays"><ChoixPays valeur={valeurs.pays} onChange={(v) => maj("pays", v)} /></Champ>
      <Champ label="Ville"><input className="input" maxLength={80} value={valeurs.ville} onChange={(e) => maj("ville", e.target.value)} placeholder="Ouagadougou" /></Champ>
      <Champ label="Adresse" className="sm:col-span-2" aide="Quartier, rue, repère… (comme on l'expliquerait à un livreur)">
        <textarea className="input" rows={2} maxLength={500} value={valeurs.adresse} onChange={(e) => maj("adresse", e.target.value)} />
      </Champ>

      {/* Coordonnées GPS + lien de contrôle sur la carte */}
      <Champ label="Latitude" aide="Ex. 12.3714 (nombre entre -90 et 90)">
        <input className="input" inputMode="decimal" value={valeurs.latitude} onChange={(e) => maj("latitude", e.target.value)} placeholder="12.3714" />
      </Champ>
      <Champ label="Longitude" aide="Ex. -1.5197 (nombre entre -180 et 180)">
        <input className="input" inputMode="decimal" value={valeurs.longitude} onChange={(e) => maj("longitude", e.target.value)} placeholder="-1.5197" />
      </Champ>
      <p className="-mt-1 text-sm sm:col-span-2">
        {carte
          ? <a href={carte} target="_blank" rel="noreferrer" className="font-semibold text-primary underline">🗺️ Voir sur la carte ↗</a>
          : <span className="text-gray-500">Astuce : dans OpenStreetMap ou Google Maps, un clic droit sur la boutique affiche ses coordonnées.</span>}
      </p>

      {/* Numéros officiels de l'entreprise */}
      <Champ label="IFU" aide="Identifiant financier unique"><input className="input font-mono" maxLength={50} value={valeurs.ifu} onChange={(e) => maj("ifu", e.target.value)} /></Champ>
      <Champ label="CNSS" aide="N° d'employeur à la sécurité sociale"><input className="input font-mono" maxLength={50} value={valeurs.cnss} onChange={(e) => maj("cnss", e.target.value)} /></Champ>
      <Champ label="RCCM" aide="Registre du commerce" className="sm:col-span-2"><input className="input font-mono" maxLength={60} value={valeurs.rccm} onChange={(e) => maj("rccm", e.target.value)} placeholder="BF-OUA-2026-B-12345" /></Champ>
    </>
  );
}

/**
 * Valeurs du formulaire -> champs d'identification envoyés au serveur
 * (textes nettoyés, coordonnées converties en nombres ou null).
 */
export function identificationVersApi(v) {
  const nombre = (t) => {
    const texte = String(t ?? "").trim().replace(",", ".");
    return texte === "" ? null : Number(texte);
  };
  return {
    pays: (v.pays || "").trim(), ville: (v.ville || "").trim(), adresse: (v.adresse || "").trim(),
    latitude: nombre(v.latitude), longitude: nombre(v.longitude),
    dg_nom: (v.dg_nom || "").trim(), dg_telephone: (v.dg_telephone || "").trim(), ifu: (v.ifu || "").trim(), cnss: (v.cnss || "").trim(), rccm: (v.rccm || "").trim(),
  };
}

/** Vérifie les coordonnées avant l'envoi ; renvoie un message d'erreur ou "" */
export function erreurCoordonnees(v) {
  const api = identificationVersApi(v);
  if ((api.latitude === null) !== (api.longitude === null)) return "Indiquez la latitude ET la longitude (ou aucune des deux).";
  if (api.latitude !== null && (Number.isNaN(api.latitude) || Math.abs(api.latitude) > 90)) return "Latitude invalide : nombre entre -90 et 90.";
  if (api.longitude !== null && (Number.isNaN(api.longitude) || Math.abs(api.longitude) > 180)) return "Longitude invalide : nombre entre -180 et 180.";
  return "";
}
