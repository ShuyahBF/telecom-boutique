// Sauvegarde GÉNÉRALE automatique (backend/sauvegarde_auto.py) : toute la base, chaque
// nuit, chiffrée au format .adlexport et envoyée sur Cloudflare R2 par un Cron Job Render.
// Alertes (désactivée, plus de 26 h sans réussite…), historique, fichiers présents dans R2
// et restauration (import « Remplacer » : mot de passe + mot REMPLACER).
import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Modal from "@/components/Modal";
import ChampMotDePasse from "@/components/ChampMotDePasse";
import { useToast } from "@/components/Toast";
import { tailleLisible } from "./outils";

const STATUTS = {
  SUCCES: { libelle: "Réussie", classe: "bg-green-100 text-green-800" },
  ECHEC: { libelle: "Échec", classe: "bg-red-100 text-red-700" },
  EN_COURS: { libelle: "En cours", classe: "bg-blue-100 text-blue-800" },
};

export default function SauvegardeGenerale() {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null);
  const [restauration, setRestauration] = useState(null); // { cle, motDePasse, confirmation, tache, erreur }

  const charger = useCallback(() => {
    apiClient.get("/plateforme/sauvegarde-auto").then(({ data }) => setDonnees(data))
      .catch((err) => toast.erreur(messageErreur(err, "Sauvegarde générale : état indisponible")));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  // Suivi de la restauration en cours (même suivi que l'import manuel)
  const tacheId = restauration?.tache?.id;
  const tacheEnCours = restauration?.tache?.statut === "EN_COURS";
  useEffect(() => {
    if (!tacheId || !tacheEnCours) return undefined;
    const t = setInterval(async () => {
      try {
        const { data } = await apiClient.get(`/plateforme/transfert/taches/${tacheId}`);
        setRestauration((r) => (r ? { ...r, tache: data } : r));
      } catch { /* session remplacée pendant l'import : on réessaie */ }
    }, 1500);
    return () => clearInterval(t);
  }, [tacheId, tacheEnCours]);

  async function lancer() {
    if (!window.confirm("Lancer maintenant la sauvegarde générale du jour (si elle n'est pas déjà faite) ?")) return;
    try {
      const { data } = await apiClient.post("/plateforme/sauvegarde-auto/lancer");
      toast.succes(data.message || "Sauvegarde générale lancée");
      setTimeout(charger, 3000);
    } catch (err) {
      toast.erreur(messageErreur(err, "Lancement impossible"));
    }
  }

  async function restaurer(e) {
    e.preventDefault();
    try {
      const { data } = await apiClient.post("/plateforme/sauvegarde-auto/restaurer", {
        cle: restauration.cle, mot_de_passe: restauration.motDePasse, confirmation: restauration.confirmation });
      setRestauration((r) => ({ ...r, motDePasse: "", tache: data, erreur: "" }));
    } catch (err) {
      setRestauration((r) => ({ ...r, erreur: messageErreur(err, "Restauration impossible") }));
    }
  }

  if (!donnees) return null;
  const d = donnees.derniere_reussite;
  return (
    <section className="card space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold">🗄️ Sauvegarde générale automatique (R2)</h2>
          <p className="text-sm text-gray-500">
            Toute la base, chaque nuit (Cron Job Render), chiffrée au format .adlexport avec la phrase SAUVEGARDE_AUTO_PHRASE.
            Conservées : {donnees.retention.quotidiennes} quotidiennes, {donnees.retention.hebdomadaires} hebdomadaires,
            {" "}{donnees.retention.mensuelles} mensuelles. Emplacement : {donnees.bucket}/{donnees.prefixe}
          </p>
        </div>
        <button type="button" className="btn-outline w-full sm:w-auto" disabled={!donnees.active} onClick={lancer}>▶ Lancer celle du jour</button>
      </div>

      {donnees.alertes.length > 0 && (
        <ul className="space-y-1 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {donnees.alertes.map((a) => <li key={a}>⚠️ {a}</li>)}
        </ul>
      )}
      <p className="text-sm">Dernière réussite : {d
        ? <b>{dateHeure(d.fin)} · {d.fichier} ({tailleLisible(d.taille)})</b>
        : <b className="text-orange-600">Aucune sauvegarde enregistrée</b>}</p>

      {donnees.historique.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-gray-500"><tr><th className="py-1 pr-3">Jour</th><th className="pr-3">Statut</th><th className="pr-3">Fichier</th><th className="pr-3">Rapport</th><th>Erreur</th></tr></thead>
            <tbody className="divide-y divide-gray-100">
              {donnees.historique.map((h) => {
                const s = STATUTS[h.statut] || { libelle: h.statut, classe: "bg-gray-100" };
                return (
                  <tr key={h.jour}>
                    <td className="py-1 pr-3 whitespace-nowrap">{h.jour}</td>
                    <td className="pr-3"><span className={`badge ${s.classe}`}>{s.libelle}</span></td>
                    <td className="pr-3">{h.fichier || "—"}{h.taille ? ` (${tailleLisible(h.taille)})` : ""}</td>
                    <td className="pr-3">{h.rapport?.statut || "—"}</td>
                    <td className="text-red-700">{h.erreur || ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div>
        <h3 className="mb-1 font-bold">Fichiers présents dans R2</h3>
        {donnees.erreur_r2 && <p className="text-sm text-red-700">{donnees.erreur_r2}</p>}
        {!donnees.fichiers_r2?.length ? <p className="text-sm text-gray-500">Aucun fichier.</p> : (
          <ul className="divide-y divide-gray-100 text-sm">
            {donnees.fichiers_r2.map((f) => (
              <li key={f.cle} className="flex flex-wrap items-center gap-2 py-1">
                <span className="min-w-0 flex-1 break-all font-mono text-xs">{f.cle.split("/").pop()}</span>
                <span className="text-xs text-gray-500">{tailleLisible(f.taille)}</span>
                <button type="button" className="btn-outline btn-sm text-red-700"
                  onClick={() => setRestauration({ cle: f.cle, motDePasse: "", confirmation: "", tache: null, erreur: "" })}>Restaurer…</button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Modal ouvert={!!restauration} titre="Restaurer une sauvegarde générale" onFermer={() => !tacheEnCours && setRestauration(null)}>
        {restauration && (restauration.tache ? (
          <div className="space-y-2 text-sm">
            <p><b>{restauration.tache.etape}</b> — {restauration.tache.progression} %</p>
            {restauration.tache.statut === "TERMINE" && <p className="rounded-lg bg-green-50 p-2 text-green-800">Restauration terminée. Reconnectez-vous si votre session a été remplacée.</p>}
            {restauration.tache.statut === "ECHEC" && <p className="rounded-lg bg-red-50 p-2 text-red-700">{restauration.tache.erreur}</p>}
          </div>
        ) : (
          <form onSubmit={restaurer} className="space-y-3 text-sm">
            <p className="rounded-lg bg-red-50 p-2 text-red-800">
              Mode « Remplacer » : TOUTES les données actuelles de la plateforme seront remplacées par celles de
              <b> {restauration.cle.split("/").pop()}</b>. Faites d'abord un export manuel si vous avez un doute.
            </p>
            <label className="block"><span className="label">Votre mot de passe</span>
              <ChampMotDePasse required autoComplete="current-password" value={restauration.motDePasse}
                onChange={(e) => setRestauration((r) => ({ ...r, motDePasse: e.target.value }))} /></label>
            <label className="block"><span className="label">Tapez REMPLACER pour confirmer</span>
              <input className="input" required value={restauration.confirmation}
                onChange={(e) => setRestauration((r) => ({ ...r, confirmation: e.target.value }))} /></label>
            {restauration.erreur && <p className="rounded-lg bg-red-50 p-2 text-red-700">{restauration.erreur}</p>}
            <button className="btn-primary w-full bg-red-600 hover:bg-red-700" disabled={restauration.confirmation !== "REMPLACER"}>Restaurer</button>
          </form>
        ))}
      </Modal>
    </section>
  );
}
