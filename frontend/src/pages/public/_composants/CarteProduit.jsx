import { Link } from "react-router-dom";
import { prix } from "@/lib/format";
import VisuelProduit from "./VisuelProduit";

// Carte d'un produit dans une grille (vitrine, produits similaires) :
// visuel, marque, nom, prix en orange et disponibilité. Toute la carte est cliquable.
export default function CarteProduit({ produit, boutique }) {
  return (
    <Link
      to={`/b/${boutique.slug}/produit/${produit.slug}`}
      className="group flex flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
    >
      {/* Visuel carré en haut de la carte */}
      <VisuelProduit produit={produit} className="aspect-square w-full border-b border-gray-100" />

      {/* Texte : marque, nom (2 lignes max), prix et stock */}
      <div className="flex flex-1 flex-col gap-1 p-3">
        {produit.marque && <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">{produit.marque}</p>}
        <p className="line-clamp-2 text-sm font-semibold leading-snug text-ink group-hover:text-boutique">{produit.nom}</p>
        <div className="mt-auto pt-2">
          <p className="text-base font-extrabold text-accent">{prix(produit.prix_vente, boutique.devise)}</p>
          {produit.disponible
            ? <p className="text-xs font-semibold text-green-600">● En stock</p>
            : <p className="text-xs font-semibold text-red-500">● Rupture</p>}
        </div>
      </div>
    </Link>
  );
}
