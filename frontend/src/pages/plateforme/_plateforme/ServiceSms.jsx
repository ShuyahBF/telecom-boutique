import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { aujourdhui, date, montant } from "@/lib/format";
import { MODES_ABONNEMENT } from "@/lib/statuts";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import JournalContacts from "@/components/JournalSms";
import { useToast } from "@/components/Toast";
import { Champ } from "./composants";

const fcfa = (v) => `${montant(v || 0)} FCFA`;

// Couleur du badge d'état du service SMS d'une boutique
const COULEURS_SERVICE = {
  ACTIF: "bg-green-100 text-green-800", SUSPENDU: "bg-red-100 text-red-700",
  DESACTIVE: "bg-gray-100 text-gray-600", NON_CONFIGURE: "bg-gray-100 text-gray-500",
};
export function BadgeService({ service }) {
  return <span className={`badge ${COULEURS_SERVICE[service.statut] || "bg-gray-100"}`}>{service.libelle}</span>;
}

// Onglet « Service SMS » des abonnements (super-administrateur) :
//  - configuration du service de chaque boutique (expéditeur OVH, prix du SMS) ;
//  - journal de ses envois, regroupés par contact ;
//  - factures (générées le 1er du mois, ou à la demande), paiements reçus ;
//  - retards : sélection des boutiques dont on suspend le SEUL service SMS.
export default function ServiceSms() {
  const [vue, setVue] = useState("boutiques");
  const [version, setVersion] = useState(0); // incrémentée pour tout recharger après une action
  const recharger = () => setVersion((v) => v + 1);

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">
        SMS envoyés par OVH au nom de chaque boutique (expéditeur déclaré pour elle). Facturation au SMS, le 1er de chaque mois
        pour le mois écoulé. En cas de retard, vous suspendez le seul service SMS : le reste de la boutique continue de fonctionner.
      </p>
      <div className="inline-flex flex-wrap rounded-xl border border-gray-200 bg-white p-1">
        {[["boutiques", "Boutiques"], ["factures", "Factures"], ["retards", "Retards"]].map(([cle, libelle]) => (
          <button key={cle} type="button" onClick={() => setVue(cle)}
            className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${vue === cle ? "bg-primary text-white" : "text-gray-600"}`}>{libelle}</button>
        ))}
      </div>
      {vue === "boutiques" && <Boutiques key={version} onMaj={recharger} />}
      {vue === "factures" && <Factures key={version} onMaj={recharger} />}
      {vue === "retards" && <Retards key={version} onMaj={recharger} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Boutiques : configuration du service + journal par contact
// ---------------------------------------------------------------------------
function Boutiques({ onMaj }) {
  const toast = useToast();
  const [lignes, setLignes] = useState(null);
  const [config, setConfig] = useState(null); // formulaire de configuration ouvert
  const [journal, setJournal] = useState(null); // boutique dont on consulte les envois

  useEffect(() => {
    apiClient.get("/plateforme/sms/boutiques").then(({ data }) => setLignes(data))
      .catch((err) => toast.erreur(messageErreur(err, "Liste indisponible")));
  }, [toast]);

  // Ouverture du formulaire, prérempli avec la configuration actuelle
  const ouvrir = (b) => setConfig({
    boutique: b, expediteur: b.service.expediteur || b.code_marchand, service_ovh: b.service_ovh || "",
    prix_sms: b.service.prix_sms, notifications_auto: b.service.notifications_auto, actif: b.actif,
  });

  async function enregistrer(e) {
    e.preventDefault();
    try {
      await apiClient.put(`/plateforme/sms/boutiques/${config.boutique.id}`, {
        expediteur: config.expediteur.trim(), service_ovh: config.service_ovh.trim(), prix_sms: Number(config.prix_sms) || 0,
        notifications_auto: config.notifications_auto, actif: config.actif,
      });
      toast.succes("Service SMS configuré");
      setConfig(null);
      onMaj();
    } catch (err) {
      toast.erreur(messageErreur(err, "Configuration refusée"));
    }
  }

  if (!lignes) return <Chargement />;
  return (
    <>
      <div className="card overflow-x-auto p-0">
        <table className="table min-w-[760px]">
          <thead><tr><th>Boutique</th><th>Service</th><th>Expéditeur</th><th className="text-right">Prix / SMS</th><th className="text-right">SMS non facturés</th><th className="text-right">Dû</th><th /></tr></thead>
          <tbody>
            {lignes.map((b) => (
              <tr key={b.id}>
                <td><p className="font-semibold">{b.nom}</p><p className="font-mono text-xs text-gray-500">{b.code_marchand}</p></td>
                <td><BadgeService service={b.service} /></td>
                <td className="font-mono">{b.service.expediteur || "—"}{b.service_ovh && <span className="block text-xs text-gray-500">{b.service_ovh}</span>}</td>
                <td className="text-right">{b.service.expediteur ? fcfa(b.service.prix_sms) : "—"}</td>
                <td className="text-right">{b.sms_non_factures}</td>
                <td className={`text-right ${b.retard_max ? "font-semibold text-red-600" : ""}`}>{b.montant_du ? fcfa(b.montant_du) : "—"}{b.retard_max > 0 && <span className="block text-xs">{b.retard_max} j de retard</span>}</td>
                <td className="whitespace-nowrap text-right">
                  <button type="button" className="btn-outline btn-sm mr-2" onClick={() => setJournal(b)} disabled={!b.service.expediteur}>📜 Envois</button>
                  <button type="button" className={b.service.expediteur ? "btn-outline btn-sm" : "btn-primary btn-sm"} onClick={() => ouvrir(b)}>
                    {b.service.expediteur ? "⚙️ Régler" : "Activer le service"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Configuration du service d'une boutique */}
      <Modal ouvert={!!config} titre={`Service SMS — ${config?.boutique.nom || ""}`} onFermer={() => setConfig(null)}>
        {config && (
          <form onSubmit={enregistrer} className="grid gap-4 sm:grid-cols-2">
            <Champ label="Expéditeur OVH *" aide="Nom déclaré (et validé) chez OVH pour cette boutique : 3 à 11 lettres ou chiffres, sans espace.">
              <input className="input font-mono uppercase" required minLength={3} maxLength={11} pattern="[A-Za-z0-9]{3,11}" value={config.expediteur}
                onChange={(e) => setConfig({ ...config, expediteur: e.target.value.replace(/[^A-Za-z0-9]/g, "") })} />
            </Champ>
            <Champ label="Service OVH dédié" aide="Laisser vide pour utiliser le compte SMS de la plateforme.">
              <input className="input font-mono" maxLength={60} value={config.service_ovh} placeholder="ex. sms-ab12345-1"
                onChange={(e) => setConfig({ ...config, service_ovh: e.target.value })} />
            </Champ>
            <Champ label="Prix d'un SMS facturé (FCFA)" aide="Un long message compte plusieurs SMS (160 caractères, 70 avec certains accents).">
              <input className="input" type="number" min={0} max={1000} required value={config.prix_sms} onChange={(e) => setConfig({ ...config, prix_sms: e.target.value })} />
            </Champ>
            <div className="space-y-2 self-end">
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-primary" checked={config.notifications_auto}
                onChange={(e) => setConfig({ ...config, notifications_auto: e.target.checked })} /> SMS automatiques aux clients (commandes, réparations)</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-primary" checked={config.actif}
                onChange={(e) => setConfig({ ...config, actif: e.target.checked })} /> Service activé</label>
            </div>
            <div className="flex justify-end gap-2 sm:col-span-2">
              <button type="button" className="btn-outline" onClick={() => setConfig(null)}>Annuler</button>
              <button className="btn-primary">Enregistrer</button>
            </div>
          </form>
        )}
      </Modal>

      {/* Envois de la boutique, regroupés par contact */}
      <Modal ouvert={!!journal} titre={`Envois SMS — ${journal?.nom || ""}`} onFermer={() => setJournal(null)} large>
        {journal && <JournalContacts base={`/plateforme/sms/boutiques/${journal.id}/contacts`} />}
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------------------
// Factures : génération pour une période, paiement reçu
// ---------------------------------------------------------------------------
function Factures({ onMaj }) {
  const toast = useToast();
  const [factures, setFactures] = useState(null);
  const [statut, setStatut] = useState("");
  const [periode, setPeriode] = useState({ debut: `${aujourdhui().slice(0, 8)}01`, fin: aujourdhui() });
  const [paiement, setPaiement] = useState(null); // { facture, mode, reference }

  const charger = useCallback(() => {
    apiClient.get("/plateforme/sms/factures", { params: { statut } }).then(({ data }) => setFactures(data)).catch(() => setFactures([]));
  }, [statut]);
  useEffect(() => { charger(); }, [charger]);

  // Factures de toutes les boutiques pour la période choisie (SMS pas encore facturés)
  async function generer() {
    if (!window.confirm(`Facturer les SMS envoyés du ${date(periode.debut)} au ${date(periode.fin)} pour toutes les boutiques ?`)) return;
    try {
      const { data } = await apiClient.post("/plateforme/sms/factures/generer", periode);
      toast.succes(data.length ? `${data.length} facture(s) créée(s)` : "Aucun SMS à facturer sur cette période");
      onMaj();
    } catch (err) {
      toast.erreur(messageErreur(err, "Facturation impossible"));
    }
  }

  async function enregistrerPaiement(e) {
    e.preventDefault();
    try {
      const { data } = await apiClient.post(`/plateforme/sms/factures/${paiement.facture.id}/paiements`,
        { mode: paiement.mode, reference: paiement.reference.trim() });
      toast.succes(data.service_retabli ? "Facture payée — service SMS rétabli" : "Facture payée");
      setPaiement(null);
      onMaj();
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible"));
    }
  }

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-end gap-3">
        <Champ label="Du"><input className="input" type="date" value={periode.debut} onChange={(e) => setPeriode({ ...periode, debut: e.target.value })} /></Champ>
        <Champ label="Au"><input className="input" type="date" value={periode.fin} onChange={(e) => setPeriode({ ...periode, fin: e.target.value })} /></Champ>
        <button type="button" className="btn-primary" onClick={generer}>🧾 Facturer cette période</button>
        <p className="text-xs text-gray-500">Automatique le 1er de chaque mois pour le mois écoulé. Un SMS n'est jamais facturé deux fois.</p>
      </div>
      <select className="input max-w-xs" value={statut} onChange={(e) => setStatut(e.target.value)} aria-label="Filtrer les factures">
        <option value="">Toutes les factures</option><option value="A_PAYER">À payer</option><option value="PAYEE">Payées</option>
      </select>
      {!factures ? <Chargement /> : (
        <div className="card overflow-x-auto p-0">
          <table className="table min-w-[820px]">
            <thead><tr><th>N°</th><th>Boutique</th><th>Période</th><th className="text-right">SMS</th><th className="text-right">Montant</th><th>Échéance</th><th>Statut</th><th /></tr></thead>
            <tbody>
              {factures.map((f) => (
                <tr key={f.id}>
                  <td className="font-mono text-xs">{f.numero}</td>
                  <td>{f.boutique_nom}</td>
                  <td className="whitespace-nowrap">{date(f.debut)} → {date(f.fin)}</td>
                  <td className="text-right">{f.nb_sms} × {fcfa(f.prix_sms)}</td>
                  <td className="text-right font-semibold">{fcfa(f.montant)}</td>
                  <td className="whitespace-nowrap">{date(f.echeance)}{f.jours_retard > 0 && <span className="block text-xs font-semibold text-red-600">{f.jours_retard} j de retard</span>}</td>
                  <td>{f.statut === "PAYEE"
                    ? <span className="badge bg-green-100 text-green-800">Payée{f.paiement ? ` (${MODES_ABONNEMENT[f.paiement.mode] || f.paiement.mode})` : ""}</span>
                    : <span className="badge bg-amber-100 text-amber-800">À payer</span>}</td>
                  <td>{f.statut === "A_PAYER" && <button type="button" className="btn-outline btn-sm" onClick={() => setPaiement({ facture: f, mode: "MOBILE_MONEY", reference: "" })}>💵 Paiement reçu</button>}</td>
                </tr>
              ))}
              {factures.length === 0 && <tr><td colSpan={8} className="text-center text-gray-500">Aucune facture.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      <Modal ouvert={!!paiement} titre={`Paiement de la facture ${paiement?.facture.numero || ""}`} onFermer={() => setPaiement(null)}>
        {paiement && (
          <form onSubmit={enregistrerPaiement} className="space-y-4">
            <p className="text-sm text-gray-600">{paiement.facture.boutique_nom} — <b>{fcfa(paiement.facture.montant)}</b></p>
            <Champ label="Mode">
              <select className="input" value={paiement.mode} onChange={(e) => setPaiement({ ...paiement, mode: e.target.value })}>
                {Object.entries(MODES_ABONNEMENT).filter(([c]) => c !== "PAWAPAY").map(([c, l]) => <option key={c} value={c}>{l}</option>)}
              </select>
            </Champ>
            <Champ label="Référence"><input className="input" maxLength={120} value={paiement.reference} onChange={(e) => setPaiement({ ...paiement, reference: e.target.value })} /></Champ>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-outline" onClick={() => setPaiement(null)}>Annuler</button>
              <button className="btn-primary">Enregistrer</button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Retards : suspension du service SMS des boutiques choisies
// ---------------------------------------------------------------------------
function Retards({ onMaj }) {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null);
  const [selection, setSelection] = useState([]);

  useEffect(() => {
    apiClient.get("/plateforme/sms/retards").then(({ data }) => setDonnees(data)).catch(() => setDonnees({ boutiques: [], total_du: 0 }));
  }, []);

  async function agir(action, ids) {
    const texte = action === "suspendre"
      ? `Suspendre le service SMS de ${ids.length} boutique(s) ? Elles ne pourront plus envoyer de SMS ; le reste de leur boutique continue de fonctionner.`
      : "Rétablir le service SMS sans paiement ?";
    if (!window.confirm(texte)) return;
    try {
      await apiClient.post(`/plateforme/sms/${action}`, { boutique_ids: ids });
      toast.succes(action === "suspendre" ? "Service SMS suspendu" : "Service SMS rétabli");
      setSelection([]);
      onMaj();
    } catch (err) {
      toast.erreur(messageErreur(err, "Action impossible"));
    }
  }

  if (!donnees) return <Chargement />;
  if (!donnees.boutiques.length) return <div className="card text-center text-gray-600">✅ Aucune facture SMS en retard.</div>;
  const basculer = (id) => setSelection((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="card p-3 font-bold">Total dû : {fcfa(donnees.total_du)}</p>
        <button type="button" className="btn-primary btn-sm bg-red-600 hover:bg-red-700" disabled={!selection.length} onClick={() => agir("suspendre", selection)}>
          🔇 Suspendre le service SMS des {selection.length || ""} boutique(s) sélectionnée(s)
        </button>
      </div>
      <div className="card divide-y divide-gray-100 p-0">
        {donnees.boutiques.map((g) => {
          const suspendu = g.service.statut === "SUSPENDU";
          return (
            <div key={g.boutique_id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <input type="checkbox" className="h-5 w-5 accent-primary" aria-label={`Sélectionner ${g.boutique_nom}`} disabled={suspendu}
                checked={selection.includes(g.boutique_id)} onChange={() => basculer(g.boutique_id)} />
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{g.boutique_nom} <span className="font-mono text-xs text-gray-500">{g.code_marchand}</span></p>
                <p className="text-xs text-gray-500">{g.factures.length} facture(s) : {g.factures.map((f) => f.numero).join(", ")}</p>
                <div className="mt-1"><BadgeService service={g.service} /></div>
              </div>
              <div className="text-right">
                <p className="text-lg font-extrabold text-red-600">{g.jours_retard} j de retard</p>
                <p className="text-sm font-semibold">{fcfa(g.montant_du)}</p>
              </div>
              {suspendu && <button type="button" className="btn-outline btn-sm text-green-700" onClick={() => agir("reactiver", [g.boutique_id])}>Rétablir</button>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
