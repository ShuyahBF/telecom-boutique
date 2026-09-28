import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Chargement from "@/components/Chargement";

// Journal des SMS d'une boutique, regroupés par contact (numéro) : utilisé par la
// boutique (/gestion/sms) et par le super-administrateur (onglet Service SMS).
// base = adresse de l'API qui renvoie la liste des contacts ; `${base}/{numéro}` ses messages.
const STATUTS_ENVOI = { ENVOYE: "✅", ECHEC: "❌", NON_ENVOYE: "⛔", NON_CONFIGURE: "⚙️" };

export default function JournalContacts({ base, version = 0 }) {
  const [q, setQ] = useState("");
  const [lignes, setLignes] = useState(null);
  const [ouvert, setOuvert] = useState(null); // numéro dont les messages sont affichés
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    const t = setTimeout(() => {
      apiClient.get(base, { params: { q } }).then(({ data }) => setLignes(data)).catch(() => setLignes([]));
    }, 250);
    return () => clearTimeout(t);
  }, [base, q, version]);

  // Déplier un contact : ses messages, du plus récent au plus ancien
  async function deplier(telephone) {
    if (ouvert === telephone) { setOuvert(null); return; }
    setOuvert(telephone);
    setMessages((await apiClient.get(`${base}/${encodeURIComponent(telephone)}`).catch(() => ({ data: [] }))).data);
  }

  return (
    <div className="space-y-3">
      <input className="input max-w-sm" placeholder="Nom ou numéro…" value={q} onChange={(e) => setQ(e.target.value)} />
      {!lignes ? <Chargement /> : lignes.length === 0 ? <p className="text-sm text-gray-500">Aucun SMS envoyé.</p> : (
        <div className="divide-y divide-gray-100 rounded-2xl border border-gray-200 bg-white">
          {lignes.map((c) => (
            <div key={c.telephone}>
              <button type="button" className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left hover:bg-gray-50" onClick={() => deplier(c.telephone)}>
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold">{c.contact_nom || "Contact sans nom"} <span className="font-mono text-sm font-normal text-gray-500">{c.telephone}</span></span>
                  <span className="block truncate text-xs text-gray-500">{dateHeure(c.dernier_envoi)} — {c.dernier_texte}</span>
                </span>
                <span className="text-right text-sm">
                  <b>{c.nb_messages}</b> message(s) · {c.nb_sms} SMS
                  {c.nb_echecs > 0 && <span className="block text-xs text-red-600">{c.nb_echecs} non envoyé(s)</span>}
                </span>
                <span aria-hidden="true">{ouvert === c.telephone ? "▲" : "▼"}</span>
              </button>
              {ouvert === c.telephone && (
                <ul className="space-y-2 bg-gray-50 px-4 py-3">
                  {messages.map((m) => (
                    <li key={m.id} className="rounded-xl bg-white p-3 text-sm shadow-sm">
                      <p className="whitespace-pre-line">{m.texte}</p>
                      <p className="mt-1 text-xs text-gray-500">
                        {STATUTS_ENVOI[m.statut] || m.statut} {dateHeure(m.date)} · {m.nb_sms} SMS · {m.origine === "MANUEL" ? `envoyé par ${m.auteur || "—"}` : "automatique"}
                        {m.erreur && <span className="text-red-600"> · {m.erreur}</span>}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

