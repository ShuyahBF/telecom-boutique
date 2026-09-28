import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import { montant } from "@/lib/format";

// Recherche d'un produit du catalogue (nom, référence, marque).
// onChoisir(produit) est appelé au clic ; le champ se vide ensuite.
// filtre : fonction facultative pour limiter la liste (ex. p => p.type_produit === "PIE")
export default function ProduitSelect({ onChoisir, filtre, placeholder = "Ajouter un produit (nom, référence)…" }) {
  const [recherche, setRecherche] = useState("");
  const [resultats, setResultats] = useState([]);
  const [ouvert, setOuvert] = useState(false); // liste des résultats affichée ou non

  // Recherche dans le catalogue, seulement quand la liste est ouverte
  // (petit délai pour ne pas interroger l'API à chaque lettre tapée)
  useEffect(() => {
    if (!ouvert) return undefined;
    const t = setTimeout(() => {
      apiClient.get("/produits", { params: { q: recherche } })
        .then(({ data }) => setResultats((filtre ? data.filter(filtre) : data).filter((p) => p.actif !== false).slice(0, 20)))
        .catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [recherche, ouvert, filtre]);

  return (
    <div className="relative">
      {/* Champ de recherche. La liste s'ouvre :
          - quand le champ reçoit le focus ;
          - au clic dans le champ (utile s'il a gardé le focus après un premier choix) ;
          - dès qu'on tape une lettre (onChange).
          Elle se ferme quand on quitte le champ (petit délai pour laisser le clic sur un résultat se faire). */}
      <input className="input" placeholder={placeholder} value={recherche}
        onFocus={() => setOuvert(true)} onClick={() => setOuvert(true)}
        onBlur={() => setTimeout(() => setOuvert(false), 200)}
        onChange={(e) => { setRecherche(e.target.value); setOuvert(true); }} />
      {ouvert && (
        <div className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-gray-200 bg-white shadow-lg">
          {resultats.map((p) => (
            <button key={p.id} type="button" className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-gray-50"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => { onChoisir(p); setRecherche(""); setOuvert(false); }}>
              <span><span className="font-medium">{p.nom}</span> <span className="text-xs text-gray-500">{p.reference}</span></span>
              <span className="whitespace-nowrap text-sm">
                {montant(p.prix_vente)}
                {p.type_produit !== "SER" && <span className={`ml-2 text-xs ${p.stock <= 0 ? "text-red-600" : "text-gray-500"}`}>stock {p.stock}</span>}
              </span>
            </button>
          ))}
          {resultats.length === 0 && <p className="px-3 py-2 text-sm text-gray-500">Aucun produit trouvé.</p>}
        </div>
      )}
    </div>
  );
}
