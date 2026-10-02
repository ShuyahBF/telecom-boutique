import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import { EnTetePlateforme } from "./_plateforme/composants";

// ---------------------------------------------------------------------------
// Page « KYC des DG » (super-administrateur) — backend/kyc_dg.py : responsables dont
// le dossier KYC n'est pas à jour (absent, refusé, incomplet ; en attente sur demande),
// sélection par cases à cocher et rappel WhatsApp (message modifiable, variables
// {dg} {boutique} {etat} {lien}), au plus 1 rappel par DG et par 24 h, journal.
// ---------------------------------------------------------------------------
const ETATS = {
  ABSENT: "bg-gray-100 text-gray-700",
  REFUSE: "bg-red-100 text-red-700",
  INCOMPLET: "bg-amber-100 text-amber-800",
  EN_ATTENTE: "bg-blue-100 text-blue-800",
};
const STATUTS_ENVOI = {
  ENVOYE: "bg-green-100 text-green-800",
  LIMITE_24H: "bg-amber-100 text-amber-800",
  ECHEC: "bg-red-100 text-red-700",
  NON_CONFIGURE: "bg-red-100 text-red-700",
};

export default function KycDg() {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null);
  const [inclureAttente, setInclureAttente] = useState(false);
  const [selection, setSelection] = useState([]);
  const [message, setMessage] = useState("");
  const [journal, setJournal] = useState([]);
  const [envoi, setEnvoi] = useState(false);

  const charger = useCallback(() => {
    apiClient.get("/plateforme/kyc-dg", { params: { inclure_en_attente: inclureAttente } })
      .then(({ data }) => { setDonnees(data); setMessage((m) => m || data.message_defaut); })
      .catch((err) => toast.erreur(messageErreur(err, "Liste indisponible")));
    apiClient.get("/plateforme/kyc-dg/journal").then(({ data }) => setJournal(data)).catch(() => {});
  }, [inclureAttente]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  const dg = donnees?.dg || [];
  const selectionnables = dg.filter((d) => d.dg_id && !d.rappel_possible_le).map((d) => d.boutique_id);
  const basculer = (id) => setSelection((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const toutCocher = () => setSelection((s) => (s.length === selectionnables.length ? [] : selectionnables));

  async function envoyer() {
    if (!selection.length) return;
    if (!window.confirm(`Envoyer un rappel WhatsApp à ${selection.length} DG ?`)) return;
    setEnvoi(true);
    try {
      const { data } = await apiClient.post("/plateforme/kyc-dg/rappels", { boutique_ids: selection, message }, { timeout: 120000 });
      const autres = data.resultats.length - data.envoyes;
      toast.succes(`${data.envoyes} rappel(s) envoyé(s)${autres ? `, ${autres} non envoyé(s) (voir le journal)` : ""}`);
      setSelection([]);
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <EnTetePlateforme />
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        <div>
          <h1 className="text-2xl font-extrabold">🪪 KYC des DG</h1>
          <p className="text-sm text-gray-500">Responsables de boutique dont le dossier d'identification n'est pas à jour. Un rappel au plus par DG et par {donnees?.limite_heures || 24} h.</p>
        </div>
        {!donnees ? <Chargement /> : (
          <>
            <section className="card space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-bold">DG concernés ({dg.length})</h2>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={inclureAttente} onChange={(e) => { setInclureAttente(e.target.checked); setSelection([]); }} />
                  Inclure les dossiers complets en attente de vérification
                </label>
              </div>
              {dg.length === 0 ? <p className="text-sm text-gray-500">Tous les KYC sont à jour.</p> : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-left text-gray-500">
                      <th className="py-2 pr-2"><input type="checkbox" aria-label="Tout cocher" checked={selection.length > 0 && selection.length === selectionnables.length} onChange={toutCocher} /></th>
                      <th className="pr-3">Boutique</th><th className="pr-3">DG</th><th className="pr-3">Téléphone</th>
                      <th className="pr-3">État du KYC</th><th className="pr-3">Dernier rappel</th>
                    </tr></thead>
                    <tbody>
                      {dg.map((d) => (
                        <tr key={d.boutique_id} className="border-t border-gray-100">
                          <td className="py-2 pr-2">
                            <input type="checkbox" aria-label={`Sélectionner ${d.dg_nom}`} disabled={!selectionnables.includes(d.boutique_id)}
                              checked={selection.includes(d.boutique_id)} onChange={() => basculer(d.boutique_id)} />
                          </td>
                          <td className="pr-3"><b>{d.boutique_nom}</b> <span className="text-gray-500">{d.code_marchand}</span></td>
                          <td className="pr-3">{d.dg_nom || <span className="text-red-700">aucun compte DG</span>}</td>
                          <td className="pr-3">{d.telephone || "—"}</td>
                          <td className="pr-3">
                            <span className={`badge ${ETATS[d.etat] || ""}`}>{d.etat_libelle}</span>
                            {d.motif_rejet && <span className="ml-1 text-xs text-gray-500">({d.motif_rejet})</span>}
                          </td>
                          <td className="pr-3 text-xs">
                            {d.dernier_rappel ? dateHeure(d.dernier_rappel) : "—"}
                            {d.rappel_possible_le && <span className="block text-amber-700">possible à partir du {dateHeure(d.rappel_possible_le)}</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="card space-y-3">
              <h2 className="text-lg font-bold">💬 Rappel WhatsApp</h2>
              <p className="text-xs text-gray-500">Variables : {"{dg}"} nom du DG, {"{boutique}"} nom de la boutique, {"{etat}"} état du KYC, {"{lien}"} lien vers les paramètres.</p>
              <textarea className="input min-h-[110px]" maxLength={1000} value={message} onChange={(e) => setMessage(e.target.value)} />
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn-primary" disabled={envoi || !selection.length} onClick={envoyer}>
                  {envoi ? "Envoi…" : `Envoyer un rappel WhatsApp (${selection.length})`}
                </button>
                <button type="button" className="btn-outline" onClick={() => setMessage(donnees.message_defaut)}>Message prédéfini</button>
              </div>
            </section>

            <section className="card space-y-2">
              <h2 className="text-lg font-bold">📋 Journal des rappels</h2>
              {journal.length === 0 ? <p className="text-sm text-gray-500">Aucun rappel envoyé.</p> : journal.slice(0, 100).map((j) => (
                <p key={j.id} className="text-sm">
                  {dateHeure(j.date)} — {j.boutique_nom || j.boutique_id} {j.dg_nom ? `(${j.dg_nom})` : ""}{" "}
                  <span className={`badge ${STATUTS_ENVOI[j.statut] || "bg-gray-100 text-gray-700"}`}>{j.statut}</span>
                  {j.erreur && <span className="text-xs text-gray-500"> {j.erreur}</span>}
                  <span className="text-xs text-gray-400"> par {j.par}</span>
                </p>
              ))}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
