import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { date, dateHeure, prix } from "@/lib/format";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { EnTetePlateforme } from "./_plateforme/composants";

// ---------------------------------------------------------------------------
// Page « Cycle de vie » de la plateforme (super-administrateur) — backend/cycle_vie.py :
// non-renouvellement d'un abonnement : avertissement à J+103, suspension à J+110,
// dernier avis à J+112, archive chiffrée vérifiée sur R2 puis suppression à J+113.
// Réglages (interrupteur, simulation, conservation, frais de réouverture), boutiques
// concernées, archives (réouverture), derniers rapports quotidiens et alertes.
// ---------------------------------------------------------------------------
const ETAPES = {
  NORMALE: { libelle: "Avant le premier avis", classe: "bg-gray-100 text-gray-700" },
  A_AVERTIR: { libelle: "Avis J+103 à envoyer", classe: "bg-amber-100 text-amber-800" },
  AVERTIE: { libelle: "Avertie (J+103)", classe: "bg-amber-100 text-amber-800" },
  SUSPENDUE: { libelle: "Suspendue (J+110)", classe: "bg-red-100 text-red-700" },
  EN_PAUSE: { libelle: "Suspension levée (cycle en pause)", classe: "bg-blue-100 text-blue-800" },
  ARCHIVEE: { libelle: "Archivée", classe: "bg-gray-800 text-white" },
};
const ACTIONS = {
  AVERTISSEMENT_J103: "Avertissement J+103",
  SUSPENSION: "Suspension",
  AVERTISSEMENT_J110: "Avertissement J+110",
  AVERTISSEMENT_J112: "Dernier avis J+112",
  ARCHIVAGE: "Archivage puis suppression",
  EFFACEMENT_ARCHIVE: "Effacement de l'archive",
};
const MODES = { ESPECES: "Espèces", MOBILE_MONEY: "Mobile Money (transfert)", VIREMENT: "Virement", CHEQUE: "Chèque", OFFERT: "Geste commercial (gratuit)" };

function Pastille({ etape }) {
  const e = ETAPES[etape] || { libelle: etape, classe: "bg-gray-100 text-gray-700" };
  return <span className={`badge whitespace-nowrap ${e.classe}`}>{e.libelle}</span>;
}

// Résultat d'une exécution (réelle ou simulée) : liste des actions
function Rapport({ rapport }) {
  if (!rapport) return null;
  return (
    <div className="space-y-1 rounded-lg bg-gray-50 p-3 text-sm">
      <p className="font-semibold">
        {rapport.simulation ? "🧪 Simulation" : "▶ Exécution"} du {date(rapport.jour)} ({rapport.declencheur}) :{" "}
        {rapport.statut === "DESACTIVE" ? "cycle de vie désactivé" : `${rapport.actions.length} action(s)`}
      </p>
      {rapport.actions.map((a, i) => (
        <p key={i} className="text-gray-700">• {a.code_marchand} {a.boutique_nom} — {ACTIONS[a.action] || a.action} (J+{a.jours_depuis_echeance}) : <b>{a.statut}</b>{a.erreur ? ` — ${a.erreur}` : ""}</p>
      ))}
      {rapport.archives_effacees?.map((a, i) => (
        <p key={`e${i}`} className="text-gray-700">• Archive de {a.boutique_nom} ({date(a.jour_archive)}) : effacement <b>{a.statut}</b></p>
      ))}
      {rapport.erreurs?.map((e, i) => <p key={`x${i}`} className="text-red-700">• {e.boutique_nom} : {e.erreur}</p>)}
    </div>
  );
}

