import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure, prix } from "@/lib/format";
import { STATUTS_COMMANDE, STATUTS_PAIEMENT_COMMANDE } from "@/lib/statuts";
import Badge from "@/components/Badge";
import Chargement from "@/components/Chargement";
import EnTetePage from "@/components/EnTetePage";
import { ListeVide } from "./_ventes/outils";

// Liste des commandes passées sur la vitrine en ligne, filtrable par statut.
// Le filtre est gardé dans l'adresse (?statut=RECUE).
export default function Commandes() {
  const { boutique } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const statut = params.get("statut") || "";
  const [commandes, setCommandes] = useState(null);
  const [erreur, setErreur] = useState("");
  const devise = boutique?.devise || "FCFA";

  // Chargement de la liste à chaque changement de filtre
  useEffect(() => {
    let annule = false;
    setCommandes(null);
    setErreur("");
    apiClient.get("/commandes", { params: { statut } })
      .then(({ data }) => { if (!annule) setCommandes(data); })
      .catch((err) => { if (!annule) { setCommandes([]); setErreur(messageErreur(err, "Impossible de charger les commandes")); } });
    return () => { annule = true; };
  }, [statut]);

  // Choix du filtre (vide = toutes les commandes)
  const filtrer = (v) => setParams(v ? { statut: v } : {}, { replace: true });

  return (
    <div>
      <EnTetePage titre="Commandes en ligne" sousTitre="Commandes reçues depuis votre vitrine" />

      {/* Filtre par statut : pastilles cliquables */}
      <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
        {[["", "Toutes"], ...Object.entries(STATUTS_COMMANDE).map(([k, s]) => [k, s.libelle])].map(([v, l]) => (
          <button key={l} type="button" onClick={() => filtrer(v)}
            className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-sm font-semibold ${statut === v ? "border-primary bg-primary text-white" : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"}`}>
            {l}
          </button>
        ))}
      </div>

      {erreur && <p className="card mb-4 text-red-600">{erreur}</p>}
      {!commandes ? <Chargement /> : commandes.length === 0 ? (
        !erreur && <ListeVide>Aucune commande{statut ? " avec ce statut" : " pour l'instant"}.</ListeVide>
      ) : (
        <>
          {/* Grand écran : tableau */}
          <div className="card hidden overflow-x-auto p-0 md:block">
            <table className="table">
              <thead>
                <tr><th>N°</th><th>Date</th><th>Client</th><th className="text-right">Total</th><th>Livraison</th><th>Statut</th><th>Paiement</th><th>Facture</th></tr>
              </thead>
              <tbody>
                {commandes.map((c) => (
                  <tr key={c.id} className="cursor-pointer hover:bg-gray-50" onClick={() => navigate(`/gestion/commandes/${c.id}`)}>
                    <td className="whitespace-nowrap font-semibold text-primary"><Link to={`/gestion/commandes/${c.id}`} onClick={(e) => e.stopPropagation()}>{c.numero}</Link></td>
                    <td className="whitespace-nowrap">{dateHeure(c.date)}</td>
                    <td><div className="font-medium">{c.client?.nom}</div><div className="text-xs text-gray-500">{c.client?.telephone}</div></td>
                    <td className="whitespace-nowrap text-right font-semibold">{prix(c.total, devise)}</td>
                    <td>{c.mode_livraison === "LIVRAISON" ? "🚚 Livraison" : "🏬 Retrait"}</td>
                    <td><Badge table={STATUTS_COMMANDE} statut={c.statut} /></td>
                    <td><Badge table={STATUTS_PAIEMENT_COMMANDE} statut={c.paiement?.statut} /></td>
                    <td>{c.facture_id
                      ? <Link to={`/gestion/documents/${c.facture_id}`} className="font-semibold text-primary" onClick={(e) => e.stopPropagation()}>Voir</Link>
                      : <span className="text-gray-400">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Téléphone : cartes */}
          <div className="space-y-2 md:hidden">
            {commandes.map((c) => (
              <Link key={c.id} to={`/gestion/commandes/${c.id}`} className="card block p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-bold">{c.numero}</p>
                    <p className="text-xs text-gray-500">{dateHeure(c.date)} · {c.mode_livraison === "LIVRAISON" ? "Livraison" : "Retrait"}</p>
                  </div>
                  <Badge table={STATUTS_COMMANDE} statut={c.statut} />
                </div>
                <div className="mt-2 flex items-end justify-between gap-2">
                  <span className="text-sm">{c.client?.nom}<span className="block text-xs text-gray-500">{c.client?.telephone}</span></span>
                  <span className="whitespace-nowrap font-bold">{prix(c.total, devise)}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge table={STATUTS_PAIEMENT_COMMANDE} statut={c.paiement?.statut} />
                  {c.facture_id && <span className="badge bg-blue-50 text-blue-700">Facturée</span>}
                </div>
              </Link>
            ))}
          </div>
          <p className="mt-3 text-xs text-gray-500">{commandes.length} commande(s)</p>
        </>
      )}
    </div>
  );
}
