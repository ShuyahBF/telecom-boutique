import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { messageErreur } from "@/lib/api";

// Connexion du personnel des boutiques (et de l'administrateur de la plateforme).
export default function Connexion() {
  const { connexion } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(false);

  async function valider(e) {
    e.preventDefault();
    setErreur("");
    setEnvoi(true);
    try {
      const user = await connexion(email, motDePasse);
      // Retour à la page demandée avant la connexion, sinon à l'accueil du rôle
      navigate(location.state?.depuis || (user.role === "super_admin" ? "/plateforme" : "/gestion"), { replace: true });
    } catch (err) {
      setErreur(messageErreur(err, "Connexion impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary to-primary-dark p-4">
      <form onSubmit={valider} className="w-full max-w-sm space-y-4 rounded-3xl bg-white p-8 shadow-xl">
        <div className="text-center">
          <p className="text-4xl">📱</p>
          <h1 className="mt-2 text-2xl font-extrabold">Espace boutique</h1>
          <p className="text-sm text-gray-500">Connectez-vous pour gérer votre boutique</p>
        </div>
        <div><label className="label" htmlFor="email">E-mail</label>
          <input id="email" className="input" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><label className="label" htmlFor="mdp">Mot de passe</label>
          <input id="mdp" className="input" type="password" autoComplete="current-password" required value={motDePasse} onChange={(e) => setMotDePasse(e.target.value)} /></div>
        {erreur && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{erreur}</p>}
        <button className="btn-primary w-full" disabled={envoi}>{envoi ? "Connexion…" : "Se connecter"}</button>
        <p className="text-center text-sm"><Link to="/" className="text-primary">← Retour aux boutiques</Link></p>
      </form>
    </div>
  );
}
