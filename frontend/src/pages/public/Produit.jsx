import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { prix } from "@/lib/format";
import { ajouterAuPanier, lirePanier } from "@/lib/panier";
import { TYPES_PRODUIT } from "@/lib/statuts";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import CarteProduit from "./_composants/CarteProduit";
import DocumentsProduit from "./_composants/DocumentsProduit";
import VisuelProduit from "./_composants/VisuelProduit";

// FICHE PRODUIT (/b/:slug/produit/:produitSlug) : photo, prix, disponibilité,
// ajout au panier, description, caractéristiques, compatibilité (pièces et
// accessoires), conseils d'utilisation, documents et produits similaires.
export default function Produit() {
  const { boutique } = useOutletContext();
  const { produitSlug } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  // Le produit (avec sa liste « similaires ») ; null = chargement
  const [produit, setProduit] = useState(null);
  const [erreur, setErreur] = useState("");
  // Quantité choisie avant l'ajout au panier
  const [quantite, setQuantite] = useState(1);
  // Compteur qui change à chaque modification du panier, pour réafficher la page
  const [, setVersionPanier] = useState(0);

  // On écoute l'événement « panier-change » (envoyé par lib/panier) pour
  // mettre à jour « déjà dans le panier » et la quantité maximale
  useEffect(() => {
    const maj = () => setVersionPanier((v) => v + 1);
    window.addEventListener("panier-change", maj);
    return () => window.removeEventListener("panier-change", maj);
  }, []);

  // Chargement du produit (et remise à zéro quand on passe à un produit similaire)
  useEffect(() => {
    let actif = true;
    setProduit(null);
    setErreur("");
    setQuantite(1);
    apiClient.get(`/public/b/${boutique.slug}/produits/${produitSlug}`)
      .then(({ data }) => {
        if (!actif) return;
        setProduit(data);
        document.title = `${data.nom} — ${boutique.nom}`;
        window.scrollTo({ top: 0 });
      })
      .catch((err) => actif && setErreur(messageErreur(err, "Produit introuvable")));
    return () => { actif = false; };
  }, [boutique.slug, boutique.nom, produitSlug]);

  // Produit introuvable (lien périmé, produit retiré...)
  if (erreur) {
    return (
      <div className="card mx-auto max-w-md py-10 text-center">
        <p className="text-4xl">😕</p>
        <p className="mt-2 font-semibold">{erreur}</p>
        <Link to={`/b/${boutique.slug}`} className="btn-boutique mt-4">← Retour au catalogue</Link>
      </div>
    );
  }
  if (!produit) return <Chargement />;

  // Quantité maximale : le stock (null = pas de limite, ex. un service), moins ce qui est déjà au panier
  const dejaAuPanier = lirePanier(boutique.slug)[produit.id]?.quantite || 0;
  const maximum = produit.stock_max == null ? 20 : Math.max(produit.stock_max - dejaAuPanier, 0);

  // Ajout au panier + message de confirmation
  const ajouter = () => {
    ajouterAuPanier(boutique.slug, produit, quantite);
    toast.succes(`${quantite} × ${produit.nom} ajouté${quantite > 1 ? "s" : ""} au panier`);
    setQuantite(1);
  };

  // Lien vers le formulaire de conseil, avec le produit pré-rempli
  const lienQuestion = `/b/${boutique.slug}/conseil?produit=${encodeURIComponent(produit.id)}&nom=${encodeURIComponent(produit.nom)}`;

  return (
    <div className="space-y-8">
      {/* Fil d'Ariane : Catalogue › Rayon › Produit */}
      <nav className="flex flex-wrap items-center gap-1 text-sm text-gray-500">
        <Link to={`/b/${boutique.slug}`} className="hover:text-boutique">Catalogue</Link>
        {produit.categorie_nom && (
          <>
            <span>›</span>
            <Link to={`/b/${boutique.slug}?categorie=${produit.categorie_id}`} className="hover:text-boutique">{produit.categorie_nom}</Link>
          </>
        )}
        <span>›</span>
        <span className="truncate text-gray-700">{produit.nom}</span>
      </nav>

      <div className="grid gap-6 md:grid-cols-2 md:gap-10">
        {/* ---------- Colonne gauche : grande image ---------- */}
        <VisuelProduit produit={produit} tailleEmoji="text-8xl" className="aspect-square w-full rounded-3xl border border-gray-200" />

        {/* ---------- Colonne droite : infos et achat ---------- */}
        <div className="flex flex-col gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-gray-400">
              {[produit.marque, TYPES_PRODUIT[produit.type_produit]].filter(Boolean).join(" · ")}
            </p>
            <h1 className="mt-1 text-2xl font-extrabold leading-tight sm:text-3xl">{produit.nom}</h1>
            <p className="mt-3 text-3xl font-extrabold text-accent">{prix(produit.prix_vente, boutique.devise)}</p>
          </div>

          {/* Disponibilité et garantie */}
          <div className="flex flex-wrap gap-2">
            {produit.disponible
              ? <span className="badge bg-green-100 px-3 py-1 text-sm text-green-800">✓ En stock</span>
              : <span className="badge bg-red-100 px-3 py-1 text-sm text-red-700">Rupture de stock</span>}
            {produit.garantie_mois > 0 && (
              <span className="badge bg-blue-50 px-3 py-1 text-sm text-blue-800">🛡️ Garantie {produit.garantie_mois} mois</span>
            )}
          </div>

          {/* Choix de la quantité + bouton d'ajout (seulement si disponible) */}
          {produit.disponible ? (
            maximum > 0 ? (
              <div className="flex items-stretch gap-3">
                <div className="flex items-center rounded-xl border border-gray-300 bg-white">
                  <button type="button" className="px-4 py-2 text-xl font-bold disabled:opacity-30" disabled={quantite <= 1}
                    onClick={() => setQuantite(quantite - 1)} aria-label="Diminuer la quantité">−</button>
                  <span className="w-8 text-center font-bold">{quantite}</span>
                  <button type="button" className="px-4 py-2 text-xl font-bold disabled:opacity-30" disabled={quantite >= maximum}
                    onClick={() => setQuantite(quantite + 1)} aria-label="Augmenter la quantité">+</button>
                </div>
                <button type="button" className="btn-accent flex-1 py-3 text-base" onClick={ajouter}>🛒 Ajouter au panier</button>
              </div>
            ) : (
              <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
                Vous avez déjà tout le stock disponible dans votre panier.
              </p>
            )
          ) : (
            <p className="rounded-xl bg-gray-100 p-3 text-sm text-gray-600">
              Ce produit est momentanément indisponible. Posez-nous la question : nous vous dirons quand il revient.
            </p>
          )}

          {/* Accès rapide au panier s'il contient déjà ce produit */}
          {dejaAuPanier > 0 && (
            <button type="button" className="btn-outline" onClick={() => navigate(`/b/${boutique.slug}/panier`)}>
              Voir mon panier ({dejaAuPanier} dans le panier) →
            </button>
          )}

          <Link to={lienQuestion} className="btn-outline">💬 Poser une question sur ce produit</Link>

          {/* Description */}
          {produit.description && (
            <div>
              <h2 className="mb-1 font-bold">Description</h2>
              <p className="whitespace-pre-line text-gray-700">{produit.description}</p>
            </div>
          )}

          {/* Fiche technique structurée (lignes « Libellé : valeur » préparées par le serveur) */}
          {produit.fiche_technique?.length > 0 && (
            <div>
              <h2 className="mb-2 font-bold">Fiche technique</h2>
              <table className="w-full overflow-hidden rounded-2xl border border-gray-200 bg-white text-sm">
                <tbody className="divide-y divide-gray-100">
                  {produit.fiche_technique.map((ligne) => {
                    // Découpe au premier « : » : libellé à gauche, valeur à droite
                    const i = ligne.indexOf(" : ");
                    return (
                      <tr key={ligne}>
                        <th className="w-2/5 bg-gray-50 px-4 py-2 text-left font-medium text-gray-500">{i > 0 ? ligne.slice(0, i) : ""}</th>
                        <td className="px-4 py-2 text-gray-800">{i > 0 ? ligne.slice(i + 3) : ligne}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Caractéristiques (liste à puces) */}
          {produit.caracteristiques?.length > 0 && (
            <div>
              <h2 className="mb-2 font-bold">Caractéristiques</h2>
              <ul className="divide-y divide-gray-100 rounded-2xl border border-gray-200 bg-white">
                {produit.caracteristiques.map((c) => (
                  <li key={c} className="flex gap-2 px-4 py-2 text-sm text-gray-700"><span className="text-boutique">•</span>{c}</li>
                ))}
              </ul>
            </div>
          )}
          {/* Compatibilité : liste des téléphones avec lesquels la pièce / l'accessoire fonctionne */}
          {produit.modeles_compatibles?.length > 0 && (
            <div>
              <h2 className="mb-2 font-bold">Compatible avec</h2>
              <div className="flex flex-wrap gap-2">
                {produit.modeles_compatibles.map((nom) => (
                  <span key={nom} className="badge bg-gray-100 px-3 py-1 text-sm text-gray-700">📱 {nom}</span>
                ))}
              </div>
            </div>
          )}

          {/* Conseils d'utilisation rédigés par la boutique (texte libre, retours à la ligne conservés) */}
          {produit.conseils_utilisation?.trim() && (
            <div>
              <h2 className="mb-1 font-bold">💡 Conseils d'utilisation</h2>
              <p className="whitespace-pre-line rounded-2xl bg-amber-50 p-4 text-sm text-gray-700">{produit.conseils_utilisation}</p>
            </div>
          )}

          {/* Documents que la boutique a rendus visibles (brochure, manuel...) */}
          <DocumentsProduit documents={produit.documents} />

          {produit.reference && <p className="text-xs text-gray-400">Réf. {produit.reference}</p>}
        </div>
      </div>

      {/* ---------- Produits similaires (même rayon) ---------- */}
      {produit.similaires?.length > 0 && (
        <section>
          <h2 className="mb-3 text-xl font-extrabold">Vous aimerez aussi</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
            {produit.similaires.map((p) => <CarteProduit key={p.id} produit={p} boutique={boutique} />)}
          </div>
        </section>
      )}
    </div>
  );
}
