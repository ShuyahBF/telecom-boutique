import { useEffect, useState } from "react";
import { apiClient, API_BASE_URL, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";

// Libellés des statuts d'envoi des identifiants au DG (e-mail / SMS)
export const LIBELLES_ENVOI = {
  ENVOYE: "✅ envoyé", ECHEC: "❌ échec", NON_CONFIGURE: "⚙️ non configuré", undefined: "—",
};

// Résultat de chaque appel du webhook : couleur du badge
const RESULTATS = {
  CREEE: ["Créée", "bg-green-100 text-green-800"],
  IGNOREE: ["Ignorée (existe déjà)", "bg-gray-100 text-gray-700"],
  REFUSEE: ["Refusée", "bg-red-100 text-red-700"],
  QUOTA: ["Quota atteint", "bg-amber-100 text-amber-800"],
};

// Fenêtre « Webhook » : adresse à donner au système appelant, état de la
// configuration et journal des derniers appels (créations, rejets, tentatives
// frauduleuses), pour repérer d'éventuels abus.
export default function JournalWebhook({ ouvert, onFermer }) {
  const [donnees, setDonnees] = useState(null);
  const [filtre, setFiltre] = useState("");
  const [erreur, setErreur] = useState("");

  // Chargement à l'ouverture et à chaque changement de filtre
  useEffect(() => {
    if (!ouvert) return;
    setDonnees(null);
    apiClient.get("/plateforme/webhooks/journal", { params: { resultat: filtre } })
      .then(({ data }) => { setDonnees(data); setErreur(""); })
      .catch((err) => setErreur(messageErreur(err, "Journal indisponible")));
  }, [ouvert, filtre]);

  return (
    <Modal ouvert={ouvert} titre="Webhook de création des boutiques" onFermer={onFermer} large>
      <div className="space-y-4 text-sm">
        {/* Adresse et règles de sécurité, à transmettre à l'intégrateur */}
        <div className="rounded-xl bg-gray-50 p-3">
          <p>Adresse : <code className="break-all font-mono">POST {API_BASE_URL}/webhooks/boutiques</code></p>
          <p className="mt-1 text-gray-600">
            Signature HMAC-SHA256 obligatoire (en-têtes <code>X-Adlyn-Horodatage</code> et <code>X-Adlyn-Signature</code>),
            événement à usage unique, quota de {donnees?.quota_jour ?? "…"} créations par 24 h.
            Les boutiques créées restent invisibles du public jusqu'à votre validation.
          </p>
          {donnees && !donnees.configure && (
            <p className="mt-2 rounded-lg bg-amber-50 p-2 text-amber-800">
              ⚠️ Webhook fermé : définissez la variable WEBHOOK_BOUTIQUES_SECRET sur Render pour l'activer.
            </p>
          )}
        </div>

        {/* Filtre par résultat */}
        <select className="input max-w-xs" value={filtre} onChange={(e) => setFiltre(e.target.value)} aria-label="Filtrer par résultat">
          <option value="">Tous les appels</option>
          {Object.entries(RESULTATS).map(([code, [libelle]]) => <option key={code} value={code}>{libelle}</option>)}
        </select>

        {erreur ? <p className="text-red-600">{erreur}</p> : !donnees ? <Chargement /> : donnees.lignes.length === 0 ? (
          <p className="py-6 text-center text-gray-500">Aucun appel enregistré.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead><tr><th>Date</th><th>Résultat</th><th>Boutique demandée</th><th>Détail</th><th>Adresse IP</th></tr></thead>
              <tbody>
                {donnees.lignes.map((l) => {
                  const [libelle, couleur] = RESULTATS[l.resultat] || [l.resultat, "bg-gray-100"];
                  return (
                    <tr key={l.id}>
                      <td className="whitespace-nowrap">{dateHeure(l.date)}</td>
                      <td><span className={`badge ${couleur}`}>{libelle}</span></td>
                      <td>{l.nom || "—"}</td>
                      <td className="max-w-xs break-words text-xs text-gray-600">{l.detail}</td>
                      <td className="font-mono text-xs">{l.ip}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Modal>
  );
}
