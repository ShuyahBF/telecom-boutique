import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { date, prix } from "@/lib/format";
import { TYPES_PRODUIT } from "@/lib/statuts";
import { useAuth } from "@/context/AuthContext";
import Chargement from "@/components/Chargement";
import EnTetePage from "@/components/EnTetePage";
import Modal from "@/components/Modal";

// Catalogue public commun : le personnel y cherche les informations d'un
// téléphone (caractéristiques, pièces détachées compatibles) et voit s'il
// l'a déjà dans son propre catalogue, avec son prix.
export default function CataloguePublic() {
  const { boutique } = useAuth();
  const [filtres, setFiltres] = useState({ q: "", type_produit: "TEL", marque: "" });
  const [resultat, setResultat] = useState(null);
  const [erreur, setErreur] = useState("");
  const [ficheId, setFicheId] = useState(null);
  // Vue : fiches détaillées du catalogue public, ou référentiel mondial (tous les appareils)
  const [vue, setVue] = useState("fiches");

  // Recherche (avec un petit délai pendant la frappe)
  useEffect(() => {
    const t = setTimeout(() => {
      apiClient.get("/catalogue-public", { params: filtres })
        .then(({ data }) => { setResultat(data); setErreur(""); })
        .catch((err) => setErreur(messageErreur(err, "Recherche impossible")));
    }, 250);
    return () => clearTimeout(t);
  }, [filtres]);

  return (
    <div>
      <EnTetePage titre="Catalogue public" sousTitre="Fiches communes à toutes les boutiques, mises à jour chaque soir. Vos prix et documents restent privés." />

      {/* Choix de la vue */}
      <div className="mb-4 inline-flex rounded-xl border border-gray-200 bg-white p-1">
        {[["fiches", "📋 Fiches détaillées"], ["monde", "📚 Tous les appareils du monde"]].map(([cle, libelle]) => (
          <button key={cle} type="button" onClick={() => setVue(cle)}
            className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${vue === cle ? "bg-primary text-white" : "text-gray-600"}`}>{libelle}</button>
        ))}
      </div>

      {vue === "monde" ? <ReferentielMondial onOuvrir={setFicheId} /> : (<>

      {/* Filtres de recherche */}
      <div className="mb-4 flex flex-wrap gap-3">
        <input className="input max-w-sm" placeholder="Rechercher un modèle (ex. Galaxy A15, Spark 20)…" value={filtres.q}
          onChange={(e) => setFiltres({ ...filtres, q: e.target.value })} />
        <select className="input max-w-[12rem]" value={filtres.type_produit} onChange={(e) => setFiltres({ ...filtres, type_produit: e.target.value })}>
          <option value="">Tous les types</option>
          <option value="TEL">{TYPES_PRODUIT.TEL}</option>
          <option value="PIE">{TYPES_PRODUIT.PIE}</option>
          <option value="ACC">{TYPES_PRODUIT.ACC}</option>
        </select>
        <select className="input max-w-[12rem]" value={filtres.marque} onChange={(e) => setFiltres({ ...filtres, marque: e.target.value })}>
          <option value="">Toutes les marques</option>
          {(resultat?.marques || []).map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      {erreur && <p className="text-red-600">{erreur}</p>}
      {!resultat ? <Chargement /> : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {resultat.modeles.map((m) => (
            <button key={m.id} type="button" onClick={() => setFicheId(m.id)}
              className="card flex items-center gap-3 text-left transition hover:border-primary">
              {m.photo_url ? <img src={m.photo_url} alt="" className="h-16 w-16 shrink-0 rounded-xl object-contain" />
                : <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-xl bg-gray-100 text-2xl">📱</span>}
              <span className="min-w-0">
                <span className="block text-xs text-gray-500">{m.marque} · {TYPES_PRODUIT[m.type_produit]}</span>
                <span className="block font-semibold">{m.nom}</span>
                <span className={`badge mt-1 ${m.produit_id ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"}`}>
                  {m.produit_id ? "Dans mon catalogue" : "Pas dans mon catalogue"}
                </span>
              </span>
            </button>
          ))}
          {resultat.modeles.length === 0 && <p className="text-gray-500">Aucun modèle trouvé.</p>}
        </div>
      )}

      </>)}

      <FicheModele id={ficheId} devise={boutique?.devise} onFermer={() => setFicheId(null)} onOuvrir={setFicheId} />
    </div>
  );
}

