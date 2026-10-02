// Section « Sauvegarde / transfert des données » (super-administrateur) :
// export COMPLET de la base dans un fichier chiffré (.adlexport) et import de
// ce fichier, pour changer de cluster MongoDB Atlas en quelques clics.
// Chaque action exige le mot de passe du super-administrateur et une phrase
// secrète (jamais conservée : sans elle, le fichier est illisible).
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL, apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { Champ } from "./composants";
import { tailleLisible } from "./outils";

const PHRASE_MIN = 12;
const MOT_REMPLACER = "REMPLACER";

// Libellés du journal des opérations
const ACTIONS = { export: "Export", import: "Import", telechargement_export: "Téléchargement" };
const STATUTS = {
  DEMARRE: { libelle: "Démarré", classe: "bg-gray-100 text-gray-700" },
  TERMINE: { libelle: "Terminé", classe: "bg-green-100 text-green-800" },
  ECHEC: { libelle: "Échec", classe: "bg-red-100 text-red-700" },
  MOT_DE_PASSE_REFUSE: { libelle: "Mot de passe refusé", classe: "bg-amber-100 text-amber-800" },
};

function Pastille({ statut }) {
  const s = STATUTS[statut] || { libelle: statut || "—", classe: "bg-gray-100 text-gray-700" };
  return <span className={`badge whitespace-nowrap ${s.classe}`}>{s.libelle}</span>;
}

// Suivi d'une opération en tâche de fond (interrogation toutes les secondes)
function useSuiviTache(tacheId) {
  const [tache, setTache] = useState(null);
  useEffect(() => {
    if (!tacheId) { setTache(null); return undefined; }
    let actif = true;
    let minuteur;
    async function interroger() {
      try {
        const { data } = await apiClient.get(`/plateforme/transfert/taches/${tacheId}`);
        if (!actif) return;
        setTache(data);
        if (data.statut === "EN_COURS") minuteur = setTimeout(interroger, 1000);
      } catch {
        // Coupure réseau passagère : on réessaie un peu plus tard
        if (actif) minuteur = setTimeout(interroger, 3000);
      }
    }
    interroger();
    return () => { actif = false; clearTimeout(minuteur); };
  }, [tacheId]);
  return tache;
}

