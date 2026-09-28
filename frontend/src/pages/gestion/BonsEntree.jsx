import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, prix } from "@/lib/format";
import EnTetePage from "@/components/EnTetePage";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import { Vide } from "./_atelier/communs";
import OngletsStock from "./_atelier/OngletsStock";

// Page « Bons d'entrée » : liste des réceptions fournisseur.
// Un bon non validé est un brouillon ; sa validation fait entrer la marchandise en stock.
export default function BonsEntree() {
  const { boutique } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [bons, setBons] = useState([]);
  const [chargement, setChargement] = useState(true);

  // Chargement de la liste des bons (GET /stock/bons)
  useEffect(() => {
    apiClient.get("/stock/bons")
      .then(({ data }) => setBons(data))
      .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger les bons d'entrée")))
      .finally(() => setChargement(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <EnTetePage titre="Stock" sousTitre="Réceptions de marchandises de vos fournisseurs">
        <Link to="/gestion/stock/bons/nouveau" className="btn-primary">+ Nouvelle réception</Link>
      </EnTetePage>
      <OngletsStock />

      {/* Tableau des bons ; un clic ouvre le bon */}
      <div className="card overflow-x-auto p-0">
        {chargement ? <Chargement /> : bons.length === 0 ? <Vide icone="📥">Aucune réception enregistrée pour l'instant.</Vide> : (
          <table className="table min-w-[720px]">
            <thead>
              <tr><th>N°</th><th>Date</th><th>Fournisseur</th><th>Réf. fournisseur</th><th className="text-right">Lignes</th><th className="text-right">Montant</th><th>État</th></tr>
            </thead>
            <tbody>
              {bons.map((b) => (
                <tr key={b.id} className="cursor-pointer hover:bg-gray-50" onClick={() => navigate(`/gestion/stock/bons/${b.id}`)}>
                  <td className="font-mono font-semibold">{b.numero}</td>
                  <td>{date(b.date)}</td>
                  <td className="font-medium">{b.fournisseur_nom}</td>
                  <td>{b.reference_fournisseur || "—"}</td>
                  <td className="text-right">{b.lignes?.length || 0}</td>
                  <td className="whitespace-nowrap text-right font-semibold">{prix(b.montant_total, boutique?.devise)}</td>
                  <td>{b.valide
                    ? <span className="badge bg-green-100 text-green-800">✔ Validé — en stock</span>
                    : <span className="badge bg-amber-100 text-amber-800">Non validé</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