export default function CycleVie() {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null);
  const [form, setForm] = useState(null);
  const [occupe, setOccupe] = useState(false);
  const [rapport, setRapport] = useState(null);
  const [reouverture, setReouverture] = useState(null); // { boutique, mode, montant, reference, formule, montant_abonnement }

  const charger = useCallback(() => {
    apiClient.get("/plateforme/cycle-vie").then(({ data }) => { setDonnees(data); setForm(data.parametres); })
      .catch((err) => toast.erreur(messageErreur(err, "Cycle de vie indisponible")));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  async function enregistrer(e) {
    e.preventDefault();
    setOccupe(true);
    try {
      await apiClient.put("/plateforme/cycle-vie/parametres", {
        actif: form.actif, simulation: form.simulation, conservation_jours: Number(form.conservation_jours),
        frais_montant: Number(form.frais_montant), frais_devise: form.frais_devise });
      toast.succes("Réglages du cycle de vie enregistrés");
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible"));
    } finally {
      setOccupe(false);
    }
  }

  async function executer(simulation) {
    if (!simulation && !window.confirm("Exécuter MAINTENANT le cycle de vie (avertissements, suspensions, archivages et suppressions dus) ?")) return;
    setOccupe(true);
    try {
      const { data } = await apiClient.post("/plateforme/cycle-vie/executer", { simulation }, { timeout: 600000 });
      setRapport(data);
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Exécution impossible"));
    } finally {
      setOccupe(false);
    }
  }

  async function reouvrir(e) {
    e.preventDefault();
    setOccupe(true);
    try {
      const r = reouverture;
      await apiClient.post(`/plateforme/cycle-vie/boutiques/${r.boutique.boutique_id}/reouvrir`, {
        mode: r.mode, montant: Number(r.montant || 0), reference: r.reference,
        formule: r.formule || null, montant_abonnement: Number(r.montant_abonnement || 0) }, { timeout: 600000 });
      toast.succes(`Boutique « ${r.boutique.boutique_nom} » réouverte et restaurée`);
      setReouverture(null);
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Réouverture impossible"));
    } finally {
      setOccupe(false);
    }
  }

  const maj = (champ, valeur) => setForm((f) => ({ ...f, [champ]: valeur }));
  const majR = (champ, valeur) => setReouverture((r) => ({ ...r, [champ]: valeur }));

  return (
    <div className="min-h-screen bg-papier">
      <EnTetePlateforme />
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        <div>
          <h1 className="text-2xl font-extrabold">♻️ Cycle de vie des abonnements non renouvelés</h1>
          <p className="text-sm text-gray-500">
            Jours comptés depuis l'échéance impayée : avertissement à J+103, suspension à J+110, dernier avis à J+112,
            archive chiffrée vérifiée sur R2 puis suppression des données à J+113. Boutiques de test exclues.
          </p>
        </div>
        {!donnees || !form ? <Chargement /> : (
          <>
            {(!donnees.phrase_configuree || !donnees.r2_configure) && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                ⚠️ Archivage impossible : {!donnees.phrase_configuree && "variable SAUVEGARDE_AUTO_PHRASE absente. "}
                {!donnees.r2_configure && "Cloudflare R2 non configuré."} Aucune donnée ne sera supprimée tant que l'archive ne peut pas être vérifiée.
              </div>
            )}
            {donnees.alertes.length > 0 && (
              <div className="space-y-1 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                <p className="font-semibold">Dernières alertes</p>
                {donnees.alertes.map((a) => <p key={a.id}>{dateHeure(a.date)} — {a.boutique_nom} : {a.message.split("\n")[0]}</p>)}
              </div>
            )}

            {/* Réglages */}
            <form onSubmit={enregistrer} className="card space-y-3">
              <h2 className="text-lg font-bold">⚙️ Réglages</h2>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.actif} onChange={(e) => maj("actif", e.target.checked)} />
                Cycle de vie automatique activé
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.simulation} onChange={(e) => maj("simulation", e.target.checked)} />
                Mode simulation : la tâche quotidienne liste ce qui serait fait, sans rien faire ni envoyer
              </label>
              <div className="grid gap-3 sm:grid-cols-3">
                <label>
                  <span className="label">Conservation des archives (jours)</span>
                  <input className="input" type="number" min="1" max="36500" required value={form.conservation_jours} onChange={(e) => maj("conservation_jours", e.target.value)} />
                </label>
                <label>
                  <span className="label">Frais de réouverture (0 = gratuit)</span>
                  <input className="input" type="number" min="0" required value={form.frais_montant} onChange={(e) => maj("frais_montant", e.target.value)} />
                </label>
                <label>
                  <span className="label">Devise</span>
                  <input className="input" maxLength={10} required value={form.frais_devise} onChange={(e) => maj("frais_devise", e.target.value)} />
                </label>
              </div>
              <div className="flex flex-wrap gap-2">
                <button className="btn-primary" disabled={occupe}>💾 Enregistrer</button>
                <button type="button" className="btn-outline" disabled={occupe} onClick={() => executer(true)}>🧪 Simuler maintenant</button>
                <button type="button" className="btn-outline" disabled={occupe || !form.actif} onClick={() => executer(false)}>▶ Exécuter maintenant</button>
              </div>
              {form.modifie_le && <p className="text-xs text-gray-500">Modifié le {dateHeure(form.modifie_le)} par {form.modifie_par}</p>}
              <Rapport rapport={rapport} />
            </form>

            {/* Boutiques concernées */}
            <section className="card space-y-3">
              <h2 className="text-lg font-bold">🏪 Boutiques concernées ({donnees.boutiques.length})</h2>
              {donnees.boutiques.length === 0 ? <p className="text-sm text-gray-500">Aucune boutique proche des échéances du cycle.</p> : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-left text-gray-500">
                      <th className="py-2 pr-3">Boutique</th><th className="pr-3">Échéance</th><th className="pr-3">Jours</th>
                      <th className="pr-3">Étape</th><th className="pr-3">Suspension</th><th className="pr-3">Archivage</th><th className="pr-3">À faire</th><th />
                    </tr></thead>
                    <tbody>
                      {donnees.boutiques.map((b) => (
                        <tr key={b.id} className="border-t border-gray-100">
                          <td className="py-2 pr-3"><b>{b.nom}</b> <span className="text-gray-500">{b.code_marchand}</span></td>
                          <td className="pr-3">{date(b.echeance)}</td>
                          <td className="pr-3">J+{b.jours_depuis_echeance}</td>
                          <td className="pr-3"><Pastille etape={b.etape} />{b.archivage_echecs > 0 && <span className="ml-1 badge bg-red-100 text-red-700">{b.archivage_echecs} échec(s)</span>}</td>
                          <td className="pr-3">{date(b.suspension_le)}</td>
                          <td className="pr-3">{date(b.archivage_le)}</td>
                          <td className="pr-3 text-xs">{b.actions_dues.map((a) => ACTIONS[a] || a).join(", ") || "—"}</td>
                          <td />
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            {/* Archives */}
            <section className="card space-y-3">
              <h2 className="text-lg font-bold">🗃️ Archives ({donnees.bucket}/{donnees.prefixe_archives})</h2>
              <p className="text-sm text-gray-500">
                Conservées {form.conservation_jours} jours puis effacées de R2. Réouverture : frais de {prix(donnees.parametres.frais_montant, donnees.parametres.frais_devise)}.
              </p>
              {donnees.archives.length === 0 ? <p className="text-sm text-gray-500">Aucune archive.</p> : (
                <div className="space-y-2">
                  {donnees.archives.map((a) => (
                    <div key={a.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-100 p-2 text-sm">
                      <span className="font-semibold">{a.boutique_nom}</span>
                      <span className="text-gray-500">{a.code_marchand}</span>
                      <span>archivée le {date(a.jour)} · {a.documents} document(s) · {a.comptes_utilisateurs} compte(s)</span>
                      {a.efface_le ? <span className="badge bg-gray-100 text-gray-600">Effacée le {date(a.efface_le)}</span>
                        : <button type="button" className="btn-outline btn-sm ml-auto" disabled={occupe}
                          onClick={() => setReouverture({ boutique: a, mode: "ESPECES", montant: donnees.parametres.frais_montant, reference: "", formule: "", montant_abonnement: 0 })}>
                          Réouvrir
                        </button>}
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Derniers rapports */}
            <section className="card space-y-3">
              <h2 className="text-lg font-bold">📋 Derniers rapports quotidiens</h2>
              {donnees.executions.length === 0 ? <p className="text-sm text-gray-500">Aucune exécution enregistrée.</p>
                : donnees.executions.map((r) => <Rapport key={r.id} rapport={r} />)}
            </section>
          </>
        )}
      </main>

      <Modal ouvert={!!reouverture} titre={`Réouvrir « ${reouverture?.boutique.boutique_nom || ""} »`} onFermer={() => setReouverture(null)}>
        {reouverture && (
          <form onSubmit={reouvrir} className="space-y-3 text-sm">
            <p className="text-gray-600">
              Frais de réouverture : <b>{prix(donnees.parametres.frais_montant, donnees.parametres.frais_devise)}</b>.
              L'archive est relue depuis R2, vérifiée puis restaurée (cette boutique uniquement) ; la boutique est réactivée.
            </p>
            <label className="block"><span className="label">Mode de paiement des frais</span>
              <select className="input" value={reouverture.mode} onChange={(e) => majR("mode", e.target.value)}>
                {Object.entries(MODES).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
              </select>
            </label>
            <label className="block"><span className="label">Montant encaissé ({donnees.parametres.frais_devise})</span>
              <input className="input" type="number" min="0" value={reouverture.montant} onChange={(e) => majR("montant", e.target.value)} />
            </label>
            <label className="block"><span className="label">Référence du paiement</span>
              <input className="input" maxLength={120} value={reouverture.reference} onChange={(e) => majR("reference", e.target.value)} />
            </label>
            <label className="block"><span className="label">Formule d'abonnement payée en même temps (facultatif, code)</span>
              <input className="input" maxLength={30} placeholder="MENSUEL, TRIMESTRIEL…" value={reouverture.formule} onChange={(e) => majR("formule", e.target.value.toUpperCase())} />
            </label>
            {reouverture.formule && (
              <label className="block"><span className="label">Montant de l'abonnement encaissé</span>
                <input className="input" type="number" min="0" value={reouverture.montant_abonnement} onChange={(e) => majR("montant_abonnement", e.target.value)} />
              </label>
            )}
            <p className="text-xs text-gray-500">Sans formule, la nouvelle échéance est aujourd'hui : le DG dispose de la période de grâce pour payer son abonnement.</p>
            <button className="btn-primary w-full" disabled={occupe}>{occupe ? "Restauration…" : "Encaisser et réouvrir"}</button>
          </form>
        )}
      </Modal>
    </div>
  );
}
