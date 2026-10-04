import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, prix } from "@/lib/format";
import { STATUTS_DOCUMENT } from "@/lib/statuts";
import Badge from "@/components/Badge";
import Chargement from "@/components/Chargement";
import EnTetePage from "@/components/EnTetePage";
import { BadgePaiement, libelleType, ListeVide, numeroDocument } from "./_ventes/outils";
import ConversionProforma from "./_ventes/ConversionProforma";

// Onglets de la liste : [valeur du filtre type_document, libellé]
const ONGLETS = [["", "Toutes"], ["FAC", "Factures"], ["PRO", "Proformas"]];

// Pastille « Convertie » : proforma qui a déjà donné une facture
function BadgeConvertie() {
  return <span className="badge bg-indigo-100 text-indigo-800" title="Cette proforma a été convertie en facture">Convertie</span>;
}

// Liste des factures et proformas, avec onglets, filtre de statut et recherche.
// Une proforma en cours ou acceptée, pas encore convertie, a son bouton
// « Convertir en facture » directement dans la liste.
// Les filtres sont gardés dans l'adresse (?type=FAC&statut=VALIDE&q=...) :
// on y revient avec « Précédent », et le tableau de bord peut y envoyer directement.
export default function Documents() {
  const { boutique } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const type = params.get("type") || "";
  const statut = params.get("statut") || "";
  const q = params.get("q") || "";

  const [recherche, setRecherche] = useState(q); // texte tapé (appliqué avec un petit délai)
  const [documents, setDocuments] = useState(null);
  const [erreur, setErreur] = useState("");
  const [aConvertir, setAConvertir] = useState(null); // proforma dont on ouvre la fenêtre de conversion
  const devise = boutique?.devise || "FCFA";

  // Modifie un filtre dans l'adresse (valeur vide = filtre retiré)
  function changerFiltre(nom, valeur) {
    setParams((precedents) => {
      const p = new URLSearchParams(precedents);
      if (valeur) p.set(nom, valeur);
      else p.delete(nom);
      return p;
    }, { replace: true });
  }

  // Recherche : on attend 300 ms après la dernière frappe avant d'interroger le serveur
  useEffect(() => {
    const t = setTimeout(() => {
      setParams((precedents) => {
        const p = new URLSearchParams(precedents);
        if (recherche.trim()) p.set("q", recherche.trim());
        else p.delete("q");
        return p;
      }, { replace: true });
    }, 300);
    return () => clearTimeout(t);
  }, [recherche, setParams]);

  // Chargement de la liste à chaque changement de filtre
  useEffect(() => {
    let annule = false; // évite d'afficher une réponse arrivée trop tard
    setDocuments(null);
    setErreur("");
    apiClient.get("/documents", { params: { type_document: type, statut, q } })
      .then(({ data }) => { if (!annule) setDocuments(data); })
      .catch((err) => { if (!annule) { setDocuments([]); setErreur(messageErreur(err, "Impossible de charger les documents")); } });
    return () => { annule = true; };
  }, [type, statut, q]);

  return (
    <div>
      <EnTetePage titre="Factures & proformas" sousTitre="Documents de vente de la boutique">
        <Link to="/gestion/documents/nouveau?type=FAC" className="btn-primary btn-sm">+ Nouvelle facture</Link>
        <Link to="/gestion/documents/nouveau?type=PRO" className="btn-outline btn-sm">+ Nouvelle proforma</Link>
      </EnTetePage>

      {/* Barre de filtres : onglets, statut, recherche */}
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center">
        <div className="flex rounded-xl border border-gray-200 bg-white p-1">
          {ONGLETS.map(([v, l]) => (
            <button key={l} type="button" onClick={() => changerFiltre("type", v)}
              className={`flex-1 rounded-lg px-4 py-1.5 text-sm font-semibold md:flex-none ${type === v ? "bg-primary text-white" : "text-gray-600 hover:bg-gray-100"}`}>
              {l}
            </button>
          ))}
        </div>
        <select className="input md:w-48" value={statut} onChange={(e) => changerFiltre("statut", e.target.value)} aria-label="Statut">
          <option value="">Tous les statuts</option>
          {Object.entries(STATUTS_DOCUMENT).filter(([k]) => k !== "EN_VALIDATION").map(([k, s]) => <option key={k} value={k}>{s.libelle}</option>)}
        </select>
        <input className="input md:flex-1" type="search" placeholder="Rechercher (n°, client, téléphone, objet)…" value={recherche}
          onChange={(e) => setRecherche(e.target.value)} />
      </div>

      {erreur && <p className="card mb-4 text-red-600">{erreur}</p>}
      {!documents ? <Chargement /> : documents.length === 0 ? (
        !erreur && <ListeVide>Aucun document ne correspond à ces critères.</ListeVide>
      ) : (
        <>
          {/* Grand écran : tableau (clic sur une ligne = ouvrir le document) */}
          <div className="card hidden overflow-x-auto p-0 md:block">
            <table className="table">
              <thead>
                <tr><th>N°</th><th>Type</th><th>Date</th><th>Client</th><th className="text-right">Total TTC</th><th>Statut</th><th>Paiement</th><th className="no-print">Actions</th></tr>
              </thead>
              <tbody>
                {documents.map((d) => (
                  <tr key={d.id} className="cursor-pointer hover:bg-gray-50" onClick={() => navigate(`/gestion/documents/${d.id}`)}>
                    <td className="whitespace-nowrap font-semibold">
                      <Link to={`/gestion/documents/${d.id}`} className={d.numero ? "text-primary" : "italic text-gray-500"} onClick={(e) => e.stopPropagation()}>{numeroDocument(d)}</Link>
                    </td>
                    <td>{libelleType(d.type_document)}</td>
                    <td className="whitespace-nowrap">{date(d.date)}</td>
                    <td><div className="font-medium">{d.client?.nom}</div><div className="text-xs text-gray-500">{d.objet || d.client?.telephone}</div></td>
                    <td className="whitespace-nowrap text-right font-semibold">{prix(d.total_ttc, devise)}</td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        <Badge table={STATUTS_DOCUMENT} statut={d.statut} />
                        {d.convertie && <BadgeConvertie />}
                      </div>
                    </td>
                    <td>{d.type_document === "FAC" && d.statut !== "ANNULE" ? <BadgePaiement libelle={d.statut_paiement} /> : <span className="text-gray-400">—</span>}</td>
                    {/* Action rapide : conversion d'une proforma (le clic ne doit pas ouvrir la ligne) */}
                    <td className="no-print whitespace-nowrap">
                      {d.convertible && (
                        <button type="button" className="btn-primary btn-sm" onClick={(e) => { e.stopPropagation(); setAConvertir(d); }}>
                          → Convertir en facture
                        </button>
                      )}
                      {d.convertie && d.facture_generee_id && d.facture_generee_id !== "EN_COURS" && (
                        <Link to={`/gestion/documents/${d.facture_generee_id}`} className="text-sm font-semibold text-primary underline" onClick={(e) => e.stopPropagation()}>
                          Voir la facture
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Téléphone : cartes empilées */}
          <div className="space-y-2 md:hidden">
            {documents.map((d) => (
              <div key={d.id} className="card p-4">
              <Link to={`/gestion/documents/${d.id}`} className="block">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className={`font-bold ${d.numero ? "" : "italic text-gray-500"}`}>{numeroDocument(d)}</p>
                    <p className="text-xs text-gray-500">{libelleType(d.type_document)} · {date(d.date)}</p>
                  </div>
                  <Badge table={STATUTS_DOCUMENT} statut={d.statut} />
                </div>
                <div className="mt-2 flex items-end justify-between gap-2">
                  <span className="text-sm">{d.client?.nom}</span>
                  <span className="whitespace-nowrap font-bold">{prix(d.total_ttc, devise)}</span>
                </div>
                {d.type_document === "FAC" && d.statut !== "ANNULE" && <div className="mt-2"><BadgePaiement libelle={d.statut_paiement} /></div>}
                {d.convertie && <div className="mt-2"><BadgeConvertie /></div>}
              </Link>
              {d.convertible && (
                <button type="button" className="btn-primary btn-sm mt-3 w-full" onClick={() => setAConvertir(d)}>→ Convertir en facture</button>
              )}
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-gray-500">{documents.length} document(s)</p>
        </>
      )}

      {/* Fenêtre de conversion d'une proforma (ouverte depuis la liste) */}
      {aConvertir && <ConversionProforma proforma={aConvertir} devise={devise} onFermer={() => setAConvertir(null)} />}
    </div>
  );
}
