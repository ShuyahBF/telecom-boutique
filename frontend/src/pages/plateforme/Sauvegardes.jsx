import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { EnTetePlateforme } from "./_plateforme/composants";
import { DECLENCHEURS, tailleLisible } from "./_plateforme/outils";
import TransfertDonnees from "./_plateforme/TransfertDonnees";
import SauvegardeGenerale from "./_plateforme/SauvegardeGenerale";

// Statut d'une sauvegarde (badge vert / rouge)
const STATUTS_SAUVEGARDE = {
  SUCCES: { libelle: "Réussie", classe: "bg-green-100 text-green-800" },
  ECHEC: { libelle: "Échec", classe: "bg-red-100 text-red-700" },
};

// Statut d'envoi du rapport de la nuit par e-mail
const STATUTS_RAPPORT = {
  ENVOYE: { libelle: "Envoyé", classe: "bg-green-100 text-green-800" },
  NON_ENVOYE: { libelle: "Non envoyé", classe: "bg-gray-100 text-gray-700" },
  ECHEC: { libelle: "Échec d'envoi", classe: "bg-red-100 text-red-700" },
};

// Petit badge générique à partir d'une des tables ci-dessus
function Pastille({ table, valeur }) {
  const s = table[valeur] || { libelle: valeur || "—", classe: "bg-gray-100 text-gray-700" };
  return <span className={`badge whitespace-nowrap ${s.classe}`}>{s.libelle}</span>;
}

// Où se trouve le fichier d'une sauvegarde (Google Drive, serveur, nulle part)
function emplacement(s) {
  if (s.drive_id) return "Google Drive";
  if (s.cle_privee) return "Serveur (stockage privé)";
  return "—";
}

