import { Link } from "react-router-dom";
import { dateHeure, montant } from "@/lib/format";
import { CANAUX, COULEURS_STATUTS } from "./outils";

// Liste des paiements : un tableau sur ordinateur (et à l'impression),
// des cartes empilées sur téléphone.
// - entrees : lignes renvoyées par GET /journal-paiements
// - statuts : libellés des statuts { SUCCES: "Réussi", … }
// - liens : { factures, commandes } = l'utilisateur a le droit d'ouvrir ces fiches
//   (le comptable, par exemple, n'a pas accès aux commandes en ligne)
export default function ListePaiements({ entrees, statuts, liens = {} }) {
  return (
    <>
      {/* Tableau : écrans moyens et grands, et toujours à l'impression */}
      <div className="card hidden overflow-x-auto p-0 md:block print:block print:border-0 print:shadow-none">
        <table className="table min-w-[860px] print:min-w-0 print:text-xs">
          <thead>
            <tr>
              <th>Date</th><th>Mode · canal</th><th>Objet · client</th>
              <th className="text-right">Montant</th><th>Statut</th><th>Référence</th><th className="whitespace-nowrap">Saisi par</th>
            </tr>
          </thead>
          <tbody>
            {entrees.map((e) => (
              <tr key={e.id} className={e.statut === "SUCCES" ? "" : "bg-gray-50/60"}>
                <td className="whitespace-nowrap">{dateHeure(e.date)}</td>
                {/* Mode de paiement, et en dessous le canal (caisse ou en ligne) */}
                <td>
                  <p className="font-semibold">{e.mode_libelle}</p>
                  <p className="text-xs text-gray-500">{CANAUX[e.canal] || e.canal}</p>
                </td>
                {/* Objet (lien vers la facture / la commande), et en dessous le client */}
                <td>
                  <Objet entree={e} liens={liens} />
                  <p className="text-xs text-gray-500">{e.client_nom || "—"}</p>
                </td>
                <td className={`whitespace-nowrap text-right font-semibold ${montantBarre(e) ? "text-gray-400 line-through" : ""}`}>
                  {montant(e.montant)} {e.devise}
                </td>
                <td>
                  <StatutPaiement statut={e.statut} statuts={statuts} />
                  {/* Motif : raison d'un échec ou d'une annulation */}
                  {e.motif && <p className="mt-1 max-w-[14rem] text-xs text-gray-500">{e.motif}</p>}
                </td>
                <td className="max-w-[9rem] break-all font-mono text-xs">{e.reference || "—"}</td>
                <td>{e.saisi_par || (e.canal === "PAWAPAY" ? "Client (en ligne)" : "—")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Cartes : téléphone uniquement (masquées à l'impression) */}
      <div className="space-y-3 md:hidden print:hidden">
        {entrees.map((e) => (
          <div key={e.id} className="card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className={`text-lg font-extrabold ${montantBarre(e) ? "text-gray-400 line-through" : ""}`}>{montant(e.montant)} {e.devise}</p>
                <p className="text-xs text-gray-500">{dateHeure(e.date)}</p>
              </div>
              <StatutPaiement statut={e.statut} statuts={statuts} />
            </div>
            <p className="mt-2 text-sm"><b>{e.mode_libelle}</b> <span className="text-gray-500">· {CANAUX[e.canal] || e.canal}</span></p>
            <p className="text-sm"><Objet entree={e} liens={liens} />{e.client_nom && <span className="text-gray-500"> · {e.client_nom}</span>}</p>
            {e.motif && <p className="mt-1 text-xs text-gray-600">Motif : {e.motif}</p>}
            <p className="mt-1 text-xs text-gray-500">
              {e.reference ? <>Réf. <span className="break-all font-mono">{e.reference}</span> · </> : null}
              {e.saisi_par ? `saisi par ${e.saisi_par}` : e.canal === "PAWAPAY" ? "payé en ligne par le client" : ""}
            </p>
          </div>
        ))}
      </div>
    </>
  );
}

// Un paiement qui n'a pas abouti (échoué ou annulé) n'est pas encaissé : montant barré
function montantBarre(e) {
  return e.statut === "ECHEC" || e.statut === "ANNULE";
}

// Pastille colorée du statut (Réussi, Échoué, En attente, Annulé)
function StatutPaiement({ statut, statuts }) {
  return <span className={`badge whitespace-nowrap ${COULEURS_STATUTS[statut] || "bg-gray-100 text-gray-700"}`}>{statuts[statut] || statut}</span>;
}

// Objet du paiement, cliquable vers la facture ou la commande concernée
// (texte simple si l'utilisateur n'a pas le droit d'ouvrir la fiche)
function Objet({ entree, liens }) {
  const texte = entree.objet || "—";
  if (entree.document_id && liens.factures) return <Link to={`/gestion/documents/${entree.document_id}`} className="font-semibold text-primary hover:underline">{texte}</Link>;
  if (entree.commande_id && liens.commandes) return <Link to={`/gestion/commandes/${entree.commande_id}`} className="font-semibold text-primary hover:underline">{texte}</Link>;
  return <span>{texte}</span>;
}
