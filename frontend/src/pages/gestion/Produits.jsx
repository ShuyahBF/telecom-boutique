import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { peut, useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { prix } from "@/lib/format";
import { TYPES_PRODUIT } from "@/lib/statuts";
import EnTetePage from "@/components/EnTetePage";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { Vide } from "./_atelier/communs";

// Page « Catalogue » : liste des produits avec recherche et filtres,
// et gestion des catégories dans une fenêtre modale.
// Les produits reçus du catalogue PUBLIC (commun à toutes les boutiques) sont
// marqués 🌍 ; les ajouts récents portent le badge « Nouveau » et arrivent
// sans prix (« Prix à fixer ») et invisibles sur le portail.
// Filtres lisibles dans l'adresse (liens directs depuis le tableau de bord...) :
//   ?nouveau=1  -> seulement les nouveautés
//   ?sans_prix=1 -> seulement les produits sans prix de vente
//   ?source=catalogue | boutique -> origine du produit
export default function Produits() {
  const { user, boutique } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  // Le technicien consulte le catalogue sans pouvoir le modifier
  const peutModifier = peut(user, "catalogue.edition");

  // --- État de la page ---
  const [produits, setProduits] = useState([]);
  const [categories, setCategories] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [filtres, setFiltres] = useState({ q: "", categorie_id: "", type_produit: "", alerte: false });
  const [modaleCategories, setModaleCategories] = useState(false);
  // Nombre de nouveautés du catalogue public pas encore consultées (tous filtres confondus)
  const [nbNouveautes, setNbNouveautes] = useState(0);
  // Compteur augmenté pour forcer le rechargement de la liste (après « tout marquer comme vu »)
  const [rechargement, setRechargement] = useState(0);

  // --- Filtres « nouveautés / sans prix / origine » : rangés dans l'adresse ---
  // (ainsi un lien comme /gestion/produits?nouveau=1 ouvre la page déjà filtrée)
  const [params, setParams] = useSearchParams();
  const nouveau = params.get("nouveau") === "1";
  const sansPrix = params.get("sans_prix") === "1";
  const source = ["catalogue", "boutique"].includes(params.get("source")) ? params.get("source") : "";
  // Change un filtre de l'adresse (valeur vide = filtre retiré), sans ajouter
  // d'étape à l'historique du navigateur
  const majAdresse = (cle, valeur) => {
    const suivants = new URLSearchParams(params);
    if (valeur) suivants.set(cle, valeur);
    else suivants.delete(cle);
    setParams(suivants, { replace: true });
  };

  // Chargement des catégories (liste des filtres + fenêtre de gestion)
  const chargerCategories = useCallback(() => {
    apiClient.get("/categories").then(({ data }) => setCategories(data)).catch(() => {});
  }, []);
  useEffect(() => { chargerCategories(); }, [chargerCategories]);

  // Chargement des produits à chaque changement de filtre
  // (petit délai pour ne pas interroger l'API à chaque lettre tapée)
  // (undefined = paramètre non envoyé à l'API)
  useEffect(() => {
    const t = setTimeout(() => {
      apiClient.get("/produits", {
        params: {
          ...filtres, alerte: filtres.alerte || undefined,
          nouveau: nouveau || undefined, sans_prix: sansPrix || undefined, source: source || undefined,
        },
      })
        .then(({ data }) => setProduits(data))
        .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger le catalogue")))
        .finally(() => setChargement(false));
    }, 250);
    return () => clearTimeout(t);
  }, [filtres, nouveau, sansPrix, source, rechargement]); // eslint-disable-line react-hooks/exhaustive-deps

  // Nombre total de nouveautés (pour afficher le bouton « Tout marquer comme vu »)
  useEffect(() => {
    apiClient.get("/produits", { params: { nouveau: true } })
      .then(({ data }) => setNbNouveautes(data.length))
      .catch(() => {});
  }, [rechargement]);

  // Retire le badge « Nouveau » de tous les produits, puis recharge la liste
  async function toutMarquerVu() {
    try {
      const { data } = await apiClient.post("/produits/nouveautes/vues");
      toast.succes(`${data.modifies} nouveauté(s) marquée(s) comme vue(s)`);
      if (nouveau) majAdresse("nouveau", ""); // le filtre « nouveautés » n'aurait plus rien à montrer
      setRechargement((n) => n + 1);
    } catch (err) {
      toast.erreur(messageErreur(err, "Opération impossible"));
    }
  }

  const maj = (champ, valeur) => setFiltres((f) => ({ ...f, [champ]: valeur }));

  return (
    <div>
      <EnTetePage titre="Catalogue" sousTitre={`${produits.length} produit(s) affiché(s)`}>
        {/* Le catalogue public sert à chercher les infos d'un modèle (caractéristiques, pièces compatibles) */}
        <Link to="/gestion/catalogue-public" className="btn-outline">🌍 Catalogue public</Link>
        {peutModifier && (
          <>
            <button type="button" className="btn-outline" onClick={() => setModaleCategories(true)}>🗂️ Catégories</button>
            <Link to="/gestion/produits/nouveau" className="btn-primary">+ Nouveau produit</Link>
          </>
        )}
      </EnTetePage>

      {/* Barre de recherche et filtres */}
      <div className="card mb-4 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <input className="input" placeholder="🔍 Nom, référence, marque…" value={filtres.q} onChange={(e) => maj("q", e.target.value)} />
        <select className="input" value={filtres.categorie_id} onChange={(e) => maj("categorie_id", e.target.value)}>
          <option value="">Toutes les catégories</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.nom}</option>)}
        </select>
        <select className="input" value={filtres.type_produit} onChange={(e) => maj("type_produit", e.target.value)}>
          <option value="">Tous les types</option>
          {Object.entries(TYPES_PRODUIT).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
        </select>
        <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-gray-300 px-3 py-2.5 text-sm font-semibold">
          <input type="checkbox" className="h-4 w-4 accent-red-600" checked={filtres.alerte} onChange={(e) => maj("alerte", e.target.checked)} />
          ⚠️ Stock en alerte seulement
        </label>
        {/* Deuxième ligne de filtres : origine, nouveautés, produits sans prix (rangés dans l'adresse) */}
        <select className="input" value={source} onChange={(e) => majAdresse("source", e.target.value)} aria-label="Origine du produit">
          <option value="">Toutes les origines</option>
          <option value="catalogue">🌍 Catalogue public</option>
          <option value="boutique">🏪 Mes produits</option>
        </select>
        <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-gray-300 px-3 py-2.5 text-sm font-semibold">
          <input type="checkbox" className="h-4 w-4 accent-accent" checked={nouveau} onChange={(e) => majAdresse("nouveau", e.target.checked ? "1" : "")} />
          ✨ Nouveautés seulement
        </label>
        <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-gray-300 px-3 py-2.5 text-sm font-semibold">
          <input type="checkbox" className="h-4 w-4 accent-accent" checked={sansPrix} onChange={(e) => majAdresse("sans_prix", e.target.checked ? "1" : "")} />
          🏷️ Sans prix seulement
        </label>
      </div>

      {/* Bandeau des nouveautés reçues du catalogue public (affiché s'il y en a) */}
      {nbNouveautes > 0 && (
        <div className="mb-4 flex flex-col gap-3 rounded-2xl border border-orange-200 bg-orange-50 px-4 py-3 text-sm text-orange-900 sm:flex-row sm:items-center">
          <p className="flex-1">
            <b>{nbNouveautes} nouveauté(s)</b> reçue(s) du catalogue public. Elles arrivent sans prix et masquées du portail :
            fixez votre prix puis rendez-les visibles.
          </p>
          <div className="flex flex-wrap gap-2">
            {!nouveau && <button type="button" className="btn-outline btn-sm" onClick={() => majAdresse("nouveau", "1")}>Voir les nouveautés</button>}
            <button type="button" className="btn-accent btn-sm" onClick={toutMarquerVu}>✓ Tout marquer comme vu</button>
          </div>
        </div>
      )}

      {!peutModifier && (
        <p className="mb-3 rounded-xl bg-blue-50 px-4 py-2 text-sm text-blue-800">Consultation seule : seuls le DG et les commerciaux modifient le catalogue.</p>
      )}

      {/* Tableau des produits (défilement horizontal sur petit écran) */}
      <div className="card overflow-x-auto p-0">
        {chargement ? <Chargement /> : produits.length === 0 ? (
          <Vide icone="📱">Aucun produit ne correspond à votre recherche.</Vide>
        ) : (
          <>
          {/* Téléphone : une ligne compacte par produit */}
          <ul className="divide-y divide-gray-100 sm:hidden">
            {produits.map((p) => {
              const service = p.type_produit === "SER";
              const enAlerte = !service && p.stock <= p.stock_alerte;
              return (
                <li key={p.id}>
                  <Link to={`/gestion/produits/${p.id}`} className={`flex items-center gap-3 p-3 ${p.actif === false ? "opacity-50" : ""}`}>
                    {p.image_url
                      ? <img src={p.image_url} alt="" className="h-12 w-12 shrink-0 rounded-lg border object-contain" />
                      : <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-lg">📱</span>}
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <NomProduit produit={p} className="min-w-0 truncate font-semibold" avecBadge={false} />
                      </span>
                      <span className="block truncate text-xs text-gray-500">{p.reference} · {p.categorie_nom}{p.visible_portail ? "" : " · masqué du portail"}</span>
                      {/* Sur téléphone, le badge « Nouveau » est placé à côté du prix pour laisser la place au nom */}
                      <span className="flex items-center gap-2">
                        <PrixProduit produit={p} devise={boutique?.devise} className="text-sm" />
                        {p.nouveau && <span className="badge bg-accent text-white">Nouveau</span>}
                      </span>
                    </span>
                    <span className={`shrink-0 text-right text-sm font-bold ${enAlerte ? "text-red-600" : ""}`}>
                      {service ? "—" : <>{p.stock}<span className="block text-[10px] font-normal text-gray-500">en stock</span></>}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
          {/* Écran large : tableau complet */}
          <table className="table hidden min-w-[760px] sm:table">
            <thead>
              <tr>
                <th className="w-16"><span className="sr-only">Photo</span></th>
                <th>Référence</th>
                <th>Nom</th>
                <th>Catégorie</th>
                <th>Marque</th>
                <th className="text-right">Prix de vente</th>
                <th className="text-right">Stock</th>
                <th className="text-center">Portail</th>
              </tr>
            </thead>
            <tbody>
              {produits.map((p) => {
                const service = p.type_produit === "SER";
                const enAlerte = !service && p.stock <= p.stock_alerte;
                return (
                  <tr key={p.id} className={`cursor-pointer hover:bg-gray-50 ${p.actif === false ? "opacity-50" : ""}`}
                    onClick={() => navigate(`/gestion/produits/${p.id}`)}>
                    <td>
                      {p.image_url
                        ? <img src={p.image_url} alt="" className="h-11 w-11 rounded-lg border object-contain" />
                        : <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-gray-100 text-lg">📱</span>}
                    </td>
                    <td className="font-mono text-xs">{p.reference}</td>
                    <td>
                      <div className="flex flex-wrap items-center gap-1.5"><NomProduit produit={p} className="font-semibold" /></div>
                      <div className="text-xs text-gray-500">{TYPES_PRODUIT[p.type_produit]}{p.actif === false && " · inactif"}</div>
                    </td>
                    <td>{p.categorie_nom}</td>
                    <td>{p.marque || "—"}</td>
                    <td className="whitespace-nowrap text-right"><PrixProduit produit={p} devise={boutique?.devise} /></td>
                    <td className={`whitespace-nowrap text-right font-bold ${enAlerte ? "text-red-600" : ""}`}>
                      {service ? "—" : p.stock}
                      {enAlerte && <span className="ml-1" title={`Seuil d'alerte : ${p.stock_alerte}`}>⚠️</span>}
                    </td>
                    <td className="text-center">{p.visible_portail ? "✅" : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </>
        )}
      </div>

      {peutModifier && (
        <ModaleCategories ouvert={modaleCategories} onFermer={() => setModaleCategories(false)}
          categories={categories} onChange={chargerCategories} />
      )}
    </div>
  );
}

// Nom d'un produit + icône 🌍 (produit du catalogue public) + badge « Nouveau »
// (avecBadge = false : le badge est affiché ailleurs, ex. sur téléphone)
function NomProduit({ produit, className = "", avecBadge = true }) {
  return (
    <>
      {produit.catalogue_id && <span title="Fiche du catalogue public" aria-label="Catalogue public" className="shrink-0">🌍</span>}
      <span className={className}>{produit.nom}</span>
      {avecBadge && produit.nouveau && <span className="badge shrink-0 bg-accent text-white">Nouveau</span>}
    </>
  );
}

// Prix de vente, ou « Prix à fixer » en orange quand il vaut 0
function PrixProduit({ produit, devise, className = "" }) {
  if (!produit.prix_vente) return <span className={`font-semibold text-accent ${className}`}>Prix à fixer</span>;
  return <span className={`font-semibold ${className}`}>{prix(produit.prix_vente, devise)}</span>;
}

// Fenêtre de gestion des catégories : ajout, renommage, ordre, suppression.
function ModaleCategories({ ouvert, onFermer, categories, onChange }) {
  const toast = useToast();
  const [nouvelle, setNouvelle] = useState({ nom: "", ordre: 0 });
  const [edition, setEdition] = useState(null); // catégorie en cours de modification

  // Création d'une catégorie (POST /categories)
  async function creer(e) {
    e.preventDefault();
    try {
      await apiClient.post("/categories", { nom: nouvelle.nom, ordre: Number(nouvelle.ordre) || 0 });
      setNouvelle({ nom: "", ordre: 0 });
      toast.succes("Catégorie créée");
      onChange();
    } catch (err) {
      toast.erreur(messageErreur(err, "Nom de catégorie invalide"));
    }
  }

  // Enregistrement d'une catégorie modifiée (PUT /categories/{id})
  async function enregistrer() {
    try {
      await apiClient.put(`/categories/${edition.id}`, { nom: edition.nom, ordre: Number(edition.ordre) || 0 });
      setEdition(null);
      toast.succes("Catégorie modifiée");
      onChange();
    } catch (err) {
      toast.erreur(messageErreur(err, "Nom de catégorie invalide"));
    }
  }

  // Suppression (refusée par l'API si des produits l'utilisent encore)
  async function supprimer(c) {
    if (!window.confirm(`Supprimer la catégorie « ${c.nom} » ?`)) return;
    try {
      await apiClient.delete(`/categories/${c.id}`);
      toast.succes("Catégorie supprimée");
      onChange();
    } catch (err) {
      toast.erreur(messageErreur(err, "Suppression impossible"));
    }
  }

  return (
    <Modal ouvert={ouvert} titre="Catégories du catalogue" onFermer={onFermer}>
      {/* Formulaire d'ajout */}
      <form onSubmit={creer} className="mb-2 flex gap-2">
        <input className="input" placeholder="Nouvelle catégorie (ex. Smartphones)" required value={nouvelle.nom}
          onChange={(e) => setNouvelle({ ...nouvelle, nom: e.target.value })} />
        <input className="input w-20 shrink-0" type="number" title="Ordre d'affichage" aria-label="Ordre d'affichage" value={nouvelle.ordre}
          onChange={(e) => setNouvelle({ ...nouvelle, ordre: e.target.value })} />
        <button className="btn-primary shrink-0">Ajouter</button>
      </form>
      <p className="mb-3 text-xs text-gray-500">Le nombre est l'ordre d'affichage sur le portail (les plus petits d'abord).</p>

      {/* Liste des catégories existantes */}
      <ul className="divide-y divide-gray-100 rounded-xl border border-gray-200">
        {categories.length === 0 && <li className="p-3 text-sm text-gray-500">Aucune catégorie pour l'instant.</li>}
        {categories.map((c) => (
          <li key={c.id} className="flex items-center gap-2 p-2">
            {edition?.id === c.id ? (
              <>
                <input className="input py-1.5" value={edition.nom} onChange={(e) => setEdition({ ...edition, nom: e.target.value })} />
                <input className="input w-16 shrink-0 py-1.5" type="number" value={edition.ordre} onChange={(e) => setEdition({ ...edition, ordre: e.target.value })} />
                <button type="button" className="btn-primary btn-sm" onClick={enregistrer}>OK</button>
                <button type="button" className="btn-sm text-gray-500" onClick={() => setEdition(null)} aria-label="Annuler">✕</button>
              </>
            ) : (
              <>
                <span className="w-8 text-center text-xs text-gray-400">{c.ordre}</span>
                <span className="flex-1 font-medium">{c.nom}</span>
                <button type="button" className="btn-outline btn-sm" onClick={() => setEdition({ ...c })}>Modifier</button>
                <button type="button" className="btn-sm rounded-lg text-red-600 hover:bg-red-50" onClick={() => supprimer(c)} aria-label="Supprimer">🗑️</button>
              </>
            )}
          </li>
        ))}
      </ul>
    </Modal>
  );
}