// ---------------------------------------------------------------------------
// Page « Sauvegardes » de la plateforme (super-administrateur) :
// configuration, lancement manuel, historique filtrable, rapports de la nuit.
// ---------------------------------------------------------------------------
export default function Sauvegardes() {
  const toast = useToast();
  const toastRef = useRef(toast); // le « toast » change à chaque affichage : on garde une référence stable
  toastRef.current = toast;

  // --- État de la page ---
  const [donnees, setDonnees] = useState(null); // {configuration, sauvegardes, rapports}
  const [boutiques, setBoutiques] = useState([]); // pour le filtre par boutique
  const [filtres, setFiltres] = useState({ boutique_id: "", du: "", au: "" });
  const [lancement, setLancement] = useState({ enCours: false, resultat: null });
  const [rapport, setRapport] = useState(null); // rapport ouvert dans la fenêtre (texte complet)

  // Chargement de l'historique (avec les filtres)
  const charger = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/plateforme/sauvegardes", { params: filtres });
      setDonnees(data);
    } catch (err) {
      toastRef.current.erreur(messageErreur(err, "Impossible de charger les sauvegardes"));
    }
  }, [filtres]);
  useEffect(() => { charger(); }, [charger]);

  // Liste des boutiques (une seule fois) pour le filtre
  useEffect(() => {
    apiClient.get("/plateforme/boutiques").then(({ data }) => setBoutiques(data)).catch(() => {});
  }, []);

  // Lancer tout de suite les sauvegardes de toutes les boutiques + le rapport
  async function lancerMaintenant() {
    if (!window.confirm("Lancer maintenant la sauvegarde de TOUTES les boutiques puis envoyer le rapport ?\nCela peut prendre quelques minutes.")) return;
    setLancement({ enCours: true, resultat: null });
    try {
      const { data } = await apiClient.post("/plateforme/sauvegardes/lancer", null, { timeout: 30 * 60000 });
      setLancement({ enCours: false, resultat: data });
      const echecs = data.sauvegardes.filter((s) => s.statut !== "SUCCES").length;
      if (echecs) toast.erreur(`${echecs} sauvegarde(s) en échec : voir le détail ci-dessous.`);
      else toast.succes("Toutes les sauvegardes ont réussi.");
      charger();
    } catch (err) {
      setLancement({ enCours: false, resultat: null });
      toast.erreur(messageErreur(err, "Le lancement des sauvegardes a échoué"));
    }
  }

  // Ouvrir le texte complet d'un rapport
  async function ouvrirRapport(r) {
    setRapport({ ...r, chargement: true });
    try {
      const { data } = await apiClient.get(`/plateforme/rapports/${r.id}`);
      setRapport(data);
    } catch (err) {
      setRapport(null);
      toast.erreur(messageErreur(err, "Rapport introuvable"));
    }
  }

  const config = donnees?.configuration;
  const resultat = lancement.resultat;
  const reussies = resultat ? resultat.sauvegardes.filter((s) => s.statut === "SUCCES").length : 0;

  return (
    <div className="min-h-screen bg-gray-50">
      <EnTetePlateforme />

      <main className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6">
        {/* Titre + lien retour + bouton de lancement */}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <Link to="/plateforme" className="text-sm font-semibold text-primary">← Retour aux boutiques</Link>
            <h1 className="text-2xl font-extrabold">Sauvegardes</h1>
            <p className="text-sm text-gray-500">Chaque nuit, les données de chaque boutique sont chiffrées puis envoyées sur Google Drive, et un rapport vous est envoyé.</p>
          </div>
          <button type="button" className="btn-primary w-full sm:w-auto" disabled={lancement.enCours || !config} onClick={lancerMaintenant}>
            {lancement.enCours ? "Sauvegardes en cours… (patientez)" : "▶ Lancer les sauvegardes maintenant"}
          </button>
        </div>

        {!donnees ? <Chargement /> : (
          <>
            {/* Résultat du dernier lancement manuel */}
            {resultat && (
              <div className={`card ${resultat.sauvegardes.length - reussies ? "border-red-200 bg-red-50/50" : "border-green-200 bg-green-50/50"}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-bold">
                    Résultat : {reussies} réussie(s) · {resultat.sauvegardes.length - reussies} échec(s) sur {resultat.sauvegardes.length} boutique(s)
                  </p>
                  <button type="button" className="text-sm text-gray-500 hover:text-ink" onClick={() => setLancement({ enCours: false, resultat: null })}>Masquer ✕</button>
                </div>
                <p className="mt-1 text-sm text-gray-600">
                  Rapport : <Pastille table={STATUTS_RAPPORT} valeur={resultat.rapport?.statut} />
                  {resultat.rapport?.erreur && <span className="ml-2">{resultat.rapport.erreur}</span>}
                  {resultat.rapport && <button type="button" className="ml-2 font-semibold text-primary underline" onClick={() => ouvrirRapport(resultat.rapport)}>Lire le rapport</button>}
                </p>
              </div>
            )}

            {/* Configuration du serveur (variables d'environnement) */}
            <CarteConfiguration config={config} />

            {/* Historique filtrable */}
            <section className="card p-0">
              <div className="flex flex-wrap items-end gap-3 border-b border-gray-200 p-4">
                <h2 className="mr-auto text-lg font-bold">Historique des sauvegardes</h2>
                <label className="w-full sm:w-56">
                  <span className="label">Boutique</span>
                  <select className="input bg-white" value={filtres.boutique_id} onChange={(e) => setFiltres({ ...filtres, boutique_id: e.target.value })}>
                    <option value="">Toutes les boutiques</option>
                    {boutiques.map((b) => <option key={b.id} value={b.id}>{b.nom} ({b.code_marchand})</option>)}
                  </select>
                </label>
                <label className="flex-1 sm:w-40 sm:flex-none">
                  <span className="label">Du</span>
                  <input className="input" type="date" value={filtres.du} onChange={(e) => setFiltres({ ...filtres, du: e.target.value })} />
                </label>
                <label className="flex-1 sm:w-40 sm:flex-none">
                  <span className="label">Au</span>
                  <input className="input" type="date" value={filtres.au} onChange={(e) => setFiltres({ ...filtres, au: e.target.value })} />
                </label>
                {(filtres.boutique_id || filtres.du || filtres.au) && (
                  <button type="button" className="btn-outline btn-sm" onClick={() => setFiltres({ boutique_id: "", du: "", au: "" })}>Effacer</button>
                )}
              </div>
              <HistoriqueSauvegardes sauvegardes={donnees.sauvegardes} />
            </section>

            {/* Rapports de la nuit */}
            <section className="card p-0">
              <div className="border-b border-gray-200 p-4">
                <h2 className="text-lg font-bold">Rapports de la nuit</h2>
                <p className="text-sm text-gray-500">Les 30 derniers rapports (sauvegardes + publication du catalogue public). Cliquez pour lire le texte complet.</p>
              </div>
              {donnees.rapports.length === 0 ? <p className="p-6 text-center text-gray-500">Aucun rapport pour l'instant.</p> : (
                <ul className="divide-y divide-gray-100">
                  {donnees.rapports.map((r) => (
                    <li key={r.id}>
                      <button type="button" className="flex w-full flex-col gap-1 p-4 text-left hover:bg-gray-50 sm:flex-row sm:items-center sm:gap-4" onClick={() => ouvrirRapport(r)}>
                        <span className="w-36 shrink-0 text-sm text-gray-500">{dateHeure(r.date)}</span>
                        <span className="min-w-0 flex-1">
                          <span className="block font-semibold">{r.sujet}</span>
                          <span className="block text-xs text-gray-500">À : {r.destinataire || "(aucun destinataire configuré)"}{r.erreur ? ` · ${r.erreur}` : ""}</span>
                        </span>
                        <span className="self-start sm:self-center"><Pastille table={STATUTS_RAPPORT} valeur={r.statut} /></span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}

        {/* Sauvegarde générale automatique de toute la base vers R2 (Cron Job Render) */}
        <SauvegardeGenerale />

        {/* Export / import complet de la base (changement de cluster MongoDB) */}
        <TransfertDonnees />
      </main>

      {/* Fenêtre : texte complet d'un rapport */}
      <Modal ouvert={!!rapport} titre="Rapport de la nuit" onFermer={() => setRapport(null)} large>
        {rapport && (rapport.chargement ? <Chargement /> : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
              <span>{dateHeure(rapport.date)}</span>·<span>À : {rapport.destinataire || "—"}</span>
              <Pastille table={STATUTS_RAPPORT} valeur={rapport.statut} />
            </div>
            {rapport.erreur && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Envoi : {rapport.erreur}</p>}
            <p className="font-semibold">{rapport.sujet}</p>
            <pre className="max-h-[55vh] overflow-auto whitespace-pre-wrap break-words rounded-xl bg-gray-50 p-3 font-mono text-xs leading-relaxed">{rapport.corps}</pre>
          </div>
        ))}
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Carte « Configuration » : ce qui est prêt (✅) et ce qui manque (⚠️), avec
// l'explication des variables à renseigner dans Render (Environment).
// ---------------------------------------------------------------------------
function CarteConfiguration({ config }) {
  const lignes = [
    {
      titre: "Clé de chiffrement",
      ok: config.cle_chiffrement,
      valeur: config.cle_chiffrement ? "Configurée" : "Absente",
      aide: <>Renseignez <code>SAUVEGARDE_CLE</code> dans Render (32 octets en base64). Pour en créer une : <code>python -c "import sauvegarde; print(sauvegarde.generer_cle())"</code> dans le dossier backend. <b>Gardez-la précieusement</b> : sans elle, les sauvegardes sont illisibles.</>,
    },
    {
      titre: "Google Drive",
      ok: config.google_drive,
      valeur: config.google_drive ? `Configuré — dossier « ${config.dossier_drive} »` : "Non configuré",
      aide: <>Renseignez <code>GDRIVE_CLIENT_ID</code>, <code>GDRIVE_CLIENT_SECRET</code> et <code>GDRIVE_REFRESH_TOKEN</code> dans Render. Le jeton s'obtient une seule fois, sur votre ordinateur, avec le script <code>backend/outils/obtenir_jeton_gdrive.py</code> : <code>python obtenir_jeton_gdrive.py --client-id … --client-secret …</code>, puis recopier les trois valeurs affichées.</>,
    },
    {
      titre: "Rétention",
      ok: true,
      valeur: `${config.retention_jours} jour(s)`,
      aide: null,
      note: "Les sauvegardes plus anciennes sont supprimées du Drive.",
    },
    {
      titre: "E-mail du rapport",
      ok: !!config.rapport_email,
      valeur: config.rapport_email || "Non renseigné",
      aide: <>Renseignez <code>RAPPORT_EMAIL</code> dans Render (adresse qui reçoit le rapport chaque nuit).</>,
    },
    {
      titre: "Envoi d'e-mails de la plateforme",
      ok: config.smtp_plateforme,
      valeur: config.smtp_plateforme ? "Configuré" : "Non configuré",
      aide: <>Choisissez le service d'envoi (Resend, ZeptoMail, Brevo ou SMTP) dans Plateforme &gt; Paramètres. Sans cela, le rapport est seulement conservé ici.</>,
    },
    {
      titre: "Prochaine exécution automatique",
      ok: true,
      valeur: dateHeure(config.prochaine_execution),
      aide: null,
      note: "Chaque nuit à 00h (heure de Ouagadougou).",
    },
  ];
  const manquants = lignes.filter((l) => !l.ok).length;

  return (
    <section className="card">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">Configuration</h2>
        {manquants
          ? <span className="badge bg-amber-100 text-amber-800">{manquants} élément(s) à configurer</span>
          : <span className="badge bg-green-100 text-green-800">Tout est configuré</span>}
      </div>
      <ul className="grid gap-3 md:grid-cols-2">
        {lignes.map((l) => (
          <li key={l.titre} className={`rounded-xl border p-3 ${l.ok ? "border-gray-200" : "border-amber-300 bg-amber-50"}`}>
            <p className="flex items-start gap-2">
              <span>{l.ok ? "✅" : "⚠️"}</span>
              <span className="min-w-0">
                <span className="block text-sm text-gray-500">{l.titre}</span>
                <span className="block break-words font-semibold">{l.valeur}</span>
              </span>
            </p>
            {l.note && <p className="mt-1 pl-7 text-xs text-gray-500">{l.note}</p>}
            {!l.ok && l.aide && <p className="mt-2 pl-7 text-xs leading-relaxed text-amber-900 [&_code]:rounded [&_code]:bg-white [&_code]:px-1 [&_code]:font-mono">{l.aide}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Historique : tableau sur grand écran, cartes empilées sur téléphone
// ---------------------------------------------------------------------------
function HistoriqueSauvegardes({ sauvegardes }) {
  if (!sauvegardes.length) return <p className="p-6 text-center text-gray-500">Aucune sauvegarde pour ces critères.</p>;
  return (
    <>
      {/* Grand écran : tableau */}
      <div className="hidden overflow-x-auto md:block">
        <table className="table">
          <thead>
            <tr><th>Date</th><th>Boutique</th><th>Déclencheur</th><th>Statut</th><th>Fichier</th><th className="text-right">Taille</th><th>Erreur / emplacement</th></tr>
          </thead>
          <tbody>
            {sauvegardes.map((s) => (
              <tr key={s.id}>
                <td className="whitespace-nowrap">{dateHeure(s.date)}</td>
                <td><span className="font-semibold">{s.boutique_nom}</span> <span className="font-mono text-xs text-gray-500">{s.code_marchand}</span></td>
                <td><Pastille table={DECLENCHEURS} valeur={s.declencheur} /></td>
                <td><Pastille table={STATUTS_SAUVEGARDE} valeur={s.statut} /></td>
                <td className="max-w-[16rem] break-all font-mono text-xs">{s.fichier || "—"}</td>
                <td className="whitespace-nowrap text-right">{s.taille ? tailleLisible(s.taille) : "—"}</td>
                <td className="max-w-xs text-xs">
                  {s.erreur ? <span className="text-red-700">{s.erreur}</span> : <span className="text-gray-500">{emplacement(s)}{s.purges ? ` · ${s.purges} ancienne(s) supprimée(s)` : ""}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Téléphone : une carte par sauvegarde */}
      <ul className="divide-y divide-gray-100 md:hidden">
        {sauvegardes.map((s) => (
          <li key={s.id} className="space-y-1 p-4 text-sm">
            <div className="flex items-start justify-between gap-2">
              <p className="font-semibold">{s.boutique_nom} <span className="font-mono text-xs text-gray-500">{s.code_marchand}</span></p>
              <Pastille table={STATUTS_SAUVEGARDE} valeur={s.statut} />
            </div>
            <p className="flex flex-wrap items-center gap-2 text-gray-500">{dateHeure(s.date)} <Pastille table={DECLENCHEURS} valeur={s.declencheur} /></p>
            {s.fichier && <p className="break-all font-mono text-xs">{s.fichier} · {tailleLisible(s.taille)}</p>}
            {s.erreur ? <p className="text-xs text-red-700">{s.erreur}</p> : <p className="text-xs text-gray-500">{emplacement(s)}</p>}
          </li>
        ))}
      </ul>
    </>
  );
}
