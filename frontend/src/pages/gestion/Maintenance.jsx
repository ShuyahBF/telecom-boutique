import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { aujourdhui, date } from "@/lib/format";
import { STATUTS_SAV } from "@/lib/statuts";
import EnTetePage from "@/components/EnTetePage";
import Chargement from "@/components/Chargement";
import Badge from "@/components/Badge";
import { useToast } from "@/components/Toast";
import { Vide } from "./_atelier/communs";

// Statuts où l'appareil n'est plus « en retard » (réparation terminée)
const TERMINES = ["PRET", "IRREPARABLE", "RESTITUE"];

// Page « Maintenance (SAV) » : liste des dossiers de réparation.
export default function Maintenance() {
  const navigate = useNavigate();
  const toast = useToast();

  // --- État ---
  const [dossiers, setDossiers] = useState([]);
  const [chargement, setChargement] = useState(true);
  // filtre : "en_cours" (par défaut), "tous", ou un code de statut (RECU, PRET...)
  const [filtre, setFiltre] = useState("en_cours");
  const [recherche, setRecherche] = useState("");

  // Chargement des dossiers selon le filtre et la recherche (GET /maintenance)
  useEffect(() => {
    const params = { q: recherche };
    if (filtre === "en_cours") params.en_cours = true;
    else if (filtre !== "tous") params.statut = filtre;
    const t = setTimeout(() => {
      apiClient.get("/maintenance", { params })
        .then(({ data }) => setDossiers(data))
        .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger les dossiers")))
        .finally(() => setChargement(false));
    }, 250);
    return () => clearTimeout(t);
  }, [filtre, recherche]); // eslint-disable-line react-hooks/exhaustive-deps

  const jour = aujourdhui();
  // Pastilles de filtre rapide
  const pastilles = [["en_cours", "En cours"], ...Object.entries(STATUTS_SAV).map(([k, v]) => [k, v.libelle]), ["tous", "Tous"]];

  return (
    <div>
      <EnTetePage titre="Maintenance (SAV)" sousTitre="Appareils déposés en réparation">
        <Link to="/gestion/maintenance/nouveau" className="btn-primary">+ Nouveau dépôt</Link>
      </EnTetePage>

      {/* Filtres : pastilles de statut (défilent sur mobile) + recherche */}
      <div className="-mx-1 mb-3 flex gap-2 overflow-x-auto px-1 pb-1">
        {pastilles.map(([code, libelle]) => (
          <button key={code} type="button" onClick={() => setFiltre(code)}
            className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-sm font-semibold transition ${
              filtre === code ? "border-primary bg-primary text-white" : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"}`}>
            {libelle}
          </button>
        ))}
      </div>
      <input className="input mb-4 sm:max-w-md" placeholder="🔍 N° de dossier, IMEI, modèle, nom ou téléphone du client…" value={recherche} onChange={(e) => setRecherche(e.target.value)} />

      {/* Tableau des dossiers ; un clic ouvre la fiche */}
      <div className="card overflow-x-auto p-0">
        {chargement ? <Chargement /> : dossiers.length === 0 ? <Vide icone="🔧">Aucun dossier ne correspond.</Vide> : (
          <>
          {/* Téléphone : une carte compacte par dossier */}
          <ul className="divide-y divide-gray-100 sm:hidden">
            {dossiers.map((d) => {
              const enRetard = d.date_prevue && d.date_prevue < jour && !TERMINES.includes(d.statut);
              return (
                <li key={d.id}>
                  <Link to={`/gestion/maintenance/${d.id}`} className="block space-y-1 p-3">
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-mono text-sm font-semibold">{d.numero}</span>
                      <Badge table={STATUTS_SAV} statut={d.statut} />
                    </span>
                    <span className="block font-semibold">{d.marque} {d.modele}</span>
                    <span className="block text-sm text-gray-600">{d.client?.nom} · {d.client?.telephone}</span>
                    <span className="block text-xs text-gray-500">
                      Déposé le {date(d.date_depot)}
                      {d.date_prevue && <span className={enRetard ? "font-bold text-red-600" : ""}> · prévu le {date(d.date_prevue)}{enRetard && " ⏰"}</span>}
                      {d.technicien_nom && ` · ${d.technicien_nom}`}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
          {/* Écran large : tableau */}
          <table className="table hidden min-w-[860px] sm:table">
            <thead><tr><th>N° dossier</th><th>Dépôt</th><th>Client</th><th>Appareil</th><th>Statut</th><th>Technicien</th><th>Prévu le</th></tr></thead>
            <tbody>
              {dossiers.map((d) => {
                // En retard : date prévue dépassée et réparation pas terminée
                const enRetard = d.date_prevue && d.date_prevue < jour && !TERMINES.includes(d.statut);
                return (
                  <tr key={d.id} className="cursor-pointer hover:bg-gray-50" onClick={() => navigate(`/gestion/maintenance/${d.id}`)}>
                    <td className="whitespace-nowrap font-mono font-semibold">{d.numero}</td>
                    <td className="whitespace-nowrap">{date(d.date_depot)}</td>
                    <td><div className="font-medium">{d.client?.nom}</div><div className="text-xs text-gray-500">{d.client?.telephone}</div></td>
                    <td><div className="font-medium">{d.marque} {d.modele}</div>{d.imei && <div className="font-mono text-xs text-gray-500">IMEI {d.imei}</div>}</td>
                    <td><Badge table={STATUTS_SAV} statut={d.statut} /></td>
                    <td>{d.technicien_nom || <span className="text-gray-400">Non attribué</span>}</td>
                    <td className={`whitespace-nowrap ${enRetard ? "font-bold text-red-600" : ""}`}>{date(d.date_prevue)}{enRetard && " ⏰"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </>
        )}
      </div>
    </div>
  );
}
