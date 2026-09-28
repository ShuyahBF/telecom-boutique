import { useEffect, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import Chargement from "@/components/Chargement";
import CarteProduit from "./_composants/CarteProduit";

// Choix de tri proposés au client (valeur envoyée à l'API -> libellé affiché)
const TRIS = [
  ["recent", "Nouveautés"],
  ["prix_asc", "Prix croissant"],
  ["prix_desc", "Prix décroissant"],
  ["nom", "Nom (A → Z)"],
];

// VITRINE d'une boutique (/b/:slug) : catalogue avec recherche, filtres, tri
// et pagination. Les filtres sont gardés dans l'adresse (?q=&categorie=...)
// pour qu'un lien partagé ou le bouton « retour » retrouve la même sélection.
export default function Vitrine() {
  const { boutique } = useOutletContext();
  const [params, setParams] = useSearchParams();

  // Filtres lus dans l'adresse de la page
  const q = params.get("q") || "";
  const categorie = params.get("categorie") || "";
  const marque = params.get("marque") || "";
  const tri = params.get("tri") || "recent";
  const page = Number(params.get("page")) || 1;

  // Texte tapé dans la recherche (envoyé seulement à la validation)
  const [saisie, setSaisie] = useState(q);
  // Réponse de l'API : { total, page, pages, produits } ; null = chargement
  const [resultat, setResultat] = useState(null);
  const [erreur, setErreur] = useState("");

  // Si l'adresse change (bouton retour...), on remet le texte de recherche à jour
  useEffect(() => setSaisie(q), [q]);

  // Chargement des produits à chaque changement de filtre
  useEffect(() => {
    let actif = true; // évite d'afficher une réponse arrivée après un nouveau filtre
    setResultat(null);
    setErreur("");
    apiClient.get(`/public/b/${boutique.slug}/produits`, { params: { q, categorie, marque, tri, page } })
      .then(({ data }) => actif && setResultat(data))
      .catch((err) => actif && setErreur(messageErreur(err, "Impossible de charger le catalogue")));
    return () => { actif = false; };
  }, [boutique.slug, q, categorie, marque, tri, page]);

  // Modifie un filtre dans l'adresse (et revient à la page 1 sauf si on change de page)
  const changer = (cle, valeur) => {
    const suivants = new URLSearchParams(params);
    if (valeur) suivants.set(cle, valeur);
    else suivants.delete(cle);
    if (cle !== "page") suivants.delete("page");
    setParams(suivants);
    if (cle === "page") window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const filtresActifs = Boolean(q || categorie || marque);
  const base = `/b/${boutique.slug}`;

  return (
    <div className="space-y-6">
      {/* ---------- Bandeau de la boutique : slogan + raccourcis ---------- */}
      <section className="relative overflow-hidden rounded-3xl bg-boutique px-5 py-6 text-white shadow sm:px-8 sm:py-8">
        <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10" />
        <div className="pointer-events-none absolute -bottom-16 right-24 h-32 w-32 rounded-full bg-white/10" />
        <p className="relative text-sm font-semibold text-white/80">Bienvenue chez {boutique.nom}</p>
        <h1 className="relative mt-1 text-2xl font-extrabold leading-tight sm:text-3xl">
          {boutique.slogan || "Téléphones, accessoires et réparations"}
        </h1>
        {boutique.ville && <p className="relative mt-1 text-sm text-white/80">📍 {boutique.ville}</p>}
        {/* Raccourcis vers les services les plus demandés */}
        <div className="relative mt-5 grid grid-cols-3 gap-2 sm:flex sm:flex-wrap">
          {[
            [`${base}/suivi-commande`, "📦", "Suivre ma commande"],
            [`${base}/suivi-reparation`, "🔧", "Suivre ma réparation"],
            [`${base}/conseil`, "💬", "Demander conseil"],
          ].map(([vers, emoji, texte]) => (
            <Link
              key={vers}
              to={vers}
              className="flex flex-col items-center gap-1 rounded-2xl bg-white/15 px-2 py-3 text-center text-xs font-semibold backdrop-blur hover:bg-white/25 sm:flex-row sm:px-4 sm:py-2 sm:text-sm"
            >
              <span className="text-xl sm:text-base">{emoji}</span>{texte}
            </Link>
          ))}
        </div>
      </section>

      {/* ---------- Recherche + filtres ---------- */}
      <section className="space-y-3">
        {/* Champ de recherche (validé par Entrée ou le bouton) */}
        <form
          className="flex gap-2"
          onSubmit={(e) => { e.preventDefault(); changer("q", saisie.trim()); }}
        >
          <input
            className="input flex-1"
            type="search"
            placeholder="Rechercher un produit…"
            value={saisie}
            onChange={(e) => setSaisie(e.target.value)}
            aria-label="Rechercher un produit"
          />
          <button type="submit" className="btn-boutique">🔍<span className="hidden sm:inline">Rechercher</span></button>
        </form>

        {/* Rayons (catégories) sous forme de pastilles qui défilent horizontalement sur mobile */}
        {boutique.categories?.length > 0 && (
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <Pastille actif={!categorie} onClick={() => changer("categorie", "")}>Tout</Pastille>
            {boutique.categories.map((c) => (
              <Pastille key={c.id} actif={categorie === c.id} onClick={() => changer("categorie", c.id)}>{c.nom}</Pastille>
            ))}
          </div>
        )}

        {/* Marque et tri, côte à côte */}
        <div className="grid grid-cols-2 gap-2 sm:flex sm:justify-end">
          <select className="input sm:w-52" value={marque} onChange={(e) => changer("marque", e.target.value)} aria-label="Marque">
            <option value="">Toutes les marques</option>
            {boutique.marques?.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <select className="input sm:w-52" value={tri} onChange={(e) => changer("tri", e.target.value)} aria-label="Trier par">
            {TRIS.map(([valeur, libelle]) => <option key={valeur} value={valeur}>{libelle}</option>)}
          </select>
        </div>
      </section>

      {/* ---------- Résultats ---------- */}
      <section>
        {erreur && <p className="card text-red-600">{erreur}</p>}
        {!erreur && resultat === null && <Chargement texte="Chargement du catalogue…" />}

        {resultat && (
          <>
            {/* Nombre de produits trouvés + effacement des filtres */}
            <div className="mb-3 flex items-center justify-between text-sm text-gray-500">
              <span>{resultat.total} produit{resultat.total > 1 ? "s" : ""}</span>
              {filtresActifs && (
                <button type="button" className="font-semibold text-boutique" onClick={() => setParams(tri !== "recent" ? { tri } : {})}>
                  Effacer les filtres ✕
                </button>
              )}
            </div>

            {/* Aucun produit */}
            {resultat.produits.length === 0 ? (
              <div className="card py-10 text-center">
                <p className="text-4xl">🔎</p>
                <p className="mt-2 font-semibold">Aucun produit ne correspond à votre recherche.</p>
                <p className="mt-1 text-sm text-gray-500">
                  Vous ne trouvez pas ?{" "}
                  <Link to={`${base}/conseil`} className="font-semibold text-boutique">Demandez-nous conseil</Link>.
                </p>
              </div>
            ) : (
              /* Grille de produits : 2 colonnes sur téléphone, jusqu'à 4 sur ordinateur */
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4">
                {resultat.produits.map((p) => <CarteProduit key={p.id} produit={p} boutique={boutique} />)}
              </div>
            )}

            {/* Pagination : précédente / n° de page / suivante */}
            {resultat.pages > 1 && (
              <nav className="mt-6 flex items-center justify-center gap-3" aria-label="Pagination">
                <button type="button" className="btn-outline btn-sm" disabled={page <= 1} onClick={() => changer("page", String(page - 1))}>
                  ← Précédente
                </button>
                <span className="text-sm text-gray-600">Page {resultat.page} / {resultat.pages}</span>
                <button type="button" className="btn-outline btn-sm" disabled={page >= resultat.pages} onClick={() => changer("page", String(page + 1))}>
                  Suivante →
                </button>
              </nav>
            )}
          </>
        )}
      </section>
    </div>
  );
}

// Pastille cliquable d'un rayon (pleine à la couleur de la boutique si sélectionnée)
function Pastille({ actif, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`shrink-0 whitespace-nowrap rounded-full px-4 py-2 text-sm font-semibold transition ${
        actif ? "bg-boutique text-white shadow" : "border border-gray-200 bg-white text-gray-700 hover:bg-gray-100"
      }`}
    >
      {children}
    </button>
  );
}
