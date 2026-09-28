import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { prix } from "@/lib/format";
import { changerQuantite, lirePanier } from "@/lib/panier";
import VisuelProduit from "./_composants/VisuelProduit";

// PANIER (/b/:slug/panier) : liste des articles choisis, modification des
// quantités, total et bouton « Commander ». Le panier est rangé dans le
// navigateur du client (voir lib/panier.js).
export default function Panier() {
  const { boutique } = useOutletContext();
  const navigate = useNavigate();

  // Contenu du panier : { produit_id: { produit, quantite } }
  const [panier, setPanier] = useState(() => lirePanier(boutique.slug));

  // On relit le panier à chaque modification (ici ou dans un autre onglet de la page)
  useEffect(() => {
    const maj = () => setPanier(lirePanier(boutique.slug));
    maj();
    window.addEventListener("panier-change", maj);
    return () => window.removeEventListener("panier-change", maj);
  }, [boutique.slug]);

  const lignes = Object.values(panier);
  const total = lignes.reduce((s, l) => s + l.produit.prix_vente * l.quantite, 0);
  const nbArticles = lignes.reduce((s, l) => s + l.quantite, 0);

  // Panier vide : message + lien vers le catalogue
  if (lignes.length === 0) {
    return (
      <div className="card mx-auto max-w-md py-12 text-center">
        <p className="text-5xl">🛒</p>
        <h1 className="mt-3 text-xl font-bold">Votre panier est vide</h1>
        <p className="mt-1 text-gray-500">Parcourez notre catalogue et ajoutez les produits qui vous plaisent.</p>
        <Link to={`/b/${boutique.slug}`} className="btn-boutique mt-5">Voir le catalogue</Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-extrabold">Mon panier</h1>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* ---------- Liste des articles ---------- */}
        <ul className="space-y-3">
          {lignes.map(({ produit, quantite }) => {
            const max = produit.stock_max; // null = pas de limite de stock
            return (
              <li key={produit.id} className="flex gap-3 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm">
                {/* Vignette cliquable vers la fiche produit */}
                <Link to={`/b/${boutique.slug}/produit/${produit.slug}`} className="shrink-0">
                  <VisuelProduit produit={produit} tailleEmoji="text-3xl" className="h-20 w-20 rounded-xl border border-gray-100" />
                </Link>
                <div className="flex min-w-0 flex-1 flex-col">
                  <div className="flex items-start justify-between gap-2">
                    <Link to={`/b/${boutique.slug}/produit/${produit.slug}`} className="line-clamp-2 font-semibold leading-snug hover:text-boutique">
                      {produit.nom}
                    </Link>
                    {/* Retirer l'article (quantité 0) */}
                    <button type="button" className="shrink-0 rounded-lg p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                      onClick={() => changerQuantite(boutique.slug, produit.id, 0)} aria-label={`Retirer ${produit.nom}`}>
                      🗑️
                    </button>
                  </div>
                  <p className="text-sm text-gray-500">{prix(produit.prix_vente, boutique.devise)} l'unité</p>
                  <div className="mt-auto flex items-center justify-between gap-2 pt-2">
                    {/* Boutons − / + pour changer la quantité */}
                    <div className="flex items-center rounded-xl border border-gray-300">
                      <button type="button" className="px-3 py-1 text-lg font-bold"
                        onClick={() => changerQuantite(boutique.slug, produit.id, quantite - 1)} aria-label="Diminuer">−</button>
                      <span className="w-8 text-center font-bold">{quantite}</span>
                      <button type="button" className="px-3 py-1 text-lg font-bold disabled:opacity-30" disabled={max != null && quantite >= max}
                        onClick={() => changerQuantite(boutique.slug, produit.id, quantite + 1)} aria-label="Augmenter">+</button>
                    </div>
                    <p className="font-extrabold text-accent">{prix(produit.prix_vente * quantite, boutique.devise)}</p>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>

        {/* ---------- Récapitulatif et bouton Commander ---------- */}
        <aside className="card h-fit space-y-3 lg:sticky lg:top-24">
          <div className="flex justify-between text-gray-600">
            <span>{nbArticles} article{nbArticles > 1 ? "s" : ""}</span>
            <span>{prix(total, boutique.devise)}</span>
          </div>
          <div className="flex items-baseline justify-between border-t border-gray-100 pt-3">
            <span className="font-bold">Total</span>
            <span className="text-2xl font-extrabold text-accent">{prix(total, boutique.devise)}</span>
          </div>
          <p className="text-xs text-gray-500">Les prix et la disponibilité sont confirmés par la boutique au moment de la commande.</p>
          <button type="button" className="btn-boutique w-full py-3 text-base" onClick={() => navigate(`/b/${boutique.slug}/commander`)}>
            Commander →
          </button>
          <Link to={`/b/${boutique.slug}`} className="block text-center text-sm font-semibold text-boutique">← Continuer mes achats</Link>
        </aside>
      </div>
    </div>
  );
}
