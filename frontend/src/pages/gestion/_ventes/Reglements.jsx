import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { aujourdhui, date, prix } from "@/lib/format";
import { useToast } from "@/components/Toast";
import Confirmation from "./Confirmation";
import { BadgePaiement } from "./outils";

// Bloc « Règlements » d'une facture : liste des paiements reçus, ajout et
// suppression. doc = facture telle que renvoyée par le serveur ;
// onMaj(docMisAJour) est appelé après chaque ajout / suppression.
export default function Reglements({ doc, devise, onMaj }) {
  const toast = useToast();
  // Modes de règlement proposés par le serveur ({ESP: "Espèces", ...})
  const [modes, setModes] = useState({});
  // Formulaire d'ajout ; le montant est pré-rempli avec le reste à payer
  const [saisie, setSaisie] = useState({ montant: "", mode: "ESP", date: aujourdhui(), reference: "" });
  const [enCours, setEnCours] = useState(false);
  const [aSupprimer, setASupprimer] = useState(null); // règlement dont on demande confirmation

  // Chargement de la liste des modes de règlement (une seule fois)
  useEffect(() => {
    apiClient.get("/documents/modes-reglement").then(({ data }) => setModes(data)).catch(() => {});
  }, []);

  // Dès que le reste à payer change, on le propose comme montant du prochain règlement
  useEffect(() => {
    setSaisie((s) => ({ ...s, montant: doc.reste_a_payer > 0 ? String(doc.reste_a_payer) : "" }));
  }, [doc.reste_a_payer]);

  const annule = doc.statut === "ANNULE";

  // Enregistrement d'un règlement (POST /documents/{id}/reglements)
  async function ajouter(e) {
    e.preventDefault();
    const valeur = Math.round(Number(saisie.montant));
    if (!valeur || valeur <= 0) {
      toast.erreur("Indiquez un montant supérieur à zéro");
      return;
    }
    setEnCours(true);
    try {
      const { data } = await apiClient.post(`/documents/${doc.id}/reglements`, { ...saisie, montant: valeur, reference: saisie.reference.trim() });
      onMaj(data);
      setSaisie((s) => ({ ...s, reference: "" }));
      toast.succes("Règlement enregistré");
    } catch (err) {
      toast.erreur(messageErreur(err, "Règlement refusé : vérifiez le montant et la date"));
    } finally {
      setEnCours(false);
    }
  }

  // Suppression d'un règlement (DELETE /documents/{id}/reglements/{rid})
  async function supprimer() {
    setEnCours(true);
    try {
      const { data } = await apiClient.delete(`/documents/${doc.id}/reglements/${aSupprimer.id}`);
      onMaj(data);
      toast.succes("Règlement supprimé");
      setASupprimer(null);
    } catch (err) {
      toast.erreur(messageErreur(err, "Suppression impossible"));
    } finally {
      setEnCours(false);
    }
  }

  return (
    <section className="card">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">Règlements</h2>
        <BadgePaiement libelle={doc.statut_paiement} />
      </div>

      {/* Résumé : total, déjà réglé, reste à payer */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-xl bg-gray-50 p-3"><p className="text-xs text-gray-500">Total TTC</p><p className="font-bold">{prix(doc.total_ttc, devise)}</p></div>
        <div className="rounded-xl bg-green-50 p-3"><p className="text-xs text-green-700">Réglé</p><p className="font-bold text-green-800">{prix(doc.total_regle, devise)}</p></div>
        <div className={`rounded-xl p-3 ${doc.reste_a_payer > 0 ? "bg-red-50" : "bg-gray-50"}`}>
          <p className={`text-xs ${doc.reste_a_payer > 0 ? "text-red-700" : "text-gray-500"}`}>Reste à payer</p>
          <p className={`font-bold ${doc.reste_a_payer > 0 ? "text-red-700" : ""}`}>{prix(doc.reste_a_payer, devise)}</p>
        </div>
      </div>

      {/* Liste des règlements déjà reçus */}
      {doc.reglements?.length > 0 && (
        <ul className="mt-4 divide-y divide-gray-100 rounded-xl border border-gray-100">
          {doc.reglements.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <div className="min-w-0">
                <p className="font-semibold">{prix(r.montant, devise)} <span className="font-normal text-gray-600">· {modes[r.mode] || r.mode}</span></p>
                <p className="truncate text-xs text-gray-500">{date(r.date)}{r.reference ? ` · réf. ${r.reference}` : ""}{r.saisi_par ? ` · saisi par ${r.saisi_par}` : ""}</p>
              </div>
              {/* Un paiement Mobile Money (PawaPay) est confirmé par l'opérateur : non supprimable */}
              {r.mode === "MM"
                ? <span className="badge bg-blue-50 text-blue-700" title="Paiement confirmé par l'opérateur">PawaPay</span>
                : !annule && <button type="button" className="rounded-lg px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50" onClick={() => setASupprimer(r)}>Supprimer</button>}
            </li>
          ))}
        </ul>
      )}

      {/* Formulaire d'ajout (tant qu'il reste quelque chose à payer) */}
      {!annule && (doc.reste_a_payer > 0 ? (
        <form onSubmit={ajouter} className="mt-4 grid gap-3 border-t border-gray-100 pt-4 sm:grid-cols-2 lg:grid-cols-5 lg:items-end">
          <div><label className="label" htmlFor="reg-montant">Montant</label>
            <input id="reg-montant" className="input" type="number" min={1} step={1} required value={saisie.montant} onChange={(e) => setSaisie({ ...saisie, montant: e.target.value })} /></div>
          <div><label className="label" htmlFor="reg-mode">Mode</label>
            <select id="reg-mode" className="input" value={saisie.mode} onChange={(e) => setSaisie({ ...saisie, mode: e.target.value })}>
              {Object.entries(modes).filter(([k]) => k !== "MM").map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              {Object.keys(modes).length === 0 && <option value="ESP">Espèces</option>}
            </select></div>
          <div><label className="label" htmlFor="reg-date">Date</label>
            <input id="reg-date" className="input" type="date" required value={saisie.date} onChange={(e) => setSaisie({ ...saisie, date: e.target.value })} /></div>
          {/* PI-SPI : la référence bancaire du virement est obligatoire (rapprochement avec le relevé) */}
          <div><label className="label" htmlFor="reg-ref">{saisie.mode === "PISPI" ? "Référence bancaire *" : "Référence"}</label>
            <input id="reg-ref" className="input" maxLength={60} required={saisie.mode === "PISPI"}
              placeholder={saisie.mode === "PISPI" ? "réf. du virement PI-SPI" : "n° de transaction…"} value={saisie.reference} onChange={(e) => setSaisie({ ...saisie, reference: e.target.value })} /></div>
          <button className="btn-primary" disabled={enCours}>{enCours ? "…" : "Enregistrer le règlement"}</button>
        </form>
      ) : (
        <p className="mt-4 rounded-xl bg-green-50 p-3 text-center text-sm font-semibold text-green-800">✓ Cette facture est entièrement réglée.</p>
      ))}

      <Confirmation ouvert={!!aSupprimer} titre="Supprimer ce règlement ?" danger libelleBouton="Supprimer" enCours={enCours}
        onConfirmer={supprimer} onFermer={() => setASupprimer(null)}>
        {aSupprimer && <p>Le règlement de <b>{prix(aSupprimer.montant, devise)}</b> du {date(aSupprimer.date)} sera retiré de la facture.</p>}
      </Confirmation>
    </section>
  );
}
