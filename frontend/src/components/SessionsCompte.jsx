import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";

// « Mon compte » : sessions ouvertes de ce compte (appareil, IP, ouverture, dernière
// activité) avec un bouton « Fermer » par session (backend/sessions_actives.py).
// Le nombre de sessions simultanées est limité : à la connexion de trop, la plus
// ancienne est fermée automatiquement.
export default function SessionsCompte({ version = 0 }) {
  const [donnees, setDonnees] = useState(null);
  const [erreur, setErreur] = useState("");
  const [occupe, setOccupe] = useState("");

  const charger = useCallback(() => {
    apiClient.get("/auth/sessions").then(({ data }) => setDonnees(data))
      .catch((err) => setErreur(messageErreur(err, "Sessions indisponibles")));
  }, []);
  useEffect(() => { charger(); }, [charger, version]);

  async function fermer(s) {
    if (!window.confirm(`Fermer la session « ${s.appareil} » ? Cet appareil devra se reconnecter.`)) return;
    setOccupe(s.id);
    setErreur("");
    try {
      await apiClient.post(`/auth/sessions/${s.id}/fermer`);
      charger();
    } catch (err) {
      setErreur(messageErreur(err, "Impossible de fermer la session"));
    } finally {
      setOccupe("");
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 p-4 text-sm">
      <p className="font-semibold text-gray-600">💻 Sessions ouvertes{donnees && ` (${donnees.sessions.length}/${donnees.limite})`}</p>
      {donnees && <p className="text-xs text-gray-500">Au plus {donnees.limite} appareils connectés en même temps : au-delà, la session la plus ancienne est fermée.</p>}
      {erreur && <p className="mt-2 rounded-lg bg-red-50 p-2 text-red-700">{erreur}</p>}
      {!donnees ? <p className="mt-2 text-gray-500">Chargement…</p> : (
        <ul className="mt-2 divide-y divide-gray-100">
          {donnees.sessions.map((s) => (
            <li key={s.id} className="flex items-center gap-2 py-2">
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{s.appareil}{s.courante && <span className="badge ml-2 bg-green-100 text-green-800">cet appareil</span>}</p>
                <p className="text-xs text-gray-500">IP {s.ip || "—"} · ouverte le {dateHeure(s.ouverte_le)} · active le {dateHeure(s.derniere_activite)}</p>
              </div>
              {!s.courante && (
                <button type="button" className="btn-outline btn-sm" disabled={!!occupe} onClick={() => fermer(s)}>
                  {occupe === s.id ? "…" : "Fermer"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
