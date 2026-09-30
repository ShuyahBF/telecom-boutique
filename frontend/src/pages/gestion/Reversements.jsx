import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { date, dateHeure, montant } from "@/lib/format";
import Chargement from "@/components/Chargement";
import EnTetePage from "@/components/EnTetePage";

const fcfa = (v) => `${montant(v || 0)} FCFA`;

// Reversements PawaPay de LA boutique (DG et comptable) : les paiements Mobile
// Money de ses clients arrivent sur le compte de la plateforme adLyn, qui les
// lui reverse. La boutique voit ici uniquement SES encaissements et SES
// reversements (le serveur filtre sur la boutique du compte connecté).
export default function Reversements() {
  const [donnees, setDonnees] = useState(null);
  const [erreur, setErreur] = useState("");
  const [filtre, setFiltre] = useState(""); // "" | "attente" | "reverses"

  useEffect(() => {
    apiClient.get("/reversements").then(({ data }) => setDonnees(data))
      .catch((err) => setErreur(messageErreur(err, "Reversements indisponibles")));
  }, []);

  if (erreur) return <p className="text-red-600">{erreur}</p>;
  if (!donnees) return <Chargement />;
  const s = donnees.situation;
  const paiements = donnees.paiements.filter((p) => !filtre || (filtre === "attente" ? !p.reversement_numero : !!p.reversement_numero));

  return (
    <div className="space-y-5">
      <EnTetePage titre="Reversements PawaPay" sousTitre="Paiements Mobile Money de vos clients encaissés par adLyn, et leurs reversements à votre boutique." />

      {/* Situation */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="card p-3"><p className="text-xs text-gray-500">Encaissé pour vous</p><p className="text-xl font-extrabold">{fcfa(s.encaisse)}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">Reversé (net)</p><p className="text-xl font-extrabold text-green-700">{fcfa(s.reverse)}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">Frais retenus</p><p className="text-xl font-extrabold text-gray-600">{fcfa(s.frais)}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">En attente de reversement</p><p className={`text-xl font-extrabold ${s.a_reverser ? "text-orange-600" : ""}`}>{fcfa(s.a_reverser)}</p>
          <p className="text-xs text-gray-500">{s.nb_en_attente} paiement(s)</p></div>
      </div>

      {/* Reversements reçus */}
      <div className="card overflow-x-auto p-0">
        <h2 className="p-4 pb-2 font-bold">Reversements reçus</h2>
        <table className="table min-w-[720px]">
          <thead><tr><th>N°</th><th>Date</th><th className="text-right">Paiements</th><th className="text-right">Brut</th><th className="text-right">Frais</th><th className="text-right">Net reçu</th><th>Mode / réf.</th></tr></thead>
          <tbody>
            {donnees.reversements.map((r) => (
              <tr key={r.id} className={r.statut === "ANNULE" ? "text-gray-400 line-through" : ""}>
                <td className="font-mono text-xs">{r.numero}</td><td>{date(r.date)}</td><td className="text-right">{r.nb_paiements}</td>
                <td className="text-right">{fcfa(r.montant_brut)}</td><td className="text-right">{fcfa(r.frais)}</td>
                <td className="text-right font-semibold">{fcfa(r.montant_net)}</td>
                <td className="text-xs">{donnees.modes[r.mode] || r.mode}{r.reference && <span className="block text-gray-500">{r.reference}</span>}</td>
              </tr>
            ))}
            {donnees.reversements.length === 0 && <tr><td colSpan={7} className="text-center text-gray-500">Aucun reversement pour l'instant.</td></tr>}
          </tbody>
        </table>
      </div>

      {/* Paiements encaissés, avec leur état de reversement */}
      <div className="card overflow-x-auto p-0">
        <div className="flex flex-wrap items-center justify-between gap-2 p-4 pb-2">
          <h2 className="font-bold">Paiements Mobile Money encaissés</h2>
          <select className="input max-w-xs" value={filtre} onChange={(e) => setFiltre(e.target.value)} aria-label="Filtrer les paiements">
            <option value="">Tous</option><option value="attente">En attente de reversement</option><option value="reverses">Reversés</option>
          </select>
        </div>
        <table className="table min-w-[640px]">
          <thead><tr><th>Date</th><th>Commande / fiche</th><th>Client</th><th className="text-right">Montant</th><th>Reversement</th></tr></thead>
          <tbody>
            {paiements.map((p) => (
              <tr key={p.id}>
                <td className="whitespace-nowrap">{dateHeure(p.updated_at || p.created_at)}</td>
                <td className="font-mono text-xs">{p.commande_numero || p.fiche_numero}</td><td>{p.client_nom}</td>
                <td className="text-right">{fcfa(p.montant)}</td>
                <td>{p.reversement_numero ? <span className="badge bg-green-100 text-green-800">✓ {p.reversement_numero}</span>
                  : <span className="badge bg-orange-100 text-orange-800">En attente</span>}</td>
              </tr>
            ))}
            {paiements.length === 0 && <tr><td colSpan={5} className="text-center text-gray-500">Aucun paiement.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
