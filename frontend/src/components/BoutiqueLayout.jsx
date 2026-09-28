import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { nombreArticles } from "@/lib/panier";
import Chargement from "@/components/Chargement";

// Mise en page de l'espace PUBLIC d'une boutique (/b/:slug/...) : en-tête aux
// couleurs de la boutique, menu, panier, pied de page. Les pages enfants
// reçoivent la boutique via useOutletContext() -> { boutique }.
export default function BoutiqueLayout() {
  const { slug } = useParams();
  const [boutique, setBoutique] = useState(null);
  const [introuvable, setIntrouvable] = useState(false);
  const [nbPanier, setNbPanier] = useState(0);
  const [menuOuvert, setMenuOuvert] = useState(false);

  useEffect(() => {
    setBoutique(null);
    setIntrouvable(false);
    apiClient.get(`/public/b/${slug}`)
      .then(({ data }) => { setBoutique(data); document.title = data.nom; })
      .catch(() => setIntrouvable(true));
  }, [slug]);

  // Compteur du panier, mis à jour à chaque modification
  useEffect(() => {
    if (!boutique) return undefined;
    const maj = () => setNbPanier(nombreArticles(boutique.slug));
    maj();
    window.addEventListener("panier-change", maj);
    return () => window.removeEventListener("panier-change", maj);
  }, [boutique]);

  if (introuvable) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
        <p className="text-5xl">🔍</p>
        <h1 className="text-2xl font-bold">Boutique introuvable</h1>
        <p className="text-gray-500">Cette boutique n'existe pas ou n'est plus active.</p>
        <Link to="/" className="btn-primary">Voir toutes les boutiques</Link>
      </div>
    );
  }
  if (!boutique) return <Chargement plein />;

  const base = `/b/${boutique.slug}`;
  // Ville et pays sur une ligne (« Ouagadougou, Burkina Faso »), sans répéter
  // la ville si elle figure déjà dans l'adresse
  const villeAffichee = boutique.ville && !(boutique.adresse || "").toLowerCase().includes(boutique.ville.toLowerCase()) ? boutique.ville : "";
  const lieu = [villeAffichee, boutique.pays].filter(Boolean).join(", ");
  // Lien d'itinéraire Google Maps : seulement si la position GPS est connue
  // (on teste « != null » car une coordonnée peut valoir 0)
  const aPosition = boutique.latitude != null && boutique.longitude != null && boutique.latitude !== "" && boutique.longitude !== "";
  const lienCarte = aPosition
    ? `https://www.google.com/maps/dir/?api=1&destination=${boutique.latitude},${boutique.longitude}`
    : "";
  const lien = ({ isActive }) => `rounded-lg px-3 py-2 text-sm font-semibold ${isActive ? "bg-white/20 text-white" : "text-white/85 hover:text-white"}`;
  return (
    <div style={{ "--couleur-boutique": boutique.couleur || "#0b5ed7" }} className="flex min-h-screen flex-col bg-gray-50">
      <header className="no-print sticky top-0 z-40 bg-boutique shadow">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Link to={base} className="flex min-w-0 items-center gap-2 text-white">
            {boutique.logo_url
              ? <img src={boutique.logo_url} alt="" className="h-10 w-10 rounded-xl bg-white object-contain p-0.5" />
              : <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/20 text-xl">📱</span>}
            <span className="truncate text-lg font-extrabold">{boutique.nom}</span>
          </Link>
          <nav className="ml-4 hidden flex-1 gap-1 md:flex">
            <NavLink end to={base} className={lien}>Catalogue</NavLink>
            <NavLink to={`${base}/suivi-commande`} className={lien}>Suivre ma commande</NavLink>
            <NavLink to={`${base}/suivi-reparation`} className={lien}>Suivre ma réparation</NavLink>
            <NavLink to={`${base}/conseil`} className={lien}>Demander conseil</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <Link to={`${base}/panier`} className="relative rounded-xl bg-white/15 px-3 py-2 font-semibold text-white hover:bg-white/25">
              🛒<span className="ml-1 hidden sm:inline">Panier</span>
              {nbPanier > 0 && <span className="absolute -right-2 -top-2 rounded-full bg-accent px-1.5 text-xs">{nbPanier}</span>}
            </Link>
            <button type="button" className="rounded-xl bg-white/15 px-3 py-2 text-white md:hidden" onClick={() => setMenuOuvert(!menuOuvert)} aria-label="Menu">☰</button>
          </div>
        </div>
        {menuOuvert && (
          <nav className="flex flex-col gap-1 px-4 pb-3 md:hidden" onClick={() => setMenuOuvert(false)}>
            <NavLink end to={base} className={lien}>Catalogue</NavLink>
            <NavLink to={`${base}/suivi-commande`} className={lien}>Suivre ma commande</NavLink>
            <NavLink to={`${base}/suivi-reparation`} className={lien}>Suivre ma réparation</NavLink>
            <NavLink to={`${base}/conseil`} className={lien}>Demander conseil</NavLink>
          </nav>
        )}
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet context={{ boutique }} />
      </main>

      <footer className="no-print border-t border-gray-200 bg-white">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 py-8 text-sm text-gray-600 sm:grid-cols-3">
          <div>
            <p className="font-bold text-ink">{boutique.nom}</p>
            {boutique.slogan && <p>{boutique.slogan}</p>}
            <p className="mt-1 text-xs">Code marchand : <b>{boutique.code_marchand}</b></p>
          </div>
          {/* Adresse, ville et pays + lien vers Google Maps (itinéraire) si la
              boutique a renseigné sa position GPS (latitude / longitude) */}
          <div>
            <p className="font-bold text-ink">Nous trouver</p>
            {boutique.adresse && <p className="whitespace-pre-line">{boutique.adresse}</p>}
            {lieu && <p>{lieu}</p>}
            {lienCarte && (
              <a href={lienCarte} target="_blank" rel="noopener noreferrer"
                className="mt-2 inline-flex items-center gap-1 font-semibold text-boutique hover:underline">
                📍 Voir sur la carte / Itinéraire
              </a>
            )}
          </div>
          <div>
            <p className="font-bold text-ink">Nous contacter</p>
            {boutique.telephone && <p>{boutique.telephone}</p>}
            {boutique.email && <p>{boutique.email}</p>}
            <Link to="/" className="mt-2 inline-block font-semibold text-primary">← Toutes les boutiques</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
