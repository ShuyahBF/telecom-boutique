import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { idBoutiqueMemorise, messageErreur } from "@/lib/api";

// Connexion du personnel : ID BOUTIQUE (6 caractères, reçu à la création de la
// boutique) + e-mail + mot de passe personnel. L'ID boutique est retenu pour
// les fois suivantes ; la session reste ouverte 30 jours (cookie sécurisé).
// L'administrateur de la plateforme se connecte sans ID boutique.
export default function Connexion() {
  const { connexion } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [codeBoutique, setCodeBoutique] = useState(idBoutiqueMemorise);
  const [administrateur, setAdministrateur] = useState(false);
  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(false);

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
      const user = await connexion(administrateur ? "" : codeBoutique, email, motDePasse);
      // Mot de passe provisoire : changement obligatoire avant tout
      if (user.doit_changer_mot_de_passe) {
        navigate("/mot-de-passe", { replace: true, state: { depuis: location.state?.depuis } });
        return;
      }
      // Retour à la page demandée avant la connexion, sinon à l'accueil du rôle
      navigate(location.state?.depuis || (user.role === "super_admin" ? "/plateforme" : "/gestion"), { replace: true });
    } catch (err) {
      setErreur(messageErreur(err, "Connexion impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-nuit-900 p-4">
      {/* Décor : halos de couleur et quadrillage discret (style Sawali) */}
      <div className="pointer-events-none absolute -right-40 -top-40 h-[30rem] w-[30rem] rounded-full bg-primary/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -left-40 h-96 w-96 rounded-full bg-accent/20 blur-3xl" />
      <div className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(#fff_1px,transparent_1px),linear-gradient(90deg,#fff_1px,transparent_1px)] [background-size:48px_48px]" />
      <form onSubmit={valider} className="relative w-full max-w-sm space-y-4 rounded-2xl border border-white/10 bg-white p-8 shadow-2xl">
        <div className="text-center">
          <p className="font-display text-3xl font-bold tracking-tight text-ink">adLyn</p>
          <p className="surtitre mt-1">{administrateur ? "Administration" : "Espace boutique"}</p>
          <h1 className="mt-3 text-xl font-bold">{administrateur ? "Administration de la plateforme" : "Connexion à votre boutique"}</h1>
          <p className="text-sm text-gray-500">Connectez-vous pour gérer votre boutique</p>
        </div>

        {/* ID boutique : raccourci unique de 6 caractères (pas de nom à taper, pas d'erreur de frappe) */}
        {!administrateur && (
          <div>
            <label className="label" htmlFor="code">ID boutique</label>
            <input id="code" className="input text-center font-mono text-lg tracking-[0.4em] uppercase" required
              autoComplete="organization" inputMode="text" placeholder="K7M2QD" maxLength={6}
              value={codeBoutique} onChange={(e) => saisirCode(e.target.value)} />
            <p className="mt-1 text-xs text-gray-500">6 lettres ou chiffres, reçus à la création de votre boutique.</p>
          </div>
        )}
        <div><label className="label" htmlFor="email">E-mail</label>
          <input id="email" className="input" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><label className="label" htmlFor="mdp">Mot de passe</label>
          <input id="mdp" className="input" type="password" autoComplete="current-password" required value={motDePasse} onChange={(e) => setMotDePasse(e.target.value)} /></div>
        {erreur && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{erreur}</p>}
        <button className="btn-primary w-full" disabled={envoi}>{envoi ? "Connexion…" : "Se connecter →"}</button>
        <p className="text-center text-xs text-gray-500">Vous resterez connecté 30 jours sur cet appareil. Votre mot de passe n'y est jamais enregistré.</p>
        <div className="flex justify-between text-sm">
          <Link to="/" className="text-primary">← Retour aux boutiques</Link>
          <button type="button" className="text-gray-500 hover:text-primary" onClick={() => { setAdministrateur(!administrateur); setErreur(""); }}>
            {administrateur ? "Personnel d'une boutique" : "Administrateur ?"}
          </button>
        </div>
      </form>
    </div>
  );
}
