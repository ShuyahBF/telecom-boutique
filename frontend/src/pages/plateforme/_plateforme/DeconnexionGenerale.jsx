import { useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { useToast } from "@/components/Toast";
import {
  dureeLisible, formatDecompte, heureLocale, signalerChangementMaintenance, useEtatMaintenance,
} from "@/lib/maintenancePlateforme";

// ---------------------------------------------------------------------------
// Section « Déconnexion de tous les utilisateurs » (Paramètres de la plateforme).
// Avant une opération importante, le super-administrateur envoie un message à
// tous les utilisateurs connectés avec une durée avant la déconnexion forcée :
//   - d'abord une modale qu'on peut fermer (puis un bandeau rouge) ;
//   - puis, pour la part choisie de la durée (80 % par défaut), l'écran est
//     verrouillé avec le message et un décompte à la seconde ;
//   - à l'échéance, tout le monde est déconnecté et ne peut plus se reconnecter
//     jusqu'à la réactivation (les super-administrateurs ne sont jamais bloqués).
// ---------------------------------------------------------------------------
const DUREE_MIN = 1;
const DUREE_MAX = 120;
const LIBELLES_ACTION = {
  ANNONCE: "Annonce envoyée",
  ANNULATION: "Annulée avant l'échéance",
  REACTIVATION: "Connexions réactivées",
};
const LIBELLES_PHASE = {
  annonce: { texte: "Annonce en cours (message fermable)", couleur: "bg-amber-100 text-amber-800" },
  verrouillage: { texte: "Écrans verrouillés", couleur: "bg-orange-100 text-orange-800" },
  maintenance: { texte: "Maintenance en cours — connexions bloquées", couleur: "bg-red-100 text-red-800" },
};

export default function DeconnexionGenerale() {
  const toast = useToast();
  // État complet (avec journal) lu sur la route du super-admin, décompte à la seconde
  const { etat, phase, secondes, maintenantServeur, recharger } = useEtatMaintenance(true, "/plateforme/deconnexion-generale");
  const [form, setForm] = useState({ message: "", duree_minutes: 5, part_verrouillage: 80 });
  const [envoi, setEnvoi] = useState(false);

  const maj = (champ, valeur) => setForm((f) => ({ ...f, [champ]: valeur }));
  const duree = Number(form.duree_minutes);
  const part = Number(form.part_verrouillage);
  const valide = form.message.trim() && Number.isInteger(duree) && duree >= DUREE_MIN && duree <= DUREE_MAX
    && Number.isInteger(part) && part >= 0 && part <= 100;

  // Aperçu chronologique si l'annonce part maintenant (heure du serveur)
  const totalS = (Number.isFinite(duree) ? duree : 0) * 60;
  const libreS = (totalS * (100 - (Number.isFinite(part) ? part : 0))) / 100;
  const debutVerrou = maintenantServeur + libreS * 1000;
  const echeance = maintenantServeur + totalS * 1000;

  async function agir(requete, succes) {
    setEnvoi(true);
    try {
      await requete();
      toast.succes(succes);
      await recharger();
      signalerChangementMaintenance(); // bandeau et autres onglets
      return true;
    } catch (err) {
      toast.erreur(messageErreur(err, "Action impossible"));
      await recharger();
      return false;
    } finally {
      setEnvoi(false);
    }
  }

  async function annoncer(e) {
    e.preventDefault();
    if (!valide) return;
    const ok = window.confirm(
      `Envoyer ce message à TOUS les utilisateurs ?\n\nIls seront déconnectés dans ${dureeLisible(totalS)} `
      + `(à ${heureLocale(echeance)}) et ne pourront se reconnecter qu'après votre réactivation.`);
    if (!ok) return;
    const fait = await agir(() => apiClient.post("/plateforme/deconnexion-generale", {
      message: form.message.trim(), duree_minutes: duree, part_verrouillage: part,
    }), "Annonce envoyée à tous les utilisateurs.");
    if (fait) setForm((f) => ({ ...f, message: "" }));
  }

  const annuler = () => window.confirm("Annuler la déconnexion programmée ? Personne ne sera déconnecté.")
    && agir(() => apiClient.post("/plateforme/deconnexion-generale/annuler"), "Déconnexion annulée.");
  const reactiver = () => agir(() => apiClient.post("/plateforme/deconnexion-generale/reactiver"),
    "Connexions réactivées : chacun peut se reconnecter.");

  return (
    <section className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">🔌 Déconnexion de tous les utilisateurs</h2>
        {phase !== "aucune" && LIBELLES_PHASE[phase] && (
          <span className={`badge ${LIBELLES_PHASE[phase].couleur}`}>{LIBELLES_PHASE[phase].texte}</span>
        )}
      </div>
      <p className="text-sm text-gray-500">
        Avant une opération importante : prévenez tous les utilisateurs connectés, verrouillez leur écran
        puis déconnectez-les. Personne (sauf les administrateurs de la plateforme) ne peut se reconnecter
        avant que vous ne réactiviez les connexions. Le portail public, les paiements et les webhooks
        (WhatsApp, PawaPay, Caisse Aizenta…) continuent de fonctionner.
      </p>

      {!etat ? <p className="text-sm text-gray-500">Chargement…</p> : phase === "aucune" ? (
        /* ---------- Formulaire d'annonce ---------- */
        <form onSubmit={annoncer} className="space-y-4">
          <label className="block">
            <span className="label">Message affiché à tous les utilisateurs</span>
            <textarea className="input min-h-[96px]" required maxLength={1000} value={form.message}
              placeholder="Ex. Mise à jour importante de la plateforme : merci d'enregistrer votre travail. Retour prévu vers 14 h."
              onChange={(e) => maj("message", e.target.value)} />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="label">Durée avant la déconnexion (minutes)</span>
              <input className="input" type="number" required min={DUREE_MIN} max={DUREE_MAX} step={1}
                value={form.duree_minutes} onChange={(e) => maj("duree_minutes", e.target.value)} />
              <span className="mt-1 block text-xs text-gray-500">De {DUREE_MIN} à {DUREE_MAX} minutes.</span>
            </label>
            <label className="block">
              <span className="label">Part de la durée avec écran verrouillé (%)</span>
              <input className="input" type="number" required min={0} max={100} step={1}
                value={form.part_verrouillage} onChange={(e) => maj("part_verrouillage", e.target.value)} />
              <span className="mt-1 block text-xs text-gray-500">80 % : sur 5 minutes, 1 minute de message puis 4 minutes verrouillées.</span>
            </label>
          </div>

          {/* Aperçu chronologique (si l'annonce part maintenant) */}
          {valide && (
            <ol className="space-y-1 rounded-lg bg-gray-50 p-3 text-sm text-gray-700">
              <li>📣 <b>{heureLocale(maintenantServeur)}</b> — message affiché à tous (fenêtre qu'on peut fermer, puis bandeau)
                {libreS > 0 ? <> pendant {dureeLisible(libreS)}</> : null}</li>
              <li>🔒 <b>{heureLocale(debutVerrou)}</b> — écran verrouillé, impossible à fermer, décompte à la seconde
                {totalS - libreS > 0 ? <> pendant {dureeLisible(totalS - libreS)}</> : null}</li>
              <li>⛔ <b>{heureLocale(echeance)}</b> — déconnexion forcée ; connexions bloquées jusqu'à votre réactivation</li>
            </ol>
          )}
          <button type="submit" className="btn-danger" disabled={envoi || !valide}>
            {envoi ? "Envoi…" : "📣 Envoyer l'annonce et programmer la déconnexion"}
          </button>
        </form>
      ) : (
        /* ---------- Annonce en cours ---------- */
        <div className="space-y-3">
          <blockquote className="whitespace-pre-line rounded-lg border-l-4 border-red-400 bg-red-50 p-3 text-gray-800">{etat.message}</blockquote>
          <ul className="space-y-1 text-sm text-gray-700">
            <li>📣 Annoncée à <b>{heureLocale(etat.annonce_le)}</b>{etat.annonce_par?.nom ? <> par {etat.annonce_par.nom}</> : null}
              {" "}({etat.duree_minutes} min, {etat.part_verrouillage} % verrouillées)</li>
            <li>🔒 Verrouillage des écrans à <b>{heureLocale(etat.debut_verrouillage)}</b></li>
            <li>⛔ Déconnexion forcée à <b>{heureLocale(etat.echeance)}</b></li>
          </ul>
          {phase === "maintenance" ? (
            <>
              <p className="rounded-lg bg-red-50 p-3 text-sm text-red-800">
                Tous les utilisateurs sont déconnectés et ne peuvent plus se connecter. Une fois votre opération
                terminée, réactivez les connexions : chacun devra se reconnecter (les anciennes sessions restent fermées).
              </p>
              <button type="button" className="btn-primary" disabled={envoi} onClick={reactiver}>
                {envoi ? "Réactivation…" : "✅ Réactiver les connexions"}
              </button>
            </>
          ) : (
            <>
              <p className="text-center">
                <span className="block text-xs font-semibold uppercase tracking-wider text-gray-500">Déconnexion forcée dans</span>
                <span className="font-mono text-3xl font-extrabold tabular-nums text-red-700">{formatDecompte(secondes)}</span>
              </p>
              <button type="button" className="btn-outline" disabled={envoi} onClick={annuler}>
                Annuler la déconnexion (personne ne sera déconnecté)
              </button>
            </>
          )}
        </div>
      )}

      {/* ---------- Journal ---------- */}
      {etat?.journal?.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold text-gray-700">Historique ({etat.journal.length})</summary>
          <ul className="mt-2 divide-y divide-gray-100">
            {etat.journal.map((j) => (
              <li key={j.id} className="py-2">
                <p><b>{LIBELLES_ACTION[j.action] || j.action}</b> — {new Date(j.date).toLocaleString("fr-FR")}
                  {j.par?.nom ? <> · {j.par.nom}</> : null}</p>
                {j.message && <p className="truncate text-gray-500">« {j.message} » · {j.duree_minutes} min, {j.part_verrouillage} % verrouillées</p>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
