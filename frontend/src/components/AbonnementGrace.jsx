import { useEffect } from "react";
import { Link } from "react-router-dom";

// Période de grâce après une échéance impayée (backend/abonnement_grace.py) :
// bandeau rouge pour tous les membres pendant la grâce, puis écran « Abonnement
// expiré » (voir GestionLayout) dès la coupure, décidée par le serveur.

/** Bandeau rouge : « Abonnement expiré — N jour(s) de grâce restant(s) — Renouveler » */
export function BandeauGrace({ grace, dg }) {
  if (!grace?.en_grace) return null;
  return (
    <div className="no-print flex flex-wrap items-center justify-between gap-2 bg-red-600 px-4 py-2 text-sm text-white">
      <span>⚠️ Abonnement expiré — {grace.jours_grace_restants} jour(s) de grâce restant(s)</span>
      {dg
        ? <Link to="/gestion/abonnement" className="font-semibold text-white underline">Renouveler →</Link>
        : <span className="font-semibold">Prévenez votre DG pour le renouveler</span>}
    </div>
  );
}

/** Relit la session à l'heure exacte de la coupure : l'écran bascule sans attendre une action. */
export function useCoupureProgrammee(grace, rafraichir) {
  useEffect(() => {
    if (!grace?.en_grace || !grace.coupure_le) return undefined;
    const delai = new Date(grace.coupure_le).getTime() - Date.now() + 1000;
    if (delai <= 0 || delai > 2 ** 31 - 1) return undefined;
    const t = setTimeout(rafraichir, delai);
    return () => clearTimeout(t);
  }, [grace?.en_grace, grace?.coupure_le, rafraichir]);
}
