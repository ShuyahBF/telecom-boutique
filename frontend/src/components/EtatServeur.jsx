import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/api";

// -----------------------------------------------------------------------------
// État du serveur affiché sur les cartes de connexion (actif, lent, injoignable)
// -----------------------------------------------------------------------------
// Composant partagé (refonte de l'interface) : auparavant défini uniquement dans
// la page « Mon espace » (EspaceClient), il est désormais aussi affiché sur la
// page de connexion du personnel, comme le demande la règle du propriétaire.
// Fonctionnement inchangé : un appel à /health au chargement ; au-delà de
// 3 secondes sans réponse, on affiche « lent » (serveur en train de se réveiller).
//  - className : classes Tailwind pour adapter la couleur du texte au fond.
export default function EtatServeur({ className = "text-gray-500" }) {
  const [etat, setEtat] = useState("verification");
  useEffect(() => {
    const debut = Date.now();
    let fini = false;
    // Au-delà de 3 secondes sans réponse : « lent » (serveur en train de se réveiller)
    const lent = setTimeout(() => { if (!fini) setEtat("lent"); }, 3000);
    fetch(`${API_BASE_URL}/health`)
      .then((r) => { fini = true; setEtat(r.ok ? (Date.now() - debut > 3000 ? "lent" : "actif") : "injoignable"); })
      .catch(() => { fini = true; setEtat("injoignable"); });
    return () => clearTimeout(lent);
  }, []);
  // Pastille de couleur + texte pour chaque état
  const styles = {
    verification: ["bg-gray-300", "Vérification du serveur…"],
    actif: ["bg-green-500", "Serveur actif"],
    lent: ["bg-amber-500", "Serveur lent (réveil en cours)…"],
    injoignable: ["bg-red-500", "Serveur injoignable"],
  };
  const [couleur, texte] = styles[etat];
  return (
    <p className={`flex items-center justify-center gap-2 text-xs ${className}`} role="status">
      {/* Pastille avec un halo de la même couleur (signal « en ligne ») */}
      <span className={`h-2 w-2 rounded-full ${couleur}`} style={{ boxShadow: "0 0 0 3px rgba(148, 163, 184, 0.18)" }} aria-hidden="true" />{texte}
    </p>
  );
}
