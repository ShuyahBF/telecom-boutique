import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import Patientez from "@/components/Patientez";
import { ChampCode, IconeWhatsapp, useCompteARebours } from "@/components/CodeWhatsapp";

// ============================================================================
// Lot B — connexion du personnel d'une boutique par TÉLÉPHONE + CODE WHATSAPP
// (onglet « Avec WhatsApp » de la page de connexion). Pas d'ID boutique ni de
// mot de passe : le numéro désigne le compte, le code reçu prouve qu'on l'a en main.
//   Étape 1 : numéro -> POST /auth/whatsapp/demander-code (réponse identique que le
//             compte existe ou non : on ne révèle rien) ;
//   Étape 2 : code à 6 chiffres -> POST /auth/whatsapp/connexion -> session ouverte.
// `onConnecte(user)` : appelé après la connexion (redirection par la page).
// ============================================================================
export default function ConnexionWhatsapp({ onConnecte }) {
  const { ouvrirSession } = useAuth();
  const [etape, setEtape] = useState("numero"); // "numero" puis "code"
  const [telephone, setTelephone] = useState("");
  const [code, setCode] = useState("");
  const [info, setInfo] = useState(null); // réponse de la demande (numéro masqué, validité)
  const [erreur, setErreur] = useState("");
  const [attente, setAttente] = useState(false); // toast « Patientez… » + jauge circulaire
  const [reste, demarrer] = useCompteARebours(); // délai avant de redemander un code

  // Étape 1 (et « Renvoyer le code ») : demande d'un code
  async function demanderCode(e) {
    e?.preventDefault();
    setErreur("");
    setAttente(true);
    try {
      const { data } = await apiClient.post("/auth/whatsapp/demander-code", { telephone: telephone.trim() });
      setInfo(data);
      setEtape("code");
      setCode("");
      demarrer(data.renvoi_dans_secondes);
    } catch (err) {
      setErreur(messageErreur(err, "Envoi du code impossible pour le moment"));
    } finally {
      setAttente(false);
    }
  }

  // Étape 2 : vérification du code et ouverture de la session
  async function seConnecter(e) {
    e.preventDefault();
    setErreur("");
    if (code.length !== 6) return setErreur("Le code contient 6 chiffres.");
    setAttente(true);
    try {
      const { data } = await apiClient.post("/auth/whatsapp/connexion", { telephone: telephone.trim(), code });
      onConnecte(ouvrirSession(data));
    } catch (err) {
      setErreur(messageErreur(err, "Connexion impossible"));
    } finally {
      setAttente(false);
    }
  }

  return (
    <div className="space-y-4">
      <Patientez actif={attente} />
      {etape === "numero" ? (
        <form onSubmit={demanderCode} className="space-y-4">
          <div>
            <label className="label" htmlFor="tel-wa">Numéro WhatsApp</label>
            <input id="tel-wa" className="input" type="tel" inputMode="tel" autoComplete="tel" required
              placeholder="70 12 34 56 ou +226 70 12 34 56" value={telephone} onChange={(e) => setTelephone(e.target.value)} />
            <p className="mt-1 text-xs text-gray-500">Le numéro de votre compte adLyn. Un code à 6 chiffres vous sera envoyé par WhatsApp.</p>
          </div>
          {erreur && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{erreur}</p>}
          <button className="btn-primary flex w-full items-center justify-center gap-2 py-3 text-base" disabled={attente}>
            <IconeWhatsapp /> Recevoir mon code
          </button>
        </form>
      ) : (
        <form onSubmit={seConnecter} className="space-y-4">
          <div className="rounded-xl bg-green-50 p-3 text-sm text-green-900">
            {info?.message} <span className="whitespace-nowrap font-semibold">{info?.telephone_masque}</span>
          </div>
          <div>
            <label className="label" htmlFor="code-wa">Code reçu par WhatsApp</label>
            <ChampCode id="code-wa" value={code} onChange={setCode} />
          </div>
          {erreur && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{erreur}</p>}
          <button className="btn-primary w-full py-3 text-base" disabled={attente || code.length !== 6}>Se connecter</button>
          <div className="flex items-center justify-between text-sm">
            <button type="button" className="text-gray-500 hover:text-primary" onClick={() => { setEtape("numero"); setErreur(""); }}>
              ← Changer de numéro
            </button>
            <button type="button" className="font-semibold text-primary disabled:text-gray-400" disabled={reste > 0 || attente} onClick={demanderCode}>
              {reste > 0 ? `Renvoyer le code (${reste} s)` : "Renvoyer le code"}
            </button>
          </div>
          <p className="text-xs text-gray-500">
            Pas de code ? Si votre compte n'a pas encore de numéro de téléphone, connectez-vous avec votre ID boutique
            et votre mot de passe, puis ajoutez-le dans « Mon compte ».
          </p>
        </form>
      )}
      <p className="text-center text-sm text-gray-600">
        Pas encore de boutique ? <Link to="/creer-ma-boutique" className="font-semibold text-primary">Créer ma boutique</Link>
      </p>
    </div>
  );
}