// Fenêtre de détail d'un modèle : caractéristiques + pièces compatibles
function FicheModele({ id, devise, onFermer, onOuvrir }) {
  const [fiche, setFiche] = useState(null);

  useEffect(() => {
    setFiche(null);
    if (id) apiClient.get(`/catalogue-public/${id}`).then(({ data }) => setFiche(data)).catch(() => onFermer());
  }, [id, onFermer]);

  if (!id) return null;
  return (
    <Modal ouvert titre={fiche ? `${fiche.marque} ${fiche.nom}` : "Chargement…"} onFermer={onFermer} large>
      {!fiche ? <Chargement /> : (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-4">
            {fiche.photo_url && <img src={fiche.photo_url} alt="" className="h-40 w-40 rounded-xl border object-contain" />}
            <div className="min-w-0 flex-1 space-y-1 text-sm">
              <p className="text-gray-500">Réf. {fiche.reference}{fiche.annee_sortie ? ` · sorti en ${fiche.annee_sortie}` : ""} · fiche v{fiche.version} du {date(fiche.date_publication)}</p>
              {fiche.description && <p>{fiche.description}</p>}
              {/* Situation dans le catalogue de MA boutique */}
              {fiche.produit ? (
                <p className="rounded-xl bg-green-50 p-2 text-green-900">
                  Dans mon catalogue : {fiche.produit.prix_vente > 0 ? prix(fiche.produit.prix_vente, devise) : "prix à fixer"}
                  {fiche.type_produit !== "SER" && ` · stock ${fiche.produit.stock}`} —{" "}
                  <Link to={`/gestion/produits/${fiche.produit.id}`} className="font-semibold underline">ouvrir la fiche</Link>
                </p>
              ) : <p className="rounded-xl bg-gray-50 p-2 text-gray-600">Ce modèle n'est pas dans votre catalogue.</p>}
            </div>
          </div>

          {fiche.caracteristiques?.length > 0 && (
            <table className="table">
              <tbody>
                {fiche.caracteristiques.map((c) => {
                  const [libelle, ...valeur] = c.split(":");
                  return <tr key={c}><th className="w-1/3">{valeur.length ? libelle.trim() : ""}</th><td>{valeur.length ? valeur.join(":").trim() : c}</td></tr>;
                })}
              </tbody>
            </table>
          )}

          {/* Pour une pièce : les téléphones compatibles */}
          {fiche.compatibles?.length > 0 && (
            <div>
              <h3 className="mb-1 font-bold">Compatible avec</h3>
              <div className="flex flex-wrap gap-2">
                {fiche.compatibles.map((t) => (
                  <button key={t.id} type="button" className="badge bg-primary/10 text-primary" onClick={() => onOuvrir(t.id)}>{t.marque} {t.nom}</button>
                ))}
              </div>
            </div>
          )}

          {/* Pour un téléphone : pièces détachées et accessoires compatibles */}
          {fiche.type_produit === "TEL" && (
            <div>
              <h3 className="mb-1 font-bold">Pièces détachées et accessoires compatibles ({fiche.pieces.length})</h3>
              {fiche.pieces.length === 0 ? <p className="text-sm text-gray-500">Aucune pièce référencée pour ce modèle.</p> : (
                <table className="table">
                  <thead><tr><th>Pièce</th><th>Réf.</th><th>Chez moi</th></tr></thead>
                  <tbody>
                    {fiche.pieces.map((p) => (
                      <tr key={p.id}>
                        <td><button type="button" className="text-left font-medium text-primary" onClick={() => onOuvrir(p.id)}>{p.nom}</button></td>
                        <td className="font-mono text-xs">{p.reference}</td>
                        <td>{p.produit ? `${p.produit.prix_vente > 0 ? prix(p.produit.prix_vente, devise) : "prix à fixer"} · stock ${p.produit.stock}` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

// Recherche dans le référentiel mondial (liste officielle Google Play + iPhone) :
// identité de n'importe quel appareil (marque, nom, codes modèle), et accès à sa
// fiche détaillée quand elle a été publiée dans le catalogue public.
function ReferentielMondial({ onOuvrir }) {
  const [q, setQ] = useState("");
  const [marque, setMarque] = useState("");
  const [marques, setMarques] = useState([]);
  const [page, setPage] = useState(1);
  const [resultat, setResultat] = useState(null);

  // Liste des marques (une seule fois)
  useEffect(() => {
    apiClient.get("/referentiel/marques").then(({ data }) => setMarques(data)).catch(() => {});
  }, []);

  // Recherche, avec un petit délai pendant la frappe
  useEffect(() => {
    const t = setTimeout(() => {
      apiClient.get("/referentiel", { params: { q, marque, page } }).then(({ data }) => setResultat(data)).catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [q, marque, page]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <input className="input max-w-sm" placeholder="Nom ou code modèle (ex. Galaxy A15, SM-A155F)…" value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select className="input max-w-[14rem]" value={marque} onChange={(e) => { setMarque(e.target.value); setPage(1); }}>
          <option value="">Toutes les marques</option>
          {marques.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      {!resultat ? <Chargement /> : (
        <>
          <p className="text-sm text-gray-500">{resultat.total.toLocaleString("fr-FR")} appareil(s) — liste officielle Google Play et iPhone</p>
          <div className="card divide-y divide-gray-100 p-0">
            {resultat.appareils.map((a) => (
              <div key={a.cle} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{a.marque} {a.nom}</p>
                  <p className="truncate font-mono text-xs text-gray-500">{a.codes_modele.join(" · ") || "—"}</p>
                </div>
                {a.fiche_publiee
                  ? <button type="button" className="btn-outline btn-sm" onClick={() => onOuvrir(a.catalogue_id)}>Voir la fiche détaillée</button>
                  : <span className="w-full text-xs text-gray-400 sm:w-auto">Fiche détaillée pas encore disponible</span>}
              </div>
            ))}
            {resultat.appareils.length === 0 && <p className="p-4 text-gray-500">Aucun appareil trouvé.</p>}
          </div>
          {resultat.pages > 1 && (
            <div className="flex items-center justify-center gap-3 text-sm">
              <button type="button" className="btn-outline btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Précédent</button>
              Page {page} / {resultat.pages}
              <button type="button" className="btn-outline btn-sm" disabled={page >= resultat.pages} onClick={() => setPage(page + 1)}>Suivant →</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
