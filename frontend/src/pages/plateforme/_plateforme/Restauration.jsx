// Fenêtre « Restaurer une sauvegarde » d'une boutique (super-administrateur).
// Opération DANGEREUSE : toutes les données de la boutique sont remplacées
// par celles du fichier. Garde-fous : avertissement clair, saisie du code
// marchand pour confirmer, et le serveur sauvegarde l'état actuel juste avant.
import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { Champ } from "./composants";
import { COLLECTIONS_SAUVEGARDE } from "./outils";

export default function Restauration({ boutique, onFermer, onRestauree }) {
  const toast = useToast();
  const [code, setCode] = useState(""); // code marchand retapé pour confirmer
  const [fichier, setFichier] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const [resultat, setResultat] = useState(null); // réponse du serveur après restauration

  // Remise à zéro à chaque ouverture
  const idBoutique = boutique?.id;
  useEffect(() => {
    setCode("");
    setFichier(null);
    setResultat(null);
  }, [idBoutique]);

  if (!boutique) return null;
  // Le bouton ne s'active que si le code saisi correspond (majuscules/minuscules indifférentes)
  const codeOk = code.trim().toUpperCase() === boutique.code_marchand;

  // Envoi du fichier + du code de confirmation (formulaire « multipart »)
  async function restaurer(e) {
    e.preventDefault();
    if (!codeOk || !fichier) return;
    const formulaire = new FormData();
    formulaire.append("fichier", fichier);
    formulaire.append("confirmation", code.trim());
    setEnvoi(true);
    try {
      const { data } = await apiClient.post(`/plateforme/boutiques/${boutique.id}/restauration`, formulaire, { timeout: 300000 });
      setResultat(data);
      toast.succes("Restauration terminée");
      onRestauree?.();
    } catch (err) {
      toast.erreur(messageErreur(err, "Restauration impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  // Total des éléments restaurés (toutes collections confondues)
  const total = resultat ? Object.values(resultat.documents_restaures || {}).reduce((s, n) => s + n, 0) : 0;

  return (
    <Modal ouvert titre={`Restaurer — ${boutique.nom}`} onFermer={onFermer}>
      {resultat ? (
        // ----- Après la restauration : compte rendu -----
        <div className="space-y-4">
          <div className="rounded-xl bg-green-50 p-3 text-sm text-green-900">
            <p className="font-bold">✅ Données restaurées ({total} élément(s))</p>
            <p>Sauvegarde du {dateHeure(resultat.date_sauvegarde)}.</p>
            {resultat.sauvegarde_avant_restauration && (
              <p className="mt-1 text-xs">L'état d'avant a été conservé sur le serveur : <span className="break-all font-mono">{resultat.sauvegarde_avant_restauration}</span></p>
            )}
          </div>
          <table className="table">
            <thead><tr><th>Données</th><th className="text-right">Nombre</th></tr></thead>
            <tbody>
              {Object.entries(resultat.documents_restaures || {}).map(([nom, n]) => (
                <tr key={nom}><td>{COLLECTIONS_SAUVEGARDE[nom] || nom}</td><td className="text-right font-mono">{n}</td></tr>
              ))}
            </tbody>
          </table>
          <button type="button" className="btn-primary w-full" onClick={onFermer}>Fermer</button>
        </div>
      ) : (
        // ----- Avant : avertissement + confirmation -----
        <form onSubmit={restaurer} className="space-y-4">
          <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-900">
            <p className="font-bold">⚠️ Attention : opération irréversible pour la boutique</p>
            <ul className="mt-1 list-inside list-disc space-y-0.5">
              <li><b>TOUTES les données</b> de « {boutique.nom} » (produits, clients, factures, commandes, SAV, comptes du personnel…) seront <b>remplacées</b> par celles du fichier.</li>
              <li>Tout ce qui a été saisi depuis la date de la sauvegarde sera perdu.</li>
              <li>Par sécurité, l'état actuel est <b>sauvegardé automatiquement</b> juste avant (visible dans l'écran Sauvegardes).</li>
            </ul>
          </div>

          <Champ label="Fichier de sauvegarde (.tlb.gz.enc)">
            <input type="file" accept=".enc,.gz,application/octet-stream" className="input py-2 text-sm"
              onChange={(e) => setFichier(e.target.files?.[0] || null)} />
          </Champ>
          <Champ label={`Pour confirmer, tapez le code marchand : ${boutique.code_marchand}`}>
            <input className={`input font-mono uppercase ${code && !codeOk ? "border-red-400" : ""}`} value={code}
              onChange={(e) => setCode(e.target.value)} placeholder={boutique.code_marchand} autoComplete="off" />
          </Champ>

          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button type="button" className="btn-outline" onClick={onFermer}>Annuler</button>
            <button className="btn-danger" disabled={!codeOk || !fichier || envoi}>{envoi ? "Restauration en cours…" : "Remplacer les données"}</button>
          </div>
        </form>
      )}
    </Modal>
  );
}
