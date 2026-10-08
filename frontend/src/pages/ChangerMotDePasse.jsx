import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { messageErreur } from "@/lib/api";
import Chargement from "@/components/Chargement";
import ChampMotDePasse from "@/components/ChampMotDePasse";
import VersionApp from "@/components/VersionApp";

// Changement de mot de passe : OBLIGATOIRE après un mot de passe provisoire
// (reçu par e-mail/SMS ou donné par le DG), et possible à tout moment.
// Les autres appareils connectés à ce compte sont alors déconnectés.
export default function ChangerMotDePasse() {
  const { user, chargement, changerMotDePasse, deconnexion } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ ancien: "", nouveau: "", confirmation: "" });
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(false);

  if (chargement) return <Chargement plein />;
  if (!user) return <Navigate to="/connexion" replace />;
  const oblige = !!user.doit_changer_mot_de_passe;
  const accueil = user.role === "super_admin" ? "/plateforme" : "/gestion";

  async function valider(e) {
    e.preventDefault();
    setErreur("");
    // Contrôles avant envoi (le serveur vérifie aussi)
    if (form.nouveau.length < 8) return setErreur("Le nouveau mot de passe doit contenir au moins 8 caractères.");
    if (form.nouveau !== form.confirmation) return setErreur("Les deux saisies du nouveau mot de passe sont différentes.");
    setEnvoi(true);
    try {
      await changerMotDePasse(form.ancien, form.nouveau);
      navigate(location.state?.depuis || accueil, { replace: true });
    } catch (err) {
      setErreur(messageErreur(err, "Changement impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  const champ = (cle, libelle, autoComplete) => (
    <div><label className="label" htmlFor={cle}>{libelle}</label>
      <ChampMotDePasse id={cle} required autoComplete={autoComplete}
        value={form[cle]} onChange={(e) => setForm({ ...form, [cle]: e.target.value })} /></div>
  );

  return (
    <div className="fond-ondes flex min-h-screen items-center justify-center p-4">{/* fond « ondes » de la charte */}
      <form onSubmit={valider} className="w-full max-w-sm space-y-4 carte-acces">
        <div className="text-center">
          <p className="text-3xl">🔑</p>
          <h1 className="mt-1 text-xl font-extrabold">{oblige ? "Choisissez votre mot de passe" : "Changer mon mot de passe"}</h1>
          <p className="text-sm text-gray-500">
            {oblige ? "Vous utilisez un mot de passe provisoire : remplacez-le par un mot de passe personnel pour continuer."
              : `${user.nom} · ${user.email || user.telephone || ""}`}
          </p>
        </div>
        {champ("ancien", oblige ? "Mot de passe provisoire reçu" : "Mot de passe actuel", "current-password")}
        {champ("nouveau", "Nouveau mot de passe (8 caractères minimum)", "new-password")}
        {champ("confirmation", "Nouveau mot de passe, encore une fois", "new-password")}
        {erreur && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{erreur}</p>}
        <button className="btn-primary w-full" disabled={envoi}>{envoi ? "Enregistrement…" : "Enregistrer"}</button>
        <div className="text-center text-sm">
          {oblige ? (
            <button type="button" className="text-gray-500" onClick={async () => { await deconnexion(); navigate("/connexion"); }}>Se déconnecter</button>
          ) : (
            <button type="button" className="text-primary" onClick={() => navigate(-1)}>← Retour</button>
          )}
        </div>
        {/* Version et lot déployés */}
        <VersionApp className="text-center text-gray-400" />
      </form>
    </div>
  );
}
