import { useCallback, useEffect, useState } from "react";
import { MOTIF_DECONNEXION_KEY, useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";
import { CLE_DECONNEXION, useInactivite } from "@/lib/inactivite";

const MESSAGE = "Session expirée après inactivité. Reconnectez-vous.";

// Déconnexion après inactivité, montée une seule fois dans App : active dès
// qu'un membre du personnel (ou le super-admin) est connecté et que la durée
// réglée n'est pas 0. Avertissement avant l'échéance avec « Rester connecté ».
export default function DeconnexionInactivite() {
  const { user, deconnexion } = useAuth();
  const [reglage, setReglage] = useState({ secondes: 0, avertissement_secondes: 0 });

  // Durée qui s'applique à l'utilisateur connecté (relue à chaque connexion)
  const idUtilisateur = user?.id;
  useEffect(() => {
    if (!idUtilisateur) {
      setReglage({ secondes: 0, avertissement_secondes: 0 });
      return undefined;
    }
    let annule = false;
    apiClient.get("/auth/inactivite")
      .then(({ data }) => { if (!annule) setReglage(data); })
      .catch(() => { /* désactivée faute de réglage lisible ; le serveur contrôle de toute façon */ });
    return () => { annule = true; };
  }, [idUtilisateur]);

  const deconnecter = useCallback(async (prevenirAutresOnglets) => {
    try {
      sessionStorage.setItem(MOTIF_DECONNEXION_KEY, MESSAGE);
      if (prevenirAutresOnglets) localStorage.setItem(CLE_DECONNEXION, String(Date.now()));
    } catch { /* stockage indisponible */ }
    await deconnexion();
    // Navigation « dure » : aucune fenêtre ni donnée de la page précédente ne reste affichée
    window.location.assign("/connexion");
  }, [deconnexion]);

  const { restant, resterConnecte } = useInactivite({
    secondes: user ? Number(reglage.secondes) || 0 : 0,
    avertissement: Number(reglage.avertissement_secondes) || 0,
    onDeconnexion: deconnecter,
  });

  if (restant === null) return null;
  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-4" role="alertdialog"
      aria-modal="true" aria-labelledby="inactivite-titre">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <h2 id="inactivite-titre" className="text-lg font-bold">⏳ Session bientôt fermée</h2>
        <p className="mt-2 text-sm text-gray-700">
          Sans activité, vous serez déconnecté(e) dans <b className="tabular-nums text-red-700">{restant}</b> seconde{restant > 1 ? "s" : ""}.
        </p>
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button type="button" className="btn-outline" onClick={() => deconnecter(true)}>Se déconnecter</button>
          <button type="button" className="btn-primary" onClick={resterConnecte}>Rester connecté</button>
        </div>
      </div>
    </div>
  );
}
