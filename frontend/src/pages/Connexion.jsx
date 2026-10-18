import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { LogoAdlyn } from "@/components/Marque";
import PoweredBySawali from "@/components/PoweredBySawali";
import { LiensLegaux } from "@/components/PageLegale";
import { MOTIF_DECONNEXION_KEY, useAuth } from "@/context/AuthContext";
import { idBoutiqueMemorise, messageErreur } from "@/lib/api";
import ChampMotDePasse from "@/components/ChampMotDePasse";
import { AvisMaintenance } from "@/components/MaintenancePlateforme";
import VersionApp from "@/components/VersionApp";
import EtatServeur from "@/components/EtatServeur";
import ConnexionWhatsapp from "@/components/ConnexionWhatsapp"; // lot B : téléphone + code WhatsApp
import { IconeWhatsapp } from "@/components/CodeWhatsapp";
import Patientez from "@/components/Patientez";
import BoutonInstaller from "@/components/BoutonInstaller"; // application Android installable

// Connexion du personnel : ID BOUTIQUE (6 caractères, reçu à la création de la
// boutique) + e-mail OU numéro de téléphone + mot de passe personnel. L'ID boutique est retenu pour
// les fois suivantes ; la session reste ouverte 30 jours (cookie sécurisé).
// L'administrateur de la plateforme se connecte sans ID boutique.
export default function Connexion() {
  const { connexion } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [codeBoutique, setCodeBoutique] = useState(idBoutiqueMemorise);
  const [administrateur, setAdministrateur] = useState(false);
  const [identifiant, setIdentifiant] = useState(""); // e-mail ou téléphone
  const [motDePasse, setMotDePasse] = useState("");
  // Session fermée par le DG ou l'administrateur : message affiché une seule fois
  const [erreur, setErreur] = useState(() => {
    try {
      const motif = sessionStorage.getItem(MOTIF_DECONNEXION_KEY) || "";
      sessionStorage.removeItem(MOTIF_DECONNEXION_KEY);
      return motif;
    } catch { return ""; }
  });
  const [envoi, setEnvoi] = useState(false);
  // Lot B — mode de connexion du personnel : « mdp » (ID boutique + identifiant + mot de
  // passe, inchangé) ou « whatsapp » (téléphone + code reçu par WhatsApp)
  // (« ?mode=whatsapp » dans l'adresse : ouvre directement l'onglet WhatsApp, ex. depuis l'inscription)
  const [mode, setMode] = useState(() => (new URLSearchParams(location.search).get("mode") === "whatsapp" ? "whatsapp" : "mdp"));

  // Après une connexion réussie (mot de passe ou WhatsApp) : page demandée, sinon accueil du rôle
  function apresConnexion(user) {
    // Mot de passe provisoire : changement obligatoire avant tout
    if (user.doit_changer_mot_de_passe) {
      navigate("/mot-de-passe", { replace: true, state: { depuis: location.state?.depuis } });
      return;
    }
    navigate(location.state?.depuis || (user.role === "super_admin" ? "/plateforme" : "/gestion"), { replace: true });
  }

  // Saisie de l'ID : majuscules, sans espace ni tiret, 6 caractères au plus
  const saisirCode = (valeur) => setCodeBoutique(valeur.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6));

  async function valider(e) {
    e.preventDefault();
    setErreur("");
    if (!administrateur && codeBoutique.length !== 6) {
      setErreur("L'ID boutique contient 6 lettres ou chiffres.");
      return;
    }
    setEnvoi(true);
    try {
      const user = await connexion(administrateur ? "" : codeBoutique, identifiant.trim(), motDePasse);
      apresConnexion(user);
    } catch (err) {
      setErreur(messageErreur(err, "Connexion impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    // Refonte « Ondes & comptoir » : fond bleu nuit à motif d'ondes (anneaux
    // concentriques partant du coin bas gauche, comme l'orbite du logo) et
    // carte blanche centrée avec le logo. Les ondes remplacent les anciens
    // halos et le quadrillage. Aucun changement de fonctionnement.
    <div className="fond-ondes relative flex min-h-screen flex-col items-center justify-center overflow-hidden p-4 pb-28 sm:pb-24">
      <div className="carte-acces max-w-sm space-y-4">
        <div className="text-center">
          <LogoAdlyn className="mx-auto h-11" />
          <h1 className="mt-5 text-2xl font-extrabold">{administrateur ? "Administration de la plateforme" : "Connexion à votre boutique"}</h1>
          <p className="mt-1 text-sm text-gray-500">
            {administrateur ? "Réservé à l'équipe adLyn."
              : mode === "whatsapp" ? "Votre numéro, puis le code reçu par WhatsApp."
              : "Votre ID boutique, puis vos identifiants personnels."}
          </p>
        </div>
        {/* Maintenance de la plateforme : message de l'administrateur */}
        <AvisMaintenance />

        {/* Lot B — deux façons de se connecter (personnel des boutiques) */}
        {!administrateur && (
          <div className="grid grid-cols-2 gap-1 rounded-xl bg-gray-100 p-1 text-sm font-semibold" role="tablist">
            <button type="button" role="tab" aria-selected={mode === "mdp"}
              className={`rounded-lg px-3 py-2 transition ${mode === "mdp" ? "bg-white text-ink shadow-sm" : "text-gray-500 hover:text-ink"}`}
              onClick={() => { setMode("mdp"); setErreur(""); }}>🔑 Mot de passe</button>
            <button type="button" role="tab" aria-selected={mode === "whatsapp"}
              className={`flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 transition ${mode === "whatsapp" ? "bg-white text-ink shadow-sm" : "text-gray-500 hover:text-ink"}`}
              onClick={() => { setMode("whatsapp"); setErreur(""); }}><IconeWhatsapp className="h-4 w-4" /> Avec WhatsApp</button>
          </div>
        )}

        {!administrateur && mode === "whatsapp" ? <ConnexionWhatsapp onConnecte={apresConnexion} /> : (
        <form onSubmit={valider} className="space-y-4">
        {/* Attente de la réponse du serveur : toast « Patientez… » + jauge circulaire */}
        <Patientez actif={envoi} />

        {/* ID boutique : raccourci unique de 6 caractères (pas de nom à taper, pas d'erreur de frappe) */}
        {!administrateur && (
          <div>
            <label className="label" htmlFor="code">ID boutique</label>
            <input id="code" className="input bg-papier text-center font-mono text-xl font-medium tracking-[0.45em] uppercase" required
              autoComplete="organization" inputMode="text" placeholder="K7M2QD" maxLength={6}
              value={codeBoutique} onChange={(e) => saisirCode(e.target.value)} />
            <p className="mt-1 text-xs text-gray-500">6 lettres ou chiffres, reçus à la création de votre boutique.</p>
          </div>
        )}
        {/* Un seul champ : l'e-mail OU le numéro de téléphone (beaucoup n'ont pas d'e-mail) */}
        <div><label className="label" htmlFor="identifiant">{administrateur ? "E-mail" : "E-mail ou téléphone"}</label>
          <input id="identifiant" className="input" type={administrateur ? "email" : "text"} autoComplete="username" required
            placeholder={administrateur ? "" : "vous@exemple.com ou 70 12 34 56"}
            value={identifiant} onChange={(e) => setIdentifiant(e.target.value)} /></div>
        <div>
          <div className="flex items-baseline justify-between">
            <label className="label" htmlFor="mdp">Mot de passe</label>
            {/* Réinitialisation par code reçu sur WhatsApp, SMS ou e-mail */}
            {!administrateur && <Link to="/mot-de-passe-oublie" className="text-xs font-semibold text-primary">Mot de passe oublié ?</Link>}
          </div>
          <ChampMotDePasse id="mdp" autoComplete="current-password" required value={motDePasse} onChange={(e) => setMotDePasse(e.target.value)} /></div>
        {erreur && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{erreur}</p>}
        <button className="btn-primary w-full py-3 text-base" disabled={envoi}>{envoi ? "Connexion…" : "Se connecter"}</button>
        {/* Lot B — inscription libre (numéro WhatsApp + code) */}
        {!administrateur && (
          <p className="text-center text-sm text-gray-600">
            Pas encore de boutique ? <Link to="/creer-ma-boutique" className="font-semibold text-primary">Créer ma boutique</Link>
          </p>
        )}
        </form>
        )}
        <p className="text-center text-xs text-gray-500">Vous resterez connecté 30 jours sur cet appareil. Votre mot de passe n'y est jamais enregistré.</p>
        {/* État du serveur (actif, lent, injoignable) : règle du propriétaire */}
        <EtatServeur />
        {/* Installer adLyn comme application (masqué quand elle est déjà installée) */}
        <BoutonInstaller />
        <div className="flex justify-between border-t border-gray-100 pt-4 text-sm">
          <Link to="/" className="text-primary">← Retour aux boutiques</Link>
          <button type="button" className="text-gray-500 hover:text-primary" onClick={() => { setAdministrateur(!administrateur); setMode("mdp"); setErreur(""); }}>
            {administrateur ? "Personnel d'une boutique" : "Administrateur ?"}
          </button>
        </div>
      </div>
      {/* Liens légaux + mention obligatoire + version/lot déployés, en bas de l'écran */}
      <div className="absolute bottom-4 left-0 right-0 space-y-1 px-4 text-center">
        <LiensLegaux className="justify-center" />
        <PoweredBySawali />
        <VersionApp className="text-gray-400" />
      </div>
    </div>
  );
}
