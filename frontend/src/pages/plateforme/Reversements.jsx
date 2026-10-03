import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { aujourdhui, date, dateHeure, montant } from "@/lib/format";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { Champ, EnTetePlateforme } from "./_plateforme/composants";

const fcfa = (v) => `${montant(v || 0)} FCFA`;

// Reversements aux boutiques (super-administrateur) : l'argent des paiements
// Mobile Money (PawaPay) arrive sur le compte de la plateforme ; on suit ici,
// boutique par boutique, ce qui a été encaissé, reversé et reste à reverser,
// et on enregistre chaque reversement (paiements couverts, frais retenus).
export default function Reversements() {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null);
  const [historique, setHistorique] = useState([]);
  const [saisie, setSaisie] = useState(null); // { boutique, paiements, choisis, frais, mode, reference, date, note }

  const charger = useCallback(() => {
    apiClient.get("/plateforme/reversements/boutiques").then(({ data }) => setDonnees(data))
      .catch((err) => toast.erreur(messageErreur(err, "Liste indisponible")));
    apiClient.get("/plateforme/reversements").then(({ data }) => setHistorique(data)).catch(() => {});
  }, [toast]);
  useEffect(() => { charger(); }, [charger]);

  // Ouverture de la saisie : paiements encore à reverser, tous cochés par défaut
  async function ouvrir(b) {
    try {
      const { data } = await apiClient.get(`/plateforme/reversements/boutiques/${b.id}/a-reverser`);
      setSaisie({ boutique: b, paiements: data, choisis: data.map((p) => p.id), frais: 0, mode: "MOBILE_MONEY",
        reference: "", date: aujourdhui(), note: "" });
    } catch (err) {
      toast.erreur(messageErreur(err, "Paiements indisponibles"));
    }
  }

  async function enregistrer(e) {
    e.preventDefault();
    try {
      const { data } = await apiClient.post("/plateforme/reversements", {
        boutique_id: saisie.boutique.id, paiement_ids: saisie.choisis, frais: Number(saisie.frais) || 0,
        mode: saisie.mode, reference: saisie.reference.trim(), date: saisie.date, note: saisie.note.trim(),
      });
      toast.succes(`Reversement ${data.numero} enregistré : ${fcfa(data.montant_net)}`);
      setSaisie(null);
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible"));
    }
  }

  async function annuler(r) {
    if (!window.confirm(`Annuler le reversement ${r.numero} ? Ses ${r.nb_paiements} paiement(s) redeviendront « à reverser ».`)) return;
    try {
      await apiClient.post(`/plateforme/reversements/${r.id}/annuler`);
      toast.succes("Reversement annulé");
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Annulation impossible"));
    }
  }

  // Total des paiements cochés dans la saisie
  const brut = saisie ? saisie.paiements.filter((p) => saisie.choisis.includes(p.id)).reduce((t, p) => t + Number(p.montant), 0) : 0;
  const basculer = (id) => setSaisie((s) => ({ ...s, choisis: s.choisis.includes(id) ? s.choisis.filter((x) => x !== id) : [...s.choisis, id] }));

  return (
    <div className="min-h-screen bg-gray-50">
      <EnTetePlateforme />
      <main className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
        <div>
          <h1 className="text-2xl font-extrabold">Reversements aux boutiques</h1>
          <p className="text-sm text-gray-500">Paiements Mobile Money des clients encaissés sur le compte PawaPay de la plateforme, à reverser à chaque boutique.</p>
        </div>

        {!donnees ? <Chargement /> : (
          <>
            {/* Totaux */}
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {[["Encaissé", donnees.total.encaisse], ["Reversé", donnees.total.reverse], ["Frais retenus", donnees.total.frais], ["Reste à reverser", donnees.total.a_reverser]].map(([l, v]) => (
                <div key={l} className="card p-3"><p className="text-xs text-gray-500">{l}</p>
                  <p className={`text-xl font-extrabold ${l === "Reste à reverser" && v ? "text-orange-600" : ""}`}>{fcfa(v)}</p></div>
              ))}
            </div>

            {/* Situation par boutique */}
            <div className="card overflow-x-auto p-0">
              <table className="table min-w-[760px]">
                <thead><tr><th>Boutique</th><th className="text-right">Encaissé</th><th className="text-right">Reversé</th><th className="text-right">Frais</th><th className="text-right">À reverser</th><th>Dernier reversement</th><th /></tr></thead>
                <tbody>
                  {donnees.boutiques.map((b) => (
                    <tr key={b.id}>
                      <td><p className="font-semibold">{b.nom}</p><p className="font-mono text-xs text-gray-500">{b.code_marchand}</p></td>
                      <td className="text-right">{fcfa(b.encaisse)}</td>
                      <td className="text-right">{fcfa(b.reverse)}</td>
                      <td className="text-right text-gray-500">{fcfa(b.frais)}</td>
                      <td className={`text-right font-semibold ${b.a_reverser ? "text-orange-600" : ""}`}>{fcfa(b.a_reverser)}{b.nb_en_attente > 0 && <span className="block text-xs font-normal">{b.nb_en_attente} paiement(s)</span>}</td>
                      <td>{date(b.dernier_reversement)}</td>
                      <td className="text-right"><button type="button" className="btn-primary btn-sm" disabled={!b.nb_en_attente} onClick={() => ouvrir(b)}>💸 Reverser</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Historique des reversements */}
            <div className="card overflow-x-auto p-0">
              <h2 className="p-4 pb-2 font-bold">Historique des reversements</h2>
              <table className="table min-w-[820px]">
                <thead><tr><th>N°</th><th>Date</th><th>Boutique</th><th className="text-right">Paiements</th><th className="text-right">Brut</th><th className="text-right">Frais</th><th className="text-right">Net versé</th><th>Mode / réf.</th><th /></tr></thead>
                <tbody>
                  {historique.map((r) => (
                    <tr key={r.id} className={r.statut === "ANNULE" ? "text-gray-400 line-through" : ""}>
                      <td className="font-mono text-xs">{r.numero}</td>
                      <td>{date(r.date)}</td>
                      <td>{r.boutique_nom}</td>
                      <td className="text-right">{r.nb_paiements}</td>
                      <td className="text-right">{fcfa(r.montant_brut)}</td>
                      <td className="text-right">{fcfa(r.frais)}</td>
                      <td className="text-right font-semibold">{fcfa(r.montant_net)}</td>
                      <td className="text-xs">{donnees.modes[r.mode] || r.mode}{r.reference && <span className="block text-gray-500">{r.reference}</span>}</td>
                      <td>{r.statut === "VALIDE" && <button type="button" className="btn-outline btn-sm text-red-600" onClick={() => annuler(r)}>Annuler</button>}</td>
                    </tr>
                  ))}
                  {historique.length === 0 && <tr><td colSpan={9} className="text-center text-gray-500">Aucun reversement pour l'instant.</td></tr>}
                </tbody>
              </table>
            </div>
          </>
        )}
      </main>

      {/* Saisie d'un reversement */}
      <Modal ouvert={!!saisie} titre={`Reverser à ${saisie?.boutique.nom || ""}`} onFermer={() => setSaisie(null)} large>
        {saisie && (
          <form onSubmit={enregistrer} className="space-y-4">
            <div className="max-h-64 overflow-y-auto rounded-xl border border-gray-200">
              <table className="table">
                <thead><tr><th /><th>Date</th><th>Commande / fiche</th><th>Client</th><th className="text-right">Montant</th></tr></thead>
                <tbody>
                  {saisie.paiements.map((p) => (
                    <tr key={p.id} /* ligne cochée = sélectionnée (index.css) */ aria-selected={saisie.choisis.includes(p.id)}>
                      <td><input type="checkbox" className="h-4 w-4 accent-primary" checked={saisie.choisis.includes(p.id)} onChange={() => basculer(p.id)} aria-label={`Inclure ${p.commande_numero || p.fiche_numero}`} /></td>
                      <td className="whitespace-nowrap">{dateHeure(p.updated_at || p.created_at)}</td>
                      <td className="font-mono text-xs">{p.commande_numero || p.fiche_numero}</td>
                      <td>{p.client_nom}</td>
                      <td className="text-right">{fcfa(p.montant)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <Champ label="Frais retenus (FCFA)" aide="Ex. frais PawaPay ou commission."><input className="input" type="number" min={0} value={saisie.frais} onChange={(e) => setSaisie({ ...saisie, frais: e.target.value })} /></Champ>
              <Champ label="Mode">
                <select className="input" value={saisie.mode} onChange={(e) => setSaisie({ ...saisie, mode: e.target.value })}>
                  {Object.entries(donnees.modes).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
                </select>
              </Champ>
              <Champ label="Date"><input className="input" type="date" required value={saisie.date} onChange={(e) => setSaisie({ ...saisie, date: e.target.value })} /></Champ>
              <Champ label="Référence du transfert" className="sm:col-span-3"><input className="input" maxLength={120} value={saisie.reference} onChange={(e) => setSaisie({ ...saisie, reference: e.target.value })} placeholder="n° de transaction Orange Money, virement…" /></Champ>
            </div>
            <p className="rounded-xl bg-gray-50 p-3 text-sm">
              {saisie.choisis.length} paiement(s) : {fcfa(brut)} − frais {fcfa(saisie.frais)} = <b>{fcfa(brut - (Number(saisie.frais) || 0))} à verser</b>
            </p>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-outline" onClick={() => setSaisie(null)}>Annuler</button>
              <button className="btn-primary" disabled={!saisie.choisis.length || Number(saisie.frais) > brut}>Enregistrer le reversement</button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