function BarreProgression({ tache, envoi }) {
  const pourcentage = envoi != null ? envoi : (tache?.progression ?? 0);
  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold">{envoi != null ? "Envoi du fichier vers le serveur…" : tache?.etape}</p>
      <div className="h-3 overflow-hidden rounded-full bg-gray-200">
        <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pourcentage}%` }} />
      </div>
      <p className="text-xs text-gray-500">
        {pourcentage} %{tache?.documents_total ? ` · ${tache.documents_traites.toLocaleString("fr-FR")} / ${tache.documents_total.toLocaleString("fr-FR")} élément(s)` : ""}
      </p>
      <p className="text-xs text-gray-500">Vous pouvez patienter sur cette page ; ne fermez pas l'onglet.</p>
    </div>
  );
}

// Encadré d'explication de la phrase secrète (export et import)
function AvertissementPhrase() {
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
      <p className="font-bold">🔑 La phrase secrète protège le fichier</p>
      <ul className="mt-1 list-inside list-disc space-y-0.5">
        <li>Le fichier contient les données de toutes les boutiques et de leurs clients : il est <b>entièrement chiffré</b> avec cette phrase.</li>
        <li>Elle sera <b>indispensable</b> pour importer le fichier. Elle n'est enregistrée nulle part : <b>si vous l'oubliez, personne ne pourra la retrouver</b> et le fichier sera inutilisable.</li>
        <li>Choisissez une phrase d'au moins {PHRASE_MIN} caractères (par exemple quelques mots sans rapport entre eux) et notez-la en lieu sûr, à part du fichier.</li>
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fenêtre « Exporter toutes les données »
// ---------------------------------------------------------------------------
function FenetreExport({ tacheInitiale, onFermer, onFini }) {
  const toast = useToast();
  const [form, setForm] = useState({ mot_de_passe: "", phrase: "", phrase_confirmation: "", note: false });
  const [envoi, setEnvoi] = useState(false);
  const [tacheId, setTacheId] = useState(tacheInitiale?.id || null);
  const [telecharge, setTelecharge] = useState(false);
  const tache = useSuiviTache(tacheId);
  const onFiniRef = useRef(onFini);
  onFiniRef.current = onFini;
  const statut = tache?.statut;
  useEffect(() => { if (statut && statut !== "EN_COURS") onFiniRef.current?.(); }, [statut]);

  const maj = (champ, valeur) => setForm((f) => ({ ...f, [champ]: valeur }));
  const phraseOk = form.phrase.length >= PHRASE_MIN;
  const identiques = form.phrase === form.phrase_confirmation;
  const pret = form.mot_de_passe && phraseOk && identiques && form.note;

  async function lancer(e) {
    e.preventDefault();
    if (!pret) return;
    setEnvoi(true);
    try {
      const { data } = await apiClient.post("/plateforme/transfert/export", {
        mot_de_passe: form.mot_de_passe, phrase: form.phrase, phrase_confirmation: form.phrase_confirmation });
      setForm({ mot_de_passe: "", phrase: "", phrase_confirmation: "", note: true }); // rien ne reste dans la page
      setTacheId(data.id);
    } catch (err) {
      toast.erreur(messageErreur(err, "L'export n'a pas pu démarrer"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Modal ouvert titre="Exporter toutes les données" onFermer={onFermer}>
      {!tacheId ? (
        <form onSubmit={lancer} className="space-y-4">
          <p className="text-sm text-gray-600">
            Toutes les données de la plateforme (boutiques, comptes, produits, clients, factures, paiements, réglages…)
            sont regroupées dans <b>un seul fichier chiffré</b>, à télécharger sur votre ordinateur.
            Les photos et documents restent sur Cloudflare R2 : le fichier contient leurs adresses.
          </p>
          <AvertissementPhrase />
          <Champ label="Phrase secrète" aide={`${form.phrase.length} caractère(s) — au moins ${PHRASE_MIN}`}>
            <input className={`input ${form.phrase && !phraseOk ? "border-red-400" : ""}`} type="password" autoComplete="new-password"
              value={form.phrase} onChange={(e) => maj("phrase", e.target.value)} />
          </Champ>
          <Champ label="Retapez la phrase secrète" aide={form.phrase_confirmation && !identiques ? "Les deux phrases ne sont pas identiques" : null}>
            <input className={`input ${form.phrase_confirmation && !identiques ? "border-red-400" : ""}`} type="password" autoComplete="new-password"
              value={form.phrase_confirmation} onChange={(e) => maj("phrase_confirmation", e.target.value)} />
          </Champ>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={form.note} onChange={(e) => maj("note", e.target.checked)} />
            <span>J'ai noté ma phrase secrète en lieu sûr. Je sais qu'elle ne pourra pas être retrouvée.</span>
          </label>
          <Champ label="Votre mot de passe (super-administrateur)" aide="Demandé à chaque export, par sécurité.">
            <input className="input" type="password" autoComplete="current-password" value={form.mot_de_passe}
              onChange={(e) => maj("mot_de_passe", e.target.value)} />
          </Champ>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button type="button" className="btn-outline" onClick={onFermer}>Annuler</button>
            <button className="btn-primary" disabled={!pret || envoi}>{envoi ? "Démarrage…" : "Lancer l'export"}</button>
          </div>
        </form>
      ) : !tache || tache.statut === "EN_COURS" ? (
        <BarreProgression tache={tache} />
      ) : tache.statut === "ECHEC" ? (
        <div className="space-y-4">
          <p className="rounded-xl bg-red-50 p-3 text-sm text-red-800">❌ {tache.erreur}</p>
          <button type="button" className="btn-outline w-full" onClick={onFermer}>Fermer</button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl bg-green-50 p-3 text-sm text-green-900">
            <p className="font-bold">✅ Export terminé</p>
            <p>{tache.rapport?.documents?.toLocaleString("fr-FR")} élément(s) dans {tache.rapport?.collections?.length} collection(s) · {tailleLisible(tache.taille)}</p>
          </div>
          {tache.fichier_disponible && !telecharge ? (
            <>
              <a className="btn-primary flex w-full justify-center" href={`${API_BASE_URL}/plateforme/transfert/taches/${tache.id}/fichier`}
                onClick={() => setTelecharge(true)}>⬇ Télécharger « {tache.fichier_nom} »</a>
              <p className="text-xs text-gray-500">
                Le fichier ne peut être téléchargé <b>qu'une seule fois</b> : il est effacé du serveur juste après
                (ou au bout d'une heure). Rangez-le en lieu sûr, par exemple sur une clé USB et dans votre Google Drive.
              </p>
            </>
          ) : (
            <p className="rounded-xl bg-gray-50 p-3 text-sm text-gray-700">
              Le fichier a été envoyé à votre navigateur puis effacé du serveur. Vérifiez qu'il se trouve bien dans
              vos téléchargements. S'il manque, relancez simplement un export.
            </p>
          )}
          <button type="button" className="btn-outline w-full" onClick={onFermer}>Fermer</button>
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Fenêtre « Importer »
// ---------------------------------------------------------------------------
function FenetreImport({ tacheInitiale, onFermer, onFini }) {
  const toast = useToast();
  const [form, setForm] = useState({ fichier: null, phrase: "", mot_de_passe: "", mode: "vide", confirmation: "" });
  const [envoi, setEnvoi] = useState(null); // pourcentage d'envoi du fichier (null = pas d'envoi)
  const [tacheId, setTacheId] = useState(tacheInitiale?.id || null);
  const tache = useSuiviTache(tacheId);
  const onFiniRef = useRef(onFini);
  onFiniRef.current = onFini;
  const statut = tache?.statut;
  useEffect(() => { if (statut && statut !== "EN_COURS") onFiniRef.current?.(); }, [statut]);

  const maj = (champ, valeur) => setForm((f) => ({ ...f, [champ]: valeur }));
  const remplacer = form.mode === "remplacer";
  const pret = form.fichier && form.phrase && form.mot_de_passe && (!remplacer || form.confirmation.trim() === MOT_REMPLACER);

  async function lancer(e) {
    e.preventDefault();
    if (!pret) return;
    const formulaire = new FormData();
    formulaire.append("fichier", form.fichier);
    formulaire.append("phrase", form.phrase);
    formulaire.append("mot_de_passe", form.mot_de_passe);
    formulaire.append("mode", form.mode);
    formulaire.append("confirmation", form.confirmation.trim());
    setEnvoi(0);
    try {
      const { data } = await apiClient.post("/plateforme/transfert/import", formulaire, {
        timeout: 0, // gros fichier : pas de limite de durée pour l'envoi
        onUploadProgress: (p) => p.total && setEnvoi(Math.round((p.loaded * 100) / p.total)),
      });
      setForm((f) => ({ ...f, phrase: "", mot_de_passe: "" }));
      setTacheId(data.id);
    } catch (err) {
      toast.erreur(messageErreur(err, "L'import n'a pas pu démarrer"));
    } finally {
      setEnvoi(null);
    }
  }

  const rapport = tache?.rapport;
  return (
    <Modal ouvert titre="Importer des données" onFermer={onFermer} large>
      {envoi != null ? (
        <BarreProgression envoi={envoi} />
      ) : !tacheId ? (
        <form onSubmit={lancer} className="space-y-4">
          <p className="text-sm text-gray-600">
            Choisissez un fichier <b>.adlexport</b> créé avec le bouton « Exporter toutes les données ».
            Le fichier est d'abord entièrement vérifié : s'il est abîmé ou si la phrase secrète est fausse,
            rien n'est modifié.
          </p>
          <Champ label="Fichier à importer (.adlexport)">
            <input type="file" accept=".adlexport,application/octet-stream" className="input py-2 text-sm"
              onChange={(e) => maj("fichier", e.target.files?.[0] || null)} />
          </Champ>
          <Champ label="Phrase secrète choisie lors de l'export">
            <input className="input" type="password" autoComplete="off" value={form.phrase} onChange={(e) => maj("phrase", e.target.value)} />
          </Champ>

          <fieldset className="space-y-2">
            <legend className="label">Que faire des données déjà présentes ?</legend>
            <label className={`flex items-start gap-2 rounded-xl border p-3 text-sm ${!remplacer ? "border-primary bg-primary/5" : "border-gray-200"}`}>
              <input type="radio" name="mode" className="mt-1" checked={!remplacer} onChange={() => maj("mode", "vide")} />
              <span><b>Base vide uniquement</b> (recommandé) — l'import est refusé si la nouvelle base contient déjà des
                boutiques ou d'autres données. Seuls les éléments créés automatiquement au démarrage du serveur
                (compte super-administrateur, formules d'abonnement par défaut) sont remplacés.</span>
            </label>
            <label className={`flex items-start gap-2 rounded-xl border p-3 text-sm ${remplacer ? "border-red-400 bg-red-50" : "border-gray-200"}`}>
              <input type="radio" name="mode" className="mt-1" checked={remplacer} onChange={() => maj("mode", "remplacer")} />
              <span><b>Remplacer</b> — chaque type de données présent dans le fichier est d'abord <b>effacé</b> de la base,
                puis remplacé par le contenu du fichier. Tout ce qui a été saisi entre-temps est perdu.</span>
            </label>
          </fieldset>
          {remplacer && (
            <Champ label={`Pour confirmer, tapez ${MOT_REMPLACER}`}>
              <input className={`input font-mono ${form.confirmation && form.confirmation.trim() !== MOT_REMPLACER ? "border-red-400" : ""}`}
                value={form.confirmation} onChange={(e) => maj("confirmation", e.target.value)} placeholder={MOT_REMPLACER} autoComplete="off" />
            </Champ>
          )}

          <div className="rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
            <p className="font-bold">ℹ️ Après l'import, reconnectez-vous</p>
            <p className="mt-1">
              Les comptes sont ceux du fichier : connectez-vous avec l'<b>e-mail et le mot de passe du super-administrateur
              de l'ancienne plateforme</b>. Le compte créé au démarrage de ce serveur est remplacé.
              Exception : si <code className="rounded bg-white px-1 font-mono">SUPER_ADMIN_RESET_PASSWORD</code> vaut « true »
              dans Render, le mot de passe de <code className="rounded bg-white px-1 font-mono">SUPER_ADMIN_EMAIL</code> sera
              remis à <code className="rounded bg-white px-1 font-mono">SUPER_ADMIN_PASSWORD</code> au prochain redémarrage.
            </p>
          </div>

          <Champ label="Votre mot de passe (super-administrateur)" aide="Celui avec lequel vous êtes connecté maintenant.">
            <input className="input" type="password" autoComplete="current-password" value={form.mot_de_passe}
              onChange={(e) => maj("mot_de_passe", e.target.value)} />
          </Champ>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button type="button" className="btn-outline" onClick={onFermer}>Annuler</button>
            <button className={remplacer ? "btn-danger" : "btn-primary"} disabled={!pret}>
              {remplacer ? "Remplacer les données" : "Lancer l'import"}
            </button>
          </div>
        </form>
      ) : !tache || tache.statut === "EN_COURS" ? (
        <BarreProgression tache={tache} />
      ) : tache.statut === "ECHEC" ? (
        <div className="space-y-4">
          <p className="rounded-xl bg-red-50 p-3 text-sm text-red-800">❌ {tache.erreur}</p>
          <button type="button" className="btn-outline w-full" onClick={onFermer}>Fermer</button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className={`rounded-xl p-3 text-sm ${rapport?.conforme ? "bg-green-50 text-green-900" : "bg-amber-50 text-amber-900"}`}>
            <p className="font-bold">{rapport?.conforme ? "✅ Import terminé : tous les nombres correspondent" : "⚠️ Import terminé avec des écarts"}</p>
            <p>{rapport?.documents?.toLocaleString("fr-FR")} élément(s) importé(s){tache.source?.date_utc ? ` · export du ${dateHeure(tache.source.date_utc)}` : ""}.</p>
            <p className="mt-1 font-semibold">Reconnectez-vous maintenant avec les identifiants du super-administrateur de l'ancienne plateforme.</p>
          </div>
          {rapport?.avertissements?.length > 0 && (
            <ul className="list-inside list-disc rounded-xl bg-amber-50 p-3 text-xs text-amber-900">
              {rapport.avertissements.map((a) => <li key={a}>{a}</li>)}
            </ul>
          )}
          <div className="max-h-72 overflow-auto">
            <table className="table">
              <thead><tr><th>Collection</th><th className="text-right">Dans le fichier</th><th className="text-right">Importés</th><th className="text-right">Dans la base</th></tr></thead>
              <tbody>
                {(rapport?.collections || []).map((c) => (
                  <tr key={c.nom} className={c.dans_la_base < c.attendus ? "bg-red-50" : ""}>
                    <td className="break-all font-mono text-xs">{c.nom}</td>
                    <td className="text-right font-mono">{c.attendus}</td>
                    <td className="text-right font-mono">{c.importes}</td>
                    <td className="text-right font-mono">{c.dans_la_base}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button type="button" className="btn-primary w-full" onClick={() => window.location.assign("/connexion")}>Aller à la page de connexion</button>
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Section affichée dans la page « Sauvegardes » de la plateforme
// ---------------------------------------------------------------------------
export default function TransfertDonnees() {
  const toast = useToast();
  const toastRef = useRef(toast);
  toastRef.current = toast;
  const [etat, setEtat] = useState(null); // {base, collections, documents, tache_en_cours, historique}
  const [fenetre, setFenetre] = useState(null); // "export" | "import" | null

  // `silencieux` : après un import, la session peut être devenue invalide (comptes remplacés)
  const charger = useCallback(async (silencieux = false) => {
    try {
      const { data } = await apiClient.get("/plateforme/transfert");
      setEtat(data);
    } catch (err) {
      if (!silencieux) toastRef.current.erreur(messageErreur(err, "Impossible de lire l'état de la base"));
    }
  }, []);
  useEffect(() => { charger(); }, [charger]);

  const enCours = etat?.tache_en_cours;
  return (
    <section className="card space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-bold">Sauvegarde / transfert des données</h2>
          <p className="text-sm text-gray-500">
            Pour déménager toute la plateforme vers une nouvelle base MongoDB (par exemple quand le cluster Atlas gratuit est plein) :
          </p>
          <ol className="mt-1 list-inside list-decimal text-sm text-gray-600">
            <li>ici, <b>Exporter toutes les données</b> et télécharger le fichier ;</li>
            <li>dans Render, remplacer <code className="rounded bg-gray-100 px-1 font-mono">MONGO_URL</code> par l'adresse de la nouvelle base ;</li>
            <li>revenir ici, se connecter, puis <b>Importer</b> le fichier.</li>
          </ol>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto">
          <button type="button" className="btn-primary" disabled={!etat || (enCours && enCours.type !== "export")} onClick={() => setFenetre("export")}>
            ⬇ Exporter toutes les données
          </button>
          <button type="button" className="btn-outline" disabled={!etat || (enCours && enCours.type !== "import")} onClick={() => setFenetre("import")}>
            ⬆ Importer
          </button>
        </div>
      </div>

      {etat && (
        <p className="rounded-xl bg-gray-50 p-3 text-sm text-gray-700">
          Base actuelle : <b className="font-mono">{etat.base}</b> · {etat.collections} collection(s) · environ {etat.documents.toLocaleString("fr-FR")} élément(s)
          {enCours && <span className="ml-2 font-semibold text-primary">· {enCours.type === "export" ? "Export" : "Import"} en cours ({enCours.progression} %)</span>}
        </p>
      )}

      {etat?.historique?.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold text-gray-700">Journal des exports et imports</summary>
          <ul className="mt-2 divide-y divide-gray-100">
            {etat.historique.map((h) => (
              <li key={h.id} className="flex flex-wrap items-center gap-2 py-2">
                <span className="w-36 shrink-0 text-gray-500">{dateHeure(h.date)}</span>
                <span className="font-semibold">{ACTIONS[h.action] || h.action}</span>
                <Pastille statut={h.statut} />
                <span className="text-gray-500">{h.email}</span>
                {h.documents != null && <span className="text-gray-500">· {h.documents.toLocaleString("fr-FR")} élément(s)</span>}
                {h.mode && <span className="text-gray-500">· mode « {h.mode === "remplacer" ? "Remplacer" : "Base vide"} »</span>}
                {h.erreur && <span className="w-full text-xs text-red-700">{h.erreur}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {fenetre === "export" && (
        <FenetreExport tacheInitiale={enCours?.type === "export" ? enCours : null} onFermer={() => { setFenetre(null); charger(); }} onFini={() => charger(true)} />
      )}
      {fenetre === "import" && (
        <FenetreImport tacheInitiale={enCours?.type === "import" ? enCours : null} onFermer={() => { setFenetre(null); charger(true); }} onFini={() => charger(true)} />
      )}
    </section>
  );
}
