import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { aujourdhui, date, dateHeure, montant } from "@/lib/format";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { Champ, EnTetePlateforme } from "./_plateforme/composants";
import { MODES_ABONNEMENT, STATUTS_ABONNEMENT } from "./_plateforme/outils";
import ServiceSms from "./_plateforme/ServiceSms";

// Onglets de la page (gardés dans l'adresse : ?onglet=...)
const ONGLETS = [
  ["retards", "⏰ Retards"], ["boutiques", "🏪 Toutes les boutiques"], ["paiements", "💵 Paiements reçus"],
  ["formules", "📋 Formules"], ["rappels", "🔔 Rappels"], ["sms", "📱 Service SMS"],
  ["parrainages", "🤝 Parrainages"],
];

// Montant en FCFA
const fcfa = (v) => `${montant(v || 0)} FCFA`;

// Badge du statut d'abonnement
export function BadgeAbonnement({ statut }) {
  const s = STATUTS_ABONNEMENT[statut] || { libelle: statut, classe: "bg-gray-100" };
  return <span className={`badge ${s.classe}`}>{s.libelle}</span>;
}

// Administration des abonnements (super-administrateur) :
//  - RETARDS : boutiques dont l'échéance est dépassée, jours de retard et montant
//    attendu ; on coche celles dont on suspend l'accès ;
//  - toutes les boutiques : essai, échéance, saisie d'un paiement reçu, correction ;
//  - paiements reçus sur une période ; formules (durée, prix) ; journal des rappels.
export default function Abonnements() {
  const [params, setParams] = useSearchParams();
  const onglet = ONGLETS.some(([c]) => c === params.get("onglet")) ? params.get("onglet") : "retards";
  const [formules, setFormules] = useState([]);
  const [paiementPour, setPaiementPour] = useState(null); // boutique pour laquelle on saisit un paiement
  const [version, setVersion] = useState(0); // incrémentée pour recharger l'onglet affiché

  // Formules (utilisées par plusieurs onglets)
  const chargerFormules = useCallback(() => {
    apiClient.get("/plateforme/abonnements/formules").then(({ data }) => setFormules(data)).catch(() => {});
  }, []);
  useEffect(() => { chargerFormules(); }, [chargerFormules]);

  const recharger = () => setVersion((v) => v + 1);

  return (
    <div className="min-h-screen bg-gray-50">
      <EnTetePlateforme />
      <main className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
        <div>
          <h1 className="text-2xl font-extrabold">Abonnements des boutiques</h1>
          <p className="text-sm text-gray-500">14 jours d'essai complet à la création, puis abonnement selon la formule choisie.
            Rappels WhatsApp 3 jours avant l'échéance, puis chaque jour tant qu'elle n'est pas réglée.</p>
        </div>

        {/* Onglets */}
        <div className="-mx-1 flex gap-1 overflow-x-auto border-b border-gray-200 px-1">
          {ONGLETS.map(([code, libelle]) => (
            <button key={code} type="button" onClick={() => setParams({ onglet: code }, { replace: true })}
              className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-semibold ${onglet === code ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-800"}`}>
              {libelle}
            </button>
          ))}
        </div>

        {onglet === "retards" && <Retards key={version} onPaiement={setPaiementPour} />}
        {onglet === "boutiques" && <Boutiques key={version} formules={formules} onPaiement={setPaiementPour} />}
        {onglet === "paiements" && <Paiements key={version} />}
        {onglet === "formules" && <Formules formules={formules} onMaj={chargerFormules} />}
        {onglet === "rappels" && <Rappels />}
        {onglet === "sms" && <ServiceSms />}
        {onglet === "parrainages" && <Parrainages />}
      </main>

      <SaisiePaiement boutique={paiementPour} formules={formules} onFermer={() => setPaiementPour(null)}
        onEnregistre={() => { setPaiementPour(null); recharger(); }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Retards : sélection des boutiques à suspendre
// ---------------------------------------------------------------------------
function Retards({ onPaiement }) {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null);
  const [selection, setSelection] = useState([]);
  const [occupe, setOccupe] = useState(false);

  const charger = useCallback(() => {
    apiClient.get("/plateforme/abonnements/retards").then(({ data }) => { setDonnees(data); setSelection([]); })
      .catch((err) => toast.erreur(messageErreur(err, "Liste indisponible")));
  }, [toast]);
  useEffect(() => { charger(); }, [charger]);

  if (!donnees) return <Chargement />;
  const aTraiter = donnees.boutiques.filter((b) => b.abonnement.statut === "EN_RETARD");
  const basculer = (id) => setSelection((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const toutCocher = () => setSelection(selection.length === aTraiter.length ? [] : aTraiter.map((b) => b.id));

  // Suspension (ou réactivation) des boutiques cochées
  async function agir(action, ids) {
    const texte = action === "suspendre"
      ? `Suspendre l'accès de ${ids.length} boutique(s) ? Leur back-office et leur vitrine seront fermés ; le DG pourra toujours payer depuis sa page Abonnement.`
      : "Rendre l'accès à cette boutique sans paiement ?";
    if (!window.confirm(texte)) return;
    setOccupe(true);
    try {
      const { data } = await apiClient.post(`/plateforme/abonnements/${action}`, { boutique_ids: ids });
      toast.succes(action === "suspendre" ? `${data.suspendues} boutique(s) suspendue(s)` : "Accès rendu");
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Action impossible"));
    } finally {
      setOccupe(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Chiffres clés */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="card p-3"><p className="text-xs text-gray-500">Boutiques en retard</p><p className="text-2xl font-extrabold">{donnees.boutiques.length}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">Encore ouvertes (à traiter)</p><p className="text-2xl font-extrabold text-red-600">{donnees.nb_a_traiter}</p></div>
        <div className="card col-span-2 p-3 sm:col-span-1"><p className="text-xs text-gray-500">Montant total attendu</p><p className="text-2xl font-extrabold">{fcfa(donnees.total_attendu)}</p></div>
      </div>

      {donnees.boutiques.length === 0 ? (
        <div className="card text-center text-gray-600">✅ Aucune boutique en retard de paiement.</div>
      ) : (
        <>
          {/* Barre d'action sur la sélection */}
          <div className="flex flex-wrap items-center gap-3">
            {aTraiter.length > 0 && (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="h-4 w-4 accent-primary" checked={selection.length > 0 && selection.length === aTraiter.length} onChange={toutCocher} />
                Tout sélectionner
              </label>
            )}
            <button type="button" className="btn-primary btn-sm bg-red-600 hover:bg-red-700" disabled={!selection.length || occupe}
              onClick={() => agir("suspendre", selection)}>
              🔒 Suspendre l'accès des {selection.length || ""} boutique(s) sélectionnée(s)
            </button>
          </div>

          {/* Une ligne par boutique en retard */}
          <div className="card divide-y divide-gray-100 p-0">
            {donnees.boutiques.map((b) => {
              const a = b.abonnement;
              const suspendue = a.statut === "SUSPENDU";
              return (
                <div key={b.id} className={`flex flex-wrap items-center gap-3 px-4 py-3 ${suspendue ? "bg-gray-50" : ""}`}>
                  <input type="checkbox" className="h-5 w-5 accent-primary" aria-label={`Sélectionner ${b.nom}`}
                    disabled={suspendue} checked={selection.includes(b.id)} onChange={() => basculer(b.id)} />
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">{b.nom} <span className="font-mono text-xs text-gray-500">{b.code_marchand}</span></p>
                    <p className="text-xs text-gray-500">
                      {a.en_essai ? "Fin d'essai" : "Échéance"} le {date(a.echeance)} · {a.formule_libelle} · DG {b.dg_nom || "—"} {b.telephone && `· ${b.telephone}`}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <BadgeAbonnement statut={a.statut} />
                      {suspendue && a.motif_suspension === "MANUEL" && <span className="badge bg-gray-100 text-gray-600">suspension manuelle</span>}
                    </div>
                  </div>
                  {/* Retard et montant attendu */}
                  <div className="text-right">
                    <p className="text-lg font-extrabold text-red-600">{a.jours_retard} j de retard</p>
                    <p className="text-sm font-semibold">{fcfa(a.montant_attendu)}</p>
                  </div>
                  <div className="flex w-full gap-2 sm:w-auto">
                    <button type="button" className="btn-outline btn-sm flex-1" onClick={() => onPaiement(b)}>💵 Paiement reçu</button>
                    {suspendue && <button type="button" className="btn-outline btn-sm flex-1 text-green-700" disabled={occupe} onClick={() => agir("reactiver", [b.id])}>Rendre l'accès</button>}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Toutes les boutiques : situation, paiement reçu, correction de l'échéance
// ---------------------------------------------------------------------------
function Boutiques({ formules, onPaiement }) {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null);
  const [filtre, setFiltre] = useState("");
  const [q, setQ] = useState("");
  const [ajustement, setAjustement] = useState(null); // { boutique, echeance, formule }

  const charger = useCallback(() => {
    apiClient.get("/plateforme/abonnements").then(({ data }) => setDonnees(data))
      .catch((err) => toast.erreur(messageErreur(err, "Liste indisponible")));
  }, [toast]);
  useEffect(() => { charger(); }, [charger]);

  // Enregistrement d'une correction (échéance / formule par défaut)
  async function ajuster(e) {
    e.preventDefault();
    try {
      await apiClient.patch(`/plateforme/abonnements/boutiques/${ajustement.boutique.id}`,
        { echeance: ajustement.echeance, formule: ajustement.formule });
      toast.succes("Abonnement corrigé");
      setAjustement(null);
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Correction impossible"));
    }
  }

  if (!donnees) return <Chargement />;
  const texte = q.trim().toLowerCase();
  const lignes = donnees.boutiques.filter((b) => (!filtre || b.abonnement.statut === filtre)
    && (!texte || [b.nom, b.code_marchand, b.ville].some((v) => (v || "").toLowerCase().includes(texte))));

  return (
    <div className="space-y-4">
      {/* Filtres par statut, avec leur nombre */}
      <div className="flex flex-wrap items-center gap-2">
        <input className="input max-w-xs" placeholder="Nom, code, ville…" value={q} onChange={(e) => setQ(e.target.value)} />
        {[["", "Toutes", donnees.boutiques.length], ...Object.entries(STATUTS_ABONNEMENT).map(([c, s]) => [c, s.libelle, donnees.compte[c] || 0])]
          .map(([code, libelle, n]) => (
            <button key={code} type="button" onClick={() => setFiltre(code)}
              className={`rounded-full px-3 py-1 text-sm font-semibold ${filtre === code ? "bg-primary text-white" : "bg-white text-gray-600 ring-1 ring-gray-200"}`}>
              {libelle} ({n})
            </button>
          ))}
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="table min-w-[760px]">
          <thead><tr><th>Boutique</th><th>Statut</th><th>Formule</th><th>Échéance</th><th className="text-right">Prochain montant</th><th /></tr></thead>
          <tbody>
            {lignes.map((b) => {
              const a = b.abonnement;
              return (
                <tr key={b.id}>
                  <td><p className="font-semibold">{b.nom}</p><p className="font-mono text-xs text-gray-500">{b.code_marchand}</p></td>
                  <td><BadgeAbonnement statut={a.statut} /></td>
                  <td>{a.formule_libelle}</td>
                  <td className="whitespace-nowrap">
                    {date(a.echeance)}
                    <span className={`block text-xs ${a.jours_retard ? "font-semibold text-red-600" : "text-gray-500"}`}>
                      {a.jours_retard ? `${a.jours_retard} j de retard` : `${a.jours_restants} j restant(s)`}
                    </span>
                  </td>
                  <td className="text-right">{fcfa(a.montant_attendu)}</td>
                  <td className="whitespace-nowrap text-right">
                    <button type="button" className="btn-outline btn-sm mr-2" onClick={() => onPaiement(b)}>💵 Paiement</button>
                    <button type="button" className="btn-outline btn-sm" title="Corriger l'échéance ou la formule"
                      onClick={() => setAjustement({ boutique: b, echeance: a.echeance, formule: a.formule })}>✏️</button>
                  </td>
                </tr>
              );
            })}
            {lignes.length === 0 && <tr><td colSpan={6} className="text-center text-gray-500">Aucune boutique.</td></tr>}
          </tbody>
        </table>
      </div>

      {/* Correction manuelle (ex. prolonger un essai) */}
      <Modal ouvert={!!ajustement} titre={`Corriger l'abonnement — ${ajustement?.boutique.nom || ""}`} onFermer={() => setAjustement(null)}>
        {ajustement && (
          <form onSubmit={ajuster} className="space-y-4">
            <Champ label="Échéance (dernier jour couvert)" aide="Par exemple pour prolonger un essai ou offrir des jours.">
              <input className="input" type="date" required value={ajustement.echeance} onChange={(e) => setAjustement({ ...ajustement, echeance: e.target.value })} />
            </Champ>
            <Champ label="Formule par défaut" aide="Sert à calculer le montant attendu et les rappels.">
              <select className="input" value={ajustement.formule} onChange={(e) => setAjustement({ ...ajustement, formule: e.target.value })}>
                {formules.map((f) => <option key={f.code} value={f.code}>{f.libelle} — {fcfa(f.montant)}</option>)}
              </select>
            </Champ>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-outline" onClick={() => setAjustement(null)}>Annuler</button>
              <button className="btn-primary">Enregistrer</button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Saisie d'un paiement reçu hors du site (prolonge l'abonnement)
// ---------------------------------------------------------------------------
function SaisiePaiement({ boutique, formules, onFermer, onEnregistre }) {
  const toast = useToast();
  const [f, setF] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  // Valeurs initiales à chaque ouverture : formule actuelle de la boutique, prix de la formule
  useEffect(() => {
    if (!boutique) return;
    const actuelle = formules.find((x) => x.code === boutique.abonnement.formule) || formules[0];
    setF({ formule: actuelle?.code || "", montant: actuelle?.montant ?? "", mode: "MOBILE_MONEY", reference: "", date: aujourdhui(),
      bonus: false });
  }, [boutique, formules]);

  if (!boutique || !f) return null;
  const choisie = formules.find((x) => x.code === f.formule);

  async function enregistrer(e) {
    e.preventDefault();
    setEnvoi(true);
    try {
      const { data } = await apiClient.post(`/plateforme/abonnements/boutiques/${boutique.id}/paiements`, {
        formule: f.formule, mode: f.mode, reference: f.reference.trim(), date: f.date,
        // Bonus déduits : le serveur calcule le montant restant dû (prix - bonus)
        ...(f.bonus ? { utiliser_bonus: true } : { montant: Number(f.montant) || 0 }),
      });
      toast.succes(`Paiement enregistré : nouvelle échéance le ${date(data.nouvelle_echeance)}${data.reactivee ? " — accès rendu" : ""}`);
      onEnregistre();
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Modal ouvert titre={`Paiement reçu — ${boutique.nom}`} onFermer={onFermer}>
      <form onSubmit={enregistrer} className="space-y-4">
        <p className="rounded-xl bg-gray-50 p-3 text-sm text-gray-600">
          Échéance actuelle : <b>{date(boutique.abonnement.echeance)}</b>
          {boutique.abonnement.jours_retard > 0 && <> · <span className="text-red-600">{boutique.abonnement.jours_retard} j de retard</span></>}.
          {" "}La nouvelle échéance est calculée selon la durée de la formule.
          {boutique.abonnement.statut === "SUSPENDU" && boutique.abonnement.motif_suspension === "IMPAYE" && " L'accès sera rendu automatiquement."}
        </p>
        <Champ label="Formule payée">
          <select className="input" value={f.formule} onChange={(e) => {
            const x = formules.find((y) => y.code === e.target.value);
            setF({ ...f, formule: e.target.value, montant: x?.montant ?? f.montant });
          }}>
            {formules.map((x) => <option key={x.code} value={x.code}>{x.libelle} ({x.mois} mois) — {fcfa(x.montant)}</option>)}
          </select>
        </Champ>
        <div className="grid gap-4 sm:grid-cols-2">
          <Champ label="Montant reçu (FCFA)" aide={choisie && Number(f.montant) !== choisie.montant ? `Prix de la formule : ${fcfa(choisie.montant)}` : ""}>
            <input className="input" type="number" min={0} required value={f.montant} onChange={(e) => setF({ ...f, montant: e.target.value })} />
          </Champ>
          <Champ label="Date du paiement"><input className="input" type="date" required value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Champ>
          <Champ label="Mode">
            <select className="input" value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value })}>
              {Object.entries(MODES_ABONNEMENT).filter(([c]) => c !== "PAWAPAY").map(([c, l]) => <option key={c} value={c}>{l}</option>)}
            </select>
          </Champ>
          <Champ label="Référence"><input className="input" maxLength={120} value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} placeholder="n° de transaction, reçu…" /></Champ>
        </div>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={f.bonus} onChange={(e) => setF({ ...f, bonus: e.target.checked })} />
          <span>Déduire les bonus de parrainage de la boutique <span className="block text-xs text-gray-500">Le montant dû est alors calculé automatiquement (prix de la formule moins les bonus disponibles).</span></span>
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-outline" onClick={onFermer}>Annuler</button>
          <button className="btn-primary" disabled={envoi}>{envoi ? "Enregistrement…" : "Enregistrer le paiement"}</button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Paiements reçus sur une période
// ---------------------------------------------------------------------------
function Paiements() {
  const [periode, setPeriode] = useState({ debut: `${aujourdhui().slice(0, 8)}01`, fin: aujourdhui() });
  const [donnees, setDonnees] = useState(null);

  useEffect(() => {
    apiClient.get("/plateforme/abonnements/paiements", { params: periode }).then(({ data }) => setDonnees(data)).catch(() => {});
  }, [periode]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Champ label="Du"><input className="input" type="date" value={periode.debut} onChange={(e) => setPeriode({ ...periode, debut: e.target.value })} /></Champ>
        <Champ label="Au"><input className="input" type="date" value={periode.fin} onChange={(e) => setPeriode({ ...periode, fin: e.target.value })} /></Champ>
        {donnees && <p className="card p-3 text-lg font-extrabold">Total : {fcfa(donnees.total)} <span className="text-sm font-normal text-gray-500">({donnees.paiements.length} paiement(s))</span></p>}
      </div>
      {!donnees ? <Chargement /> : (
        <div className="card overflow-x-auto p-0">
          <table className="table min-w-[720px]">
            <thead><tr><th>Date</th><th>Boutique</th><th>Formule</th><th>Mode</th><th>Référence</th><th className="text-right">Montant</th><th>Nouvelle échéance</th></tr></thead>
            <tbody>
              {donnees.paiements.map((p) => (
                <tr key={p.id}>
                  <td className="whitespace-nowrap">{date(p.date)}</td>
                  <td>{p.boutique_nom} <span className="font-mono text-xs text-gray-500">{p.code_marchand}</span></td>
                  <td>{p.formule_libelle}</td>
                  <td>{MODES_ABONNEMENT[p.mode] || p.mode}</td>
                  <td className="text-xs text-gray-600">{p.reference || "—"}{p.saisi_par && <span className="block">par {p.saisi_par}</span>}</td>
                  <td className="text-right font-semibold">{fcfa(p.montant)}{p.bonus_deduit > 0 && <span className="block text-xs font-normal text-green-700">+ {fcfa(p.bonus_deduit)} de bonus</span>}</td>
                  <td className="whitespace-nowrap">{date(p.nouvelle_echeance)}{p.reactivee && <span className="block text-xs text-green-700">accès rendu</span>}</td>
                </tr>
              ))}
              {donnees.paiements.length === 0 && <tr><td colSpan={7} className="text-center text-gray-500">Aucun paiement sur cette période.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formules : libellé, durée en mois, prix
// ---------------------------------------------------------------------------
function Formules({ formules, onMaj }) {
  const toast = useToast();
  const [edition, setEdition] = useState(null); // formule modifiée ou nouvelle ({ code: null })

  async function enregistrer(e) {
    e.preventDefault();
    const corps = { libelle: edition.libelle.trim(), mois: Number(edition.mois), montant: Number(edition.montant) || 0,
      actif: edition.actif, ordre: Number(edition.ordre) || 0 };
    try {
      if (edition.code) await apiClient.put(`/plateforme/abonnements/formules/${edition.code}`, corps);
      else await apiClient.post("/plateforme/abonnements/formules", corps);
      toast.succes("Formule enregistrée");
      setEdition(null);
      onMaj();
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez le libellé, la durée (1 à 60 mois) et le prix"));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-gray-500">Un nouveau prix s'applique aux prochains paiements. Les formules inactives ne sont plus proposées aux boutiques.</p>
        <button type="button" className="btn-primary btn-sm" onClick={() => setEdition({ code: null, libelle: "", mois: 1, montant: 0, actif: true, ordre: formules.length + 1 })}>+ Nouvelle formule</button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {formules.map((f) => (
          <div key={f.code} className={`card ${f.actif ? "" : "opacity-60"}`}>
            <p className="font-bold">{f.libelle}</p>
            <p className="text-2xl font-extrabold text-primary">{fcfa(f.montant)}</p>
            <p className="text-sm text-gray-500">{f.mois} mois{f.mois > 1 ? ` · ${fcfa(Math.round(f.montant / f.mois))} / mois` : ""}</p>
            {!f.actif && <span className="badge mt-1 bg-gray-100 text-gray-600">inactive</span>}
            <button type="button" className="btn-outline btn-sm mt-3 w-full" onClick={() => setEdition({ ...f })}>✏️ Modifier</button>
          </div>
        ))}
      </div>
      <Modal ouvert={!!edition} titre={edition?.code ? "Modifier la formule" : "Nouvelle formule"} onFermer={() => setEdition(null)}>
        {edition && (
          <form onSubmit={enregistrer} className="grid gap-4 sm:grid-cols-2">
            <Champ label="Libellé" className="sm:col-span-2"><input className="input" required minLength={2} maxLength={60} value={edition.libelle} onChange={(e) => setEdition({ ...edition, libelle: e.target.value })} placeholder="ex. 1 an" /></Champ>
            <Champ label="Durée (mois)" aide="L'échéance est repoussée d'autant de mois."><input className="input" type="number" min={1} max={60} required value={edition.mois} onChange={(e) => setEdition({ ...edition, mois: e.target.value })} /></Champ>
            <Champ label="Prix (FCFA)"><input className="input" type="number" min={0} required value={edition.montant} onChange={(e) => setEdition({ ...edition, montant: e.target.value })} /></Champ>
            <Champ label="Ordre d'affichage"><input className="input" type="number" value={edition.ordre} onChange={(e) => setEdition({ ...edition, ordre: e.target.value })} /></Champ>
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <input type="checkbox" className="h-4 w-4 accent-primary" checked={edition.actif} onChange={(e) => setEdition({ ...edition, actif: e.target.checked })} />
              Proposée aux boutiques
            </label>
            <div className="flex justify-end gap-2 sm:col-span-2">
              <button type="button" className="btn-outline" onClick={() => setEdition(null)}>Annuler</button>
              <button className="btn-primary">Enregistrer</button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Journal des rappels (WhatsApp, SMS de repli, e-mail)
// ---------------------------------------------------------------------------
const ICONES_ENVOI = { ENVOYE: "✅", ECHEC: "❌", NON_CONFIGURE: "⚙️", NON_ENVOYE: "—" };

function Rappels() {
  const toast = useToast();
  const [lignes, setLignes] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  const charger = useCallback(() => {
    apiClient.get("/plateforme/abonnements/rappels").then(({ data }) => setLignes(data)).catch(() => setLignes([]));
  }, []);
  useEffect(() => { charger(); }, [charger]);

  async function envoyerMaintenant() {
    setEnvoi(true);
    try {
      const { data } = await apiClient.post("/plateforme/abonnements/rappels/envoyer", null, { timeout: 120000 });
      toast.succes(`${data.envoyes.length} rappel(s) envoyé(s)`);
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-gray-500">Envoi automatique chaque jour à 9h (un rappel par boutique et par jour). ✅ envoyé · ❌ échec · ⚙️ non configuré.</p>
        <button type="button" className="btn-outline btn-sm" disabled={envoi} onClick={envoyerMaintenant}>{envoi ? "Envoi…" : "🔔 Envoyer les rappels du jour maintenant"}</button>
      </div>
      {!lignes ? <Chargement /> : (
        <div className="card overflow-x-auto p-0">
          <table className="table min-w-[720px]">
            <thead><tr><th>Date</th><th>Boutique</th><th>Situation</th><th className="text-right">Montant</th><th>WhatsApp</th><th>SMS</th><th>E-mail</th></tr></thead>
            <tbody>
              {lignes.map((r) => (
                <tr key={r.id}>
                  <td className="whitespace-nowrap">{dateHeure(r.date)}</td>
                  <td>{r.boutique_nom} <span className="font-mono text-xs text-gray-500">{r.code_marchand}</span></td>
                  <td>{r.jours_retard ? <span className="text-red-600">{r.jours_retard} j de retard</span> : `échéance dans ${r.jours_restants} j`}</td>
                  <td className="text-right">{fcfa(r.montant)}</td>
                  <td title={r.whatsapp_erreur}>{ICONES_ENVOI[r.whatsapp] || r.whatsapp}</td>
                  <td title={r.sms_erreur}>{ICONES_ENVOI[r.sms] || r.sms}</td>
                  <td title={r.email_erreur}>{ICONES_ENVOI[r.email] || r.email}</td>
                </tr>
              ))}
              {lignes.length === 0 && <tr><td colSpan={7} className="text-center text-gray-500">Aucun rappel envoyé pour l'instant.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Parrainages entre boutiques (bonus validé à l'ouverture de la boutique filleule)
// ---------------------------------------------------------------------------
const STATUTS_PARRAINAGE = {
  EN_ATTENTE: ["En attente d'ouverture", "bg-amber-100 text-amber-800"],
  VALIDE: ["Bonus validé", "bg-green-100 text-green-800"],
  ANNULE: ["Annulé", "bg-gray-100 text-gray-600"],
};

function Parrainages() {
  const [liste, setListe] = useState(null);
  useEffect(() => {
    apiClient.get("/plateforme/parrainages").then(({ data }) => setListe(data)).catch(() => setListe([]));
  }, []);
  if (!liste) return <Chargement />;
  const valides = liste.filter((p) => p.statut === "VALIDE");
  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        Une boutique filleule est créée <b>en attente</b> quand l'invité accepte l'invitation. Le bonus du parrain est
        validé quand vous <b>validez</b> la boutique filleule (onglet Plateforme). Bonus validés : <b>{fcfa(valides.reduce((t, p) => t + p.bonus, 0))}</b>.
      </p>
      <div className="card overflow-x-auto p-0">
        <table className="table min-w-[720px]">
          <thead><tr><th>Invitation acceptée</th><th>Parrain</th><th>Boutique filleule</th><th>Statut</th><th className="text-right">Bonus</th></tr></thead>
          <tbody>
            {liste.length === 0 && <tr><td colSpan={5} className="text-center text-gray-500">Aucun parrainage pour le moment.</td></tr>}
            {liste.map((p) => {
              const [libelle, classe] = STATUTS_PARRAINAGE[p.statut] || [p.statut, ""];
              return (
                <tr key={p.id}>
                  <td className="whitespace-nowrap">{dateHeure(p.invitation_acceptee_le)}</td>
                  <td>{p.parrain_nom} <span className="font-mono text-xs text-gray-500">{p.parrain_code}</span></td>
                  <td>{p.filleul_nom} <span className="text-xs text-gray-500">{p.filleul_ville}</span></td>
                  <td><span className={`badge ${classe}`}>{libelle}</span>{p.valide_le && <span className="block text-xs text-gray-500">{dateHeure(p.valide_le)}</span>}</td>
                  <td className="text-right font-semibold">{fcfa(p.bonus)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
