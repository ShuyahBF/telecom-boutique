import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, dateHeure, montant, prix } from "@/lib/format";
import Chargement from "@/components/Chargement";
import EnTetePage from "@/components/EnTetePage";
import { useToast } from "@/components/Toast";

// Page « Caisse Aizenta » : situation de la caisse du logiciel Aizenta, reçue
// automatiquement de Loois (webhook, voir docs/caisse-aizenta.md).
// Toujours présente dans le menu ; visible du DG, du comptable et du secrétariat.

// Ouagadougou est à UTC+0 toute l'année : la date du jour est la date UTC.
function jourIso(decalageJours = 0) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + decalageJours);
  return d.toISOString().slice(0, 10);
}

// Périodes proposées (du / au au format AAAA-MM-JJ)
const PERIODES = {
  aujourdhui: { libelle: "Aujourd'hui", bornes: () => [jourIso(), jourIso()] },
  hier: { libelle: "Hier", bornes: () => [jourIso(-1), jourIso(-1)] },
  semaine: { libelle: "7 derniers jours", bornes: () => [jourIso(-6), jourIso()] },
  mois: { libelle: "Ce mois", bornes: () => [`${jourIso().slice(0, 8)}01`, jourIso()] },
  perso: { libelle: "Intervalle personnalisé", bornes: null },
};

const TYPES = {
  VENTE: "Vente", REGLEMENT: "Règlement", AVOIR: "Avoir", DEPENSE: "Dépense",
  VERSEMENT: "Versement", FOND_DE_CAISSE: "Fond de caisse", AUTRE: "Autre",
};
const PAR_PAGE = 50;

