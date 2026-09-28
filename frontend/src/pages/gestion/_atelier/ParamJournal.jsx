import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import { Vide } from "./communs";

// Présentation des statuts d'envoi
const STATUTS_ENVOI = {
  ENVOYE: { libelle: "Envoyé", classe: "bg-green-100 text-green-800" },
  ECHEC: { libelle: "Échec", classe: "bg-red-100 text-red-700" },
  NON_ENVOYE: { libelle: "Non envoyé", classe: "bg-gray-100 text-gray-700" },
};

// Onglet « Journal des envois » : les 200 derniers e-mails tentés.
export default function ParamJournal() {
  const toast = useToast();
  const [envois, setEnvois] = useState([]);
  const [chargement, setChargement] = useState(true);

  // Chargement (GET /boutique/messagerie/journal)
  const charger = useCallback(() => {
    setChargement(true);
    apiClient.get("/boutique/messagerie/journal")
      .then(({ data }) => setEnvois(data))
      .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger le journal")))
      .finally(() => setChargement(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-sm text-gray-500">« Non envoyé » : la messagerie était désactivée ou pas encore réglée au moment de l'envoi.</p>
        <button type="button" className="btn-outline btn-sm shrink-0" onClick={charger}>↻ Actualiser</button>
      </div>
      <div className="card overflow-x-auto p-0">
        {chargement ? <Chargement /> : envois.length === 0 ? <Vide icone="✉️">Aucun e-mail envoyé pour l'instant.</Vide> : (
          <table className="table min-w-[720px]">
            <thead><tr><th>Date</th><th>Type</th><th>Destinataire</th><th>Sujet</th><th>Statut</th></tr></thead>
            <tbody>
              {envois.map((j) => {
                const s = STATUTS_ENVOI[j.statut] || { libelle: j.statut, classe: "bg-gray-100 text-gray-700" };
                return (
                  <tr key={j.id}>
                    <td className="whitespace-nowrap">{dateHeure(j.date)}</td>
                    <td className="font-mono text-xs">{j.code || "—"}</td>
                    <td>{j.destinataire}</td>
                    <td className="max-w-xs">{j.sujet}</td>
                    <td>
                      <span className={`badge ${s.classe}`}>{s.libelle}</span>
                      {j.erreur && <p className="mt-1 max-w-xs break-words text-xs text-red-600">{j.erreur}</p>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
