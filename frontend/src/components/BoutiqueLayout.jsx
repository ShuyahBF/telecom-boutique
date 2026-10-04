import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useParams, useSearchParams } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { nombreArticles } from "@/lib/panier";
import BoutonAppelWa from "@/components/BoutonAppelWa";
import Chargement from "@/components/Chargement";
import PoweredBySawali from "@/components/PoweredBySawali";
import { LiensLegaux } from "@/components/PageLegale";
import { IconeAdlyn } from "@/components/Marque";

// Mise en page de l'espace PUBLIC d'une boutique (/b/:slug/...) : en-tête aux
// couleurs de la boutique, menu, panier, pied de page. Les pages enfants
// reçoivent la boutique via useOutletContext() -> { boutique }.
export default function BoutiqueLayout() {
  const { slug } = useParams();
  const [boutique, setBoutique] = useState(null);
  const [introuvable, setIntrouvable] = useState(false);
  const [nbPanier, setNbPanier] = useState(0);
  const [menuOuvert, setMenuOuvert] = useState(false);
  // Arrivée depuis le QR code d'une facture (?espace=1) : bandeau « Mon espace » mis en avant
  const [params] = useSearchParams();
  const depuisQr = params.get("espace") === "1";

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
        <PoweredBySawali sombre={false} className="mt-6" />
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
    <div style={{ "--couleur-boutique": boutique.couleur || "#1e90ff" }} className="flex min-h-screen flex-col bg-gray-50">
      <header className="no-print sticky top-0 z-40 bg-boutique shadow">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Link to={base} className="flex min-w-0 items-center gap-2 text-white">
            {boutique.logo_url
              ? <img src={boutique.logo_url} alt="" className="h-10 w-10 rounded-xl bg-white object-contain p-0.5" />
              : <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/20 text-xl">📱</span>}
            <span className="truncate font-display text-lg font-bold">{boutique.nom}</span>
          </Link>
          <nav className="ml-4 hidden flex-1 gap-1 md:flex">
            <NavLink end to={base} className={lien}>Catalogue</NavLink>
            <NavLink to={`${base}/suivi-commande`} className={lien}>Suivre ma commande</NavLink>
            <NavLink to={`${base}/suivi-reparation`} className={lien}>Suivre ma réparation</NavLink>
            <NavLink to={`${base}/conseil`} className={lien}>Demander conseil</NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {/* « Mon espace » : factures, devis, règlements et SAV du client (numéro + code WhatsApp) */}
            <Link to={`/mon-espace/${boutique.slug}`} className="rounded-xl bg-white/15 px-3 py-2 font-semibold text-white hover:bg-white/25">
              👤<span className="ml-1 hidden sm:inline">Mon espace</span>
            </Link>
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
            <NavLink to={`/mon-espace/${boutique.slug}`} className={lien}>Mon espace</NavLink>
          </nav>
        )}
      </header>

      {depuisQr && (
        <div className="no-print bg-white shadow-sm">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
            <p className="text-sm text-gray-700">Retrouvez vos factures, devis, règlements et réparations dans votre espace client.</p>
            <Link to={`/mon-espace/${boutique.slug}`} className="btn-primary btn-sm">👤 Mon espace</Link>
          </div>
        </div>
      )}

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet context={{ boutique }} />
      </main>

      <footer className="no-print bg-nuit-950 text-gray-400">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm sm:grid-cols-3">
          <div>
            <p className="font-display text-lg font-bold text-white">{boutique.nom}</p>
            {boutique.slogan && <p>{boutique.slogan}</p>}
            <p className="puce mt-3 text-gray-400">Code marchand · {boutique.code_marchand}</p>
          </div>
          {/* Adresse, ville et pays + lien vers Google Maps (itinéraire) si la
              boutique a renseigné sa position GPS (latitude / longitude) */}
          <div>
            <p className="mb-2 font-display font-semibold text-white">Nous trouver</p>
            {boutique.adresse && <p className="whitespace-pre-line">{boutique.adresse}</p>}
            {lieu && <p>{lieu}</p>}
            {lienCarte && (
              <a href={lienCarte} target="_blank" rel="noopener noreferrer"
                className="mt-2 inline-flex items-center gap-1 font-semibold text-primary-clair hover:underline">
                📍 Voir sur la carte / Itinéraire
              </a>
            )}
          </div>
          <div>
            <p className="mb-2 font-display font-semibold text-white">Nous contacter</p>
            {boutique.telephone && <p>{boutique.telephone}</p>}
            {boutique.email && <p>{boutique.email}</p>}
            {/* Appel WhatsApp : bouton grisé en attendant l'ouverture du service */}
            <BoutonAppelWa telephone={boutique.telephone} sombre className="btn-sm mt-3" />
            <br />
            <Link to="/" className="mt-3 inline-block font-semibold text-primary-clair hover:underline">← Toutes les boutiques</Link>
          </div>
        </div>
        {/* Mention de la plateforme, comme la ligne de copyright de Sawali */}
        {/* Bas de page : plateforme adLyn + mention obligatoire « Powered by Sawali Smart Systems » */}
        <div className="space-y-1 border-t border-white/5 py-4 text-center text-xs text-gray-500">
          <p className="flex items-center justify-center gap-1.5">
            Boutique en ligne sur
            <Link to="/" className="inline-flex items-center gap-1 font-semibold text-gray-300 hover:text-white">
              <IconeAdlyn clair className="h-4 w-4" /> adLyn
            </Link>
          </p>
          <LiensLegaux className="justify-center" />
          <PoweredBySawali />
        </div>
      </footer>
    </div>
  );
}
