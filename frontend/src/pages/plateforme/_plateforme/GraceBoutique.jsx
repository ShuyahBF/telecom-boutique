import { useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { date } from "@/lib/format";
import { useToast } from "@/components/Toast";

// Période de grâce d'une boutique en retard (backend/abonnement_grace.py) :
// état (grâce en cours / accès coupé), délai propre à la boutique (0 à 30 jours,
// vide = 3 jours) et bouton « Renouveler la grâce (+3 j) », 3 fois au plus par échéance.
export default function GraceBoutique({ boutique, grace, onMaj }) {
  const toast = useToast();
  const [jours, setJours] = useState(grace?.jours_grace ?? 3);
  const [occupe, setOccupe] = useState(false);
  if (!grace) return null;
  const base = `/plateforme/abonnements/boutiques/${boutique.id}/grace`;

  async function appel(fonction, message) {
    setOccupe(true);
    try {
      await fonction();
      toast.succes(message);
      onMaj?.();
    } catch (err) {
      toast.erreur(messageErreur(err, "Action impossible"));
    } finally {
      setOccupe(false);
    }
  }

  const renouveler = () => window.confirm(`Accorder 3 jours de grâce de plus à « ${boutique.nom} » ?`)
    && appel(() => apiClient.post(`${base}/renouveler`), "Grâce renouvelée (+3 jours)");
  const regler = (e) => {
    e.preventDefault();
    const valeur = String(jours).trim() === "" ? null : Number(jours);
    return appel(() => apiClient.put(base, { jours: valeur }), "Délai de grâce enregistré");
  };

  return (
    <div className="flex w-full flex-wrap items-center gap-2 rounded-lg bg-gray-50 px-3 py-2 text-xs">
      {!grace.applicable ? <span className="badge bg-gray-100 text-gray-600">Boutique de test : jamais coupée</span>
        : grace.coupe ? <span className="badge bg-red-100 text-red-700">Accès coupé depuis le {date(grace.coupure_le)}</span>
          : grace.en_grace ? <span className="badge bg-amber-100 text-amber-800">Grâce : {grace.jours_grace_restants} j restant(s), jusqu'au {date(grace.dernier_jour_grace)}</span>
            : null}
      <span className="text-gray-500">Renouvellements : {grace.prolongations}/{grace.prolongations_max}</span>
      <button type="button" className="btn-outline btn-sm" disabled={occupe || !grace.prolongation_possible} onClick={renouveler}>
        Renouveler la grâce (+3 j)
      </button>
      <form onSubmit={regler} className="ml-auto flex items-center gap-1">
        <label htmlFor={`grace-${boutique.id}`} className="text-gray-500">Délai de grâce (jours)</label>
        <input id={`grace-${boutique.id}`} className="input w-16 py-1" type="number" min="0" max="30" value={jours} onChange={(e) => setJours(e.target.value)} />
        <button className="btn-outline btn-sm" disabled={occupe}>OK</button>
      </form>
    </div>
  );
}