export default function CaisseAizenta() {
  const { boutique } = useAuth();
  const toast = useToast();
  const devise = boutique?.devise || "FCFA";

  // --- Période choisie ---
  const [choix, setChoix] = useState("aujourdhui");
  const [du, setDu] = useState(jourIso());
  const [au, setAu] = useState(jourIso());
  // --- Situation (totaux, ventilations) ---
  const [situation, setSituation] = useState(null);
  const [erreur, setErreur] = useState("");
  // --- Liste détaillée : filtres et page ---
  const [filtres, setFiltres] = useState({ type: "", mode: "", caissier: "", q: "" });
  const [page, setPage] = useState(1);
  const [liste, setListe] = useState(null);
  const [exportEnCours, setExportEnCours] = useState(false);

  // Choix d'une période prédéfinie : on recalcule « du » et « au »
  function choisir(cle) {
    setChoix(cle);
    if (PERIODES[cle].bornes) {
      const [d, a] = PERIODES[cle].bornes();
      setDu(d);
      setAu(a);
    }
    setPage(1);
  }

  // Chargement de la situation à chaque changement de période
  useEffect(() => {
    if (!du || !au || du > au) return;
    setErreur("");
    apiClient.get("/caisse-aizenta/situation", { params: { du, au } })
      .then(({ data }) => setSituation(data))
      .catch((err) => setErreur(messageErreur(err, "Impossible de charger la situation de caisse")));
  }, [du, au]);

  // Chargement de la liste détaillée (période + filtres + page)
  const chargerListe = useCallback(() => {
    if (!du || !au || du > au) return;
    apiClient.get("/caisse-aizenta/operations", { params: { du, au, ...filtres, page, par_page: PAR_PAGE } })
      .then(({ data }) => setListe(data))
      .catch(() => setListe(null));
  }, [du, au, filtres, page]);
  useEffect(() => { chargerListe(); }, [chargerListe]);

  // Export CSV (mêmes filtres que la liste)
  async function exporter() {
    setExportEnCours(true);
    try {
      const { data } = await apiClient.get("/caisse-aizenta/operations.csv", { params: { du, au, ...filtres }, responseType: "blob" });
      const url = URL.createObjectURL(data);
      const lien = document.createElement("a");
      lien.href = url;
      lien.download = `caisse_aizenta_${boutique?.code_marchand || ""}_${du}_${au}.csv`;
      document.body.appendChild(lien);
      lien.click();
      lien.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (err) {
      toast.erreur(messageErreur(err, "Export impossible"));
    } finally {
      setExportEnCours(false);
    }
  }

  const filtrer = (champ, valeur) => { setFiltres((f) => ({ ...f, [champ]: valeur })); setPage(1); };
  const nbPages = liste ? Math.max(1, Math.ceil(liste.total / PAR_PAGE)) : 1;

  return (
    <div className="space-y-6">
      <EnTetePage titre="Caisse Aizenta" sousTitre="Situation de caisse transmise automatiquement par Loois depuis votre logiciel Aizenta" />

      {/* ===== Choix de la période ===== */}
      <div className="card flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          {Object.entries(PERIODES).map(([cle, p]) => (
            <button key={cle} type="button" onClick={() => choisir(cle)}
              className={`btn-sm ${choix === cle ? "btn-primary" : "btn-outline"}`}>{p.libelle}</button>
          ))}
        </div>
        {choix === "perso" && (
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">Du<input type="date" className="input mt-1" value={du} max={au || undefined} onChange={(e) => { setDu(e.target.value); setPage(1); }} /></label>
            <label className="text-sm">Au<input type="date" className="input mt-1" value={au} min={du || undefined} onChange={(e) => { setAu(e.target.value); setPage(1); }} /></label>
            {du > au && <p className="text-sm text-red-600">La date de début doit précéder la date de fin.</p>}
          </div>
        )}
        <p className="text-sm text-gray-500">Période : {du === au ? `le ${date(du)}` : `du ${date(du)} au ${date(au)}`} (heure de Ouagadougou)</p>
      </div>

      {erreur && <p className="card text-red-600">{erreur}</p>}
      {!situation && !erreur && <Chargement />}

      {situation && (
        <>
          {/* ===== Dernière réception de Loois ===== */}
          <EtatReception situation={situation} />

          {!situation.a_des_donnees ? <AucuneDonnee situation={situation} /> : (
            <>
              {/* ===== Indicateurs ===== */}
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Tuile libelle="Total encaissé" valeur={prix(situation.total_encaisse, devise)} couleur="text-green-700" />
                <Tuile libelle="Sorties" valeur={prix(situation.total_sorties, devise)} couleur="text-red-600" />
                <Tuile libelle="Solde net" detail="entrées − sorties" valeur={prix(situation.solde_net, devise)} couleur={situation.solde_net < 0 ? "text-red-600" : "text-primary"} />
                <Tuile libelle="Opérations" valeur={montant(situation.nb_operations)}
                  detail={situation.fond_de_caisse ? `fond de caisse : ${prix(situation.fond_de_caisse, devise)}` : "sur la période"} />
              </div>

              {/* ===== Ventilations ===== */}
              <div className="grid gap-6 lg:grid-cols-3">
                <Ventilation titre="Par type" lignes={situation.par_type} devise={devise} />
                <Ventilation titre="Par mode de paiement" lignes={situation.par_mode} devise={devise} avecCodes />
                <Ventilation titre="Par caissier" lignes={situation.par_caissier} devise={devise} />
              </div>

              {/* ===== Arrêts de caisse (seulement s'il y en a) ===== */}
              {situation.arrets_caisse.length > 0 && <ArretsCaisse arrets={situation.arrets_caisse} devise={devise} />}

              {/* ===== Liste détaillée ===== */}
              <section className="card overflow-hidden p-0">
                <div className="flex flex-wrap items-end gap-2 border-b border-gray-100 p-4">
                  <h2 className="mr-auto font-bold">Opérations {liste ? <span className="text-sm font-normal text-gray-500">({liste.total} · {prix(liste.total_montant, devise)})</span> : null}</h2>
                  <input className="input w-full sm:w-48" placeholder="🔍 N°, référence, client…" value={filtres.q} onChange={(e) => filtrer("q", e.target.value)} />
                  <select className="input w-full bg-white sm:w-40" value={filtres.type} onChange={(e) => filtrer("type", e.target.value)} aria-label="Type">
                    <option value="">Tous les types</option>
                    {Object.entries(TYPES).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
                  </select>
                  <select className="input w-full bg-white sm:w-44" value={filtres.mode} onChange={(e) => filtrer("mode", e.target.value)} aria-label="Mode de paiement">
                    <option value="">Tous les modes</option>
                    {situation.par_mode.map((m) => <option key={m.libelle} value={m.libelle}>{m.libelle}</option>)}
                  </select>
                  <select className="input w-full bg-white sm:w-40" value={filtres.caissier} onChange={(e) => filtrer("caissier", e.target.value)} aria-label="Caissier">
                    <option value="">Tous les caissiers</option>
                    {situation.par_caissier.map((c) => <option key={c.libelle} value={c.libelle}>{c.libelle}</option>)}
                  </select>
                  <button type="button" className="btn-outline btn-sm" disabled={exportEnCours} onClick={exporter}>{exportEnCours ? "Export…" : "⬇️ Export CSV"}</button>
                </div>
                <ListeOperations liste={liste} devise={devise} />
                {liste && liste.total > PAR_PAGE && (
                  <div className="flex items-center justify-between gap-2 border-t border-gray-100 p-3 text-sm">
                    <button type="button" className="btn-outline btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Précédent</button>
                    <span>Page {page} / {nbPages}</span>
                    <button type="button" className="btn-outline btn-sm" disabled={page >= nbPages} onClick={() => setPage(page + 1)}>Suivant →</button>
                  </div>
                )}
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}

// Bandeau : date de la dernière réception de Loois, alerte au-delà de 24 h
function EtatReception({ situation }) {
  const derniere = situation.derniere_reception;
  if (!derniere && !situation.a_des_donnees) return null;
  return (
    <div className={`rounded-2xl border p-3 text-sm ${situation.alerte_reception ? "border-amber-300 bg-amber-50 text-amber-900" : "border-green-200 bg-green-50 text-green-900"}`}>
      {derniere
        ? <>Dernière réception de Loois : <b>{dateHeure(derniere.date)}</b> ({derniere.nb_operations} opération(s){derniere.base ? `, base ${derniere.base}` : ""}).</>
        : <>Aucune réception récente de Loois.</>}
      {situation.alerte_reception && <> ⚠️ Rien reçu depuis plus de 24 heures : vérifiez que Loois fonctionne sur le poste Aizenta.</>}
    </div>
  );
}

// Aucune donnée encore reçue : comment brancher Loois
function AucuneDonnee({ situation }) {
  return (
    <div className="card mx-auto max-w-2xl text-center">
      <p className="text-4xl">🧮</p>
      <h2 className="mt-2 text-lg font-bold">Aucune donnée de caisse reçue pour l'instant</h2>
      <p className="mt-2 text-gray-600">
        La caisse Aizenta s'affiche ici dès que <b>Loois</b> envoie ses données à adLyn. Pour le configurer, il faut :
      </p>
      <ol className="mx-auto mt-3 max-w-md list-decimal space-y-1 text-left text-sm text-gray-700">
        <li>l'adresse du webhook : <code className="break-all rounded bg-gray-100 px-1">{situation.webhook_url}</code></li>
        <li>le <b>jeton</b> de votre boutique, fourni par l'équipe adLyn {situation.jeton_configure ? "(déjà généré)" : "(pas encore généré : contactez adLyn)"} ;</li>
        <li>votre ID boutique : <b className="font-mono">{situation.code_boutique || "voir en haut du menu"}</b>.</li>
      </ol>
    </div>
  );
}

function Tuile({ libelle, valeur, detail, couleur = "text-ink" }) {
  return (
    <div className="card flex flex-col gap-1 p-4">
      <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">{libelle}</span>
      <span className={`text-lg font-extrabold sm:text-2xl ${couleur}`}>{valeur}</span>
      {detail && <span className="text-xs text-gray-500">{detail}</span>}
    </div>
  );
}

// Tableau de ventilation : libellé, nombre, total + barre de proportion
function Ventilation({ titre, lignes, devise, avecCodes = false }) {
  const max = Math.max(...lignes.map((l) => Math.abs(l.total)), 1);
  return (
    <section className="card overflow-hidden p-0">
      <h2 className="border-b border-gray-100 px-4 py-3 font-bold">{titre}</h2>
      {lignes.length === 0 ? <p className="px-4 py-6 text-center text-sm text-gray-500">Aucune opération.</p> : (
        <ul className="divide-y divide-gray-100">
          {lignes.map((l) => (
            <li key={l.libelle} className="px-4 py-2 text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="min-w-0 truncate font-semibold" title={avecCodes && l.codes?.length ? `Code(s) Aizenta : ${l.codes.join(", ")}` : undefined}>
                  {l.libelle}{avecCodes && l.codes?.length ? <span className="ml-1 font-mono text-xs font-normal text-gray-400">({l.codes.join(", ")})</span> : null}
                </span>
                <span className={`shrink-0 font-bold ${l.total < 0 ? "text-red-600" : ""}`}>{prix(l.total, devise)}</span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <div className="h-1.5 flex-1 rounded-full bg-gray-100">
                  <div className={`h-1.5 rounded-full ${l.total < 0 ? "bg-red-400" : "bg-primary"}`} style={{ width: `${(Math.abs(l.total) / max) * 100}%` }} />
                </div>
                <span className="shrink-0 text-xs text-gray-500">{l.nb} op.</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// Arrêts de caisse de la période, écarts mis en évidence
function ArretsCaisse({ arrets, devise }) {
  return (
    <section className="card overflow-x-auto p-0">
      <h2 className="border-b border-gray-100 px-4 py-3 font-bold">Arrêts de caisse</h2>
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr><th className="px-4 py-2">Date</th><th className="px-4 py-2">Caissier</th><th className="px-4 py-2 text-right">Théorique</th><th className="px-4 py-2 text-right">Compté</th><th className="px-4 py-2 text-right">Écart</th></tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {arrets.map((a) => (
            <tr key={a.id_aizenta} className={a.ecart ? "bg-red-50/50" : ""}>
              <td className="px-4 py-2">{dateHeure(a.date_heure)}</td>
              <td className="px-4 py-2">{a.caissier || "—"}</td>
              <td className="px-4 py-2 text-right">{prix(a.montant_theorique, devise)}</td>
              <td className="px-4 py-2 text-right">{prix(a.montant_compte, devise)}</td>
              <td className={`px-4 py-2 text-right font-bold ${a.ecart < 0 ? "text-red-600" : a.ecart > 0 ? "text-amber-700" : "text-green-700"}`}>
                {a.ecart > 0 ? "+" : ""}{prix(a.ecart, devise)}{a.ecart ? " ⚠️" : " ✓"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

// Tableau des opérations (sur téléphone : défilement horizontal)
function ListeOperations({ liste, devise }) {
  if (!liste) return <Chargement />;
  if (liste.lignes.length === 0) return <p className="px-4 py-6 text-center text-sm text-gray-500">Aucune opération pour ces critères.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-2">Date</th><th className="px-4 py-2">N°</th><th className="px-4 py-2">Type</th>
            <th className="px-4 py-2">Mode</th><th className="px-4 py-2">Caissier</th><th className="px-4 py-2">Référence / libellé</th>
            <th className="px-4 py-2 text-right">Montant</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {liste.lignes.map((o) => (
            <tr key={o.id_aizenta}>
              <td className="whitespace-nowrap px-4 py-2">{dateHeure(o.date_heure)}</td>
              <td className="px-4 py-2 font-mono text-xs">{o.id_aizenta}</td>
              <td className="px-4 py-2">{o.type_libelle}</td>
              <td className="px-4 py-2">{o.mode_libelle}</td>
              <td className="px-4 py-2">{o.caissier || "—"}</td>
              <td className="max-w-xs truncate px-4 py-2 text-gray-600" title={[o.reference, o.libelle, o.observation, o.code_client].filter(Boolean).join(" · ")}>
                {[o.reference, o.libelle || o.observation, o.code_client && `client ${o.code_client}`].filter(Boolean).join(" · ") || "—"}
              </td>
              <td className={`whitespace-nowrap px-4 py-2 text-right font-semibold ${o.montant < 0 ? "text-red-600" : ""}`}>{prix(o.montant, devise)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
