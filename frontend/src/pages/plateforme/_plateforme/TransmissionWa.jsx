import { useEffect, useState } from "react";
import { apiClient, API_BASE_URL, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Chargement from "@/components/Chargement";

// Types de retours envoyés par SAWALI (protocole Liluvine v3) : libellé et couleur du badge
const TYPES = {
  statut: ["Statut", "bg-sky-100 text-sky-800"],
  reponse: ["Réponse du client", "bg-green-100 text-green-800"],
  desinscription: ["Désinscription (STOP)", "bg-red-100 text-red-700"],
  refus_desinscrit: ["Envoi refusé : désinscrit", "bg-amber-100 text-amber-800"],
};

// Carte « Transmission WA » (Plateforme > Paramètres) : canaux configurés, adresse de
// retour à saisir dans SAWALI, et les 100 derniers retours (statuts, réponses des
// clients, désinscriptions). Aucune clé n'est jamais affichée.
export default function TransmissionWa() {
  const [donnees, setDonnees] = useState(null);
  const [filtre, setFiltre] = useState("");
  const [erreur, setErreur] = useState("");

  // Chargement à l'ouverture et à chaque changement de filtre
  useEffect(() => {
    setDonnees(null);
    apiClient.get("/admin/transmission-wa/retours", { params: { type: filtre } })
      .then(({ data }) => { setDonnees(data); setErreur(""); })
      .catch((err) => setErreur(messageErreur(err, "Retours indisponibles")));
  }, [filtre]);

  return (
    <div className="card space-y-3">
      <h2 className="text-lg font-bold">💬 Transmission WA (WhatsApp)</h2>
      {/* Ordre des canaux et état de la configuration (booléens seulement) */}
      <p className="text-sm text-gray-600">
        Ordre d'envoi : WhatsApp Business de la boutique, puis celui de la plateforme, sinon la Transmission WA
        Universelle Liluvine (SAWALI). Si un WhatsApp Business échoue (fenêtre de 24 h…), le message repart par Liluvine,
        sauf numéro invalide. Le carrousel de produits reste réservé au WhatsApp Business.
      </p>
      {donnees && (
        <ul className="grid gap-1 text-sm sm:grid-cols-2">
          <li>WhatsApp Business de la plateforme : <b>{donnees.waba_plateforme_configure ? "✅ configuré" : "— non configuré"}</b></li>
          <li>Transmission Liluvine : <b>{donnees.liluvine_configure ? `✅ configurée (émetteur « ${donnees.emetteur} »)` : "⚠️ non configurée"}</b></li>
        </ul>
      )}
      {/* Adresse de retour à saisir dans SAWALI pour l'émetteur adLyn */}
      <p className="rounded-xl bg-gray-50 p-3 text-sm">
        Adresse de retour à saisir dans SAWALI :{" "}
        <code className="break-all font-mono">POST {API_BASE_URL}/webhooks/liluvine-retour</code>
        <span className="block text-xs text-gray-500">Signée avec la même clé que les envois (LILUVINE_WA_HMAC). Les réponses des clients sont aussi signalées par e-mail aux administrateurs.</span>
      </p>

      {/* Filtre par type de retour */}
      <select className="input max-w-xs" value={filtre} onChange={(e) => setFiltre(e.target.value)} aria-label="Filtrer par type de retour">
        <option value="">Tous les retours</option>
        {Object.entries(TYPES).map(([code, [libelle]]) => <option key={code} value={code}>{libelle}</option>)}
      </select>

      {/* Les 100 derniers retours (tableau : survol bleu clair / sélection orange par la règle CSS globale) */}
      {erreur ? <p className="text-red-600">{erreur}</p> : !donnees ? <Chargement /> : donnees.retours.length === 0 ? (
        <p className="py-4 text-center text-sm text-gray-500">Aucun retour reçu de SAWALI.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="table">
            <thead><tr><th>Reçu le</th><th>Type</th><th>Numéro</th><th>Boutique</th><th>Détail</th></tr></thead>
            <tbody>
              {donnees.retours.map((l) => {
                const [libelle, couleur] = TYPES[l.type] || [l.type, "bg-gray-100"];
                return (
                  <tr key={l.id}>
                    <td className="whitespace-nowrap">{dateHeure(l.recu_le)}</td>
                    <td><span className={`badge ${couleur}`}>{libelle}</span></td>
                    <td className="font-mono text-xs">{l.numero || "—"}</td>
                    <td>{l.boutique_nom || "—"}</td>
                    <td className="max-w-xs break-words text-xs text-gray-600">
                      {l.type === "statut" ? `${l.statut || ""}${l.erreur ? ` — ${l.erreur}` : ""}` : l.texte || (l.media ? `Pièce jointe : ${l.media.type}` : "")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
