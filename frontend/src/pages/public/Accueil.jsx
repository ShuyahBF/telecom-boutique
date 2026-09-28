import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import Chargement from "@/components/Chargement";
import ScannerQr from "@/components/ScannerQr";
import { useToast } from "@/components/Toast";

// Page d'ENTRÉE de la plateforme (adresse « / ») : accroche, carrousel de
// toutes les boutiques, recherche par nom ou code marchand, scan de QR code.
export default function Accueil() {
  const navigate = useNavigate();
  const toast = useToast();

  // Toutes les boutiques actives (pour le carrousel) ; null = en cours de chargement
  const [boutiques, setBoutiques] = useState(null);
  // Recherche : texte saisi, résultats (null = pas encore cherché), recherche en cours
  const [recherche, setRecherche] = useState("");
  const [resultats, setResultats] = useState(null);
  const [recherchant, setRecherchant] = useState(false);
  // Fenêtre du scanner de QR code ouverte ou non
  const [scannerOuvert, setScannerOuvert] = useState(false);

  // Au chargement de la page : titre de l'onglet + liste des boutiques
  useEffect(() => {
    document.title = "adLyn — Trouvez votre boutique de téléphonie";
    apiClient.get("/public/boutiques")
      .then(({ data }) => setBoutiques(data))
      .catch(() => setBoutiques([]));
  }, []);

  // Recherche d'une boutique par nom, ville ou code marchand
  const chercher = async (e) => {
    e.preventDefault();
    const q = recherche.trim();
    if (!q) return;
    setRecherchant(true);
    try {
      const { data } = await apiClient.get("/public/boutiques", { params: { q } });
      // Un seul résultat dont le code marchand correspond exactement : on y va directement
      if (data.length === 1 && data[0].code_marchand === q.toUpperCase()) {
        navigate(`/b/${data[0].slug}`);
        return;
      }
      setResultats(data);
    } catch (err) {
      toast.erreur(messageErreur(err, "La recherche a échoué"));
    } finally {
      setRecherchant(false);
    }
  };

  // Résultat du scanner : une adresse « https://site/b/<slug> » ou un code marchand.
  // useCallback évite de relancer la caméra à chaque affichage de la page.
  const surScan = useCallback(async (texte) => {
    setScannerOuvert(false);
    const lu = (texte || "").trim();
    // 1) Le texte est une adresse web : on garde uniquement le chemin « /b/... »
    let url = null;
    try {
      url = new URL(lu);
    } catch {
      url = null; // ce n'est pas une adresse web : on passe au cas 2
    }
    if (url) {
      const position = url.pathname.indexOf("/b/");
      if (position >= 0) navigate(url.pathname.slice(position) + url.search);
      else toast.erreur("Ce QR code ne correspond pas à une boutique.");
      return;
    }
    // 2) Sinon, on le traite comme un code marchand
    try {
      const { data } = await apiClient.get(`/public/b/${encodeURIComponent(lu)}`);
      navigate(`/b/${data.slug}`);
    } catch {
      toast.erreur(`Aucune boutique ne correspond au code « ${lu} ».`);
    }
  }, [navigate, toast]);

  // Fermeture du scanner (fonction stable, pour ne pas relancer la caméra inutilement)
  const fermerScanner = useCallback(() => setScannerOuvert(false), []);

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      {/* ---------- Bandeau d'accroche (fond bleu dégradé) ---------- */}
      <header className="relative overflow-hidden bg-gradient-to-br from-primary via-primary to-primary-dark text-white">
        {/* Cercles décoratifs en arrière-plan */}
        <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-white/10" />
        <div className="pointer-events-none absolute -bottom-24 -left-16 h-64 w-64 rounded-full bg-accent/20" />

        {/* Barre du haut : nom de la plateforme + lien discret vers l'espace boutique */}
        <div className="relative mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <span className="flex min-w-0 items-center gap-2 text-lg font-extrabold">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/15">📱</span>
            adLyn
          </span>
          <Link to="/connexion" className="whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-semibold text-white/80 hover:bg-white/10 hover:text-white">
            Espace boutique
          </Link>
        </div>

        {/* Titre, sous-titre, recherche et bouton de scan */}
        <div className="relative mx-auto max-w-3xl px-4 pb-14 pt-6 text-center sm:pt-10">
          <h1 className="text-3xl font-extrabold leading-tight sm:text-5xl">
            Votre boutique de téléphonie,<br className="hidden sm:block" /> <span className="text-accent">à portée de main</span>
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-white/85 sm:text-lg">
            Téléphones, accessoires et réparations : commandez en ligne, suivez votre commande et votre réparation, posez vos questions.
          </p>

          {/* Formulaire de recherche : nom de la boutique ou code marchand */}
          <form onSubmit={chercher} className="mx-auto mt-8 flex max-w-xl flex-col gap-2 sm:flex-row">
            <input
              className="input flex-1 border-transparent py-3 text-ink shadow-lg"
              placeholder="Nom de la boutique ou code marchand"
              value={recherche}
              onChange={(e) => setRecherche(e.target.value)}
              aria-label="Nom de la boutique ou code marchand"
            />
            <button type="submit" className="btn-accent py-3 shadow-lg" disabled={recherchant}>
              {recherchant ? "Recherche…" : "🔍 Rechercher"}
            </button>
          </form>
          <button
            type="button"
            onClick={() => setScannerOuvert(true)}
            className="btn mt-3 border border-white/40 bg-white/10 text-white hover:bg-white/20"
          >
            📷 Scanner un QR code
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        {/* ---------- Résultats de la recherche (affichés seulement après une recherche) ---------- */}
        {resultats && (
          <section className="mb-10">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-lg font-bold">
                {resultats.length === 0
                  ? "Aucune boutique trouvée"
                  : `${resultats.length} boutique${resultats.length > 1 ? "s" : ""} trouvée${resultats.length > 1 ? "s" : ""}`}
              </h2>
              <button type="button" className="text-sm font-semibold text-primary" onClick={() => { setResultats(null); setRecherche(""); }}>
                Effacer
              </button>
            </div>
            {resultats.length === 0 ? (
              <p className="card text-gray-500">Vérifiez l'orthographe ou le code marchand (affiché en boutique et sur vos factures).</p>
            ) : (
              <ul className="divide-y divide-gray-100 overflow-hidden rounded-2xl border border-gray-200 bg-white">
                {resultats.map((b) => (
                  <li key={b.id}>
                    <Link to={`/b/${b.slug}`} className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50">
                      <LogoBoutique boutique={b} taille="h-12 w-12 text-2xl" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-bold">{b.nom}</p>
                        <p className="truncate text-sm text-gray-500">{[lieuBoutique(b), b.slogan].filter(Boolean).join(" · ") || "Boutique de téléphonie"}</p>
                      </div>
                      <span className="badge bg-gray-100 font-mono text-gray-600">{b.code_marchand}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {/* ---------- Carrousel de toutes les boutiques ---------- */}
        <section>
          <h2 className="mb-1 text-xl font-extrabold sm:text-2xl">Nos boutiques partenaires</h2>
          <p className="mb-4 text-sm text-gray-500">Faites glisser pour les parcourir, puis touchez une boutique pour entrer.</p>
          {boutiques === null && <Chargement texte="Chargement des boutiques…" />}
          {boutiques?.length === 0 && <p className="card text-gray-500">Aucune boutique n'est encore ouverte.</p>}
          {boutiques?.length > 0 && <Carrousel boutiques={boutiques} />}
        </section>

        {/* ---------- Comment ça marche (3 étapes) ---------- */}
        <section className="mt-12 grid gap-4 sm:grid-cols-3">
          {[
            ["🏪", "Choisissez votre boutique", "Par son nom, son code marchand ou en scannant son QR code."],
            ["🛒", "Commandez en ligne", "Retrait en boutique ou livraison, paiement à la réception ou par Mobile Money."],
            ["🔧", "Suivez tout en direct", "L'avancement de votre commande et de votre réparation, à tout moment."],
          ].map(([emoji, titre, texte]) => (
            <div key={titre} className="card">
              <p className="text-3xl">{emoji}</p>
              <p className="mt-2 font-bold">{titre}</p>
              <p className="mt-1 text-sm text-gray-500">{texte}</p>
            </div>
          ))}
        </section>
      </main>

      {/* ---------- Pied de page ---------- */}
      <footer className="border-t border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-4 py-6 text-center text-sm text-gray-500 sm:flex-row sm:text-left">
          <p>© {new Date().getFullYear()} adLyn — la plateforme des boutiques de téléphonie</p>
          <Link to="/connexion" className="font-semibold text-primary">Vous êtes une boutique ? Connexion</Link>
        </div>
      </footer>

      {/* Fenêtre du scanner (caméra), affichée seulement quand elle est ouverte */}
      <ScannerQr ouvert={scannerOuvert} onFermer={fermerScanner} onResultat={surScan} />
    </div>
  );
}

// Lieu d'une boutique : « Ouagadougou, Burkina Faso », ou seulement ce qui est
// renseigné (ville seule, pays seul), ou "" si rien n'est connu.
function lieuBoutique(b) {
  return [b.ville, b.pays].filter(Boolean).join(", ");
}

// Logo d'une boutique, ou emoji 📱 sur fond de la couleur de la boutique s'il n'y en a pas.
function LogoBoutique({ boutique, taille }) {
  if (boutique.logo_url) {
    return <img src={boutique.logo_url} alt="" className={`${taille} shrink-0 rounded-2xl border border-gray-100 bg-white object-contain p-1`} />;
  }
  return (
    <span
      className={`${taille} flex shrink-0 items-center justify-center rounded-2xl text-white`}
      style={{ backgroundColor: boutique.couleur || "#0b5ed7" }}
      aria-hidden="true"
    >
      📱
    </span>
  );
}

// Carrousel glissant : défile tout seul d'une carte toutes les 3 secondes,
// se met en pause au survol de la souris ou quand on le touche du doigt,
// se fait glisser au doigt (défilement horizontal « aimanté ») et a deux flèches.
function Carrousel({ boutiques }) {
  const pisteRef = useRef(null); // la bande horizontale qui défile
  const [enPause, setEnPause] = useState(false);
  const reprise = useRef(null); // minuterie qui relance le défilement après un toucher

  // Fait défiler d'une carte vers la droite (sens = 1) ou la gauche (sens = -1).
  // Arrivé au bout, on revient au début (et inversement).
  const defiler = useCallback((sens) => {
    const piste = pisteRef.current;
    if (!piste) return;
    const carte = piste.querySelector("[data-carte]");
    const pas = carte ? carte.offsetWidth + 16 : piste.clientWidth * 0.8; // 16 px = espace entre cartes
    const max = piste.scrollWidth - piste.clientWidth;
    if (max <= 0) return; // tout tient à l'écran : rien à faire défiler
    if (sens > 0 && piste.scrollLeft >= max - 4) piste.scrollTo({ left: 0, behavior: "smooth" });
    else if (sens < 0 && piste.scrollLeft <= 4) piste.scrollTo({ left: max, behavior: "smooth" });
    else piste.scrollBy({ left: sens * pas, behavior: "smooth" });
  }, []);

  // Défilement automatique toutes les 3 s (arrêté pendant la pause)
  useEffect(() => {
    if (enPause) return undefined;
    const minuterie = setInterval(() => defiler(1), 3000);
    return () => clearInterval(minuterie);
  }, [enPause, defiler]);

  // Nettoyage de la minuterie de reprise quand on quitte la page
  useEffect(() => () => clearTimeout(reprise.current), []);

  // Toucher du doigt : pause, puis reprise 4 s après avoir lâché
  const debutToucher = () => { clearTimeout(reprise.current); setEnPause(true); };
  const finToucher = () => { reprise.current = setTimeout(() => setEnPause(false), 4000); };

  return (
    <div
      className="relative"
      onMouseEnter={() => setEnPause(true)}
      onMouseLeave={() => setEnPause(false)}
      onTouchStart={debutToucher}
      onTouchEnd={finToucher}
    >
      {/* La piste : cartes alignées, défilement horizontal aimanté, barre de défilement masquée */}
      <div
        ref={pisteRef}
        className="-mx-4 flex snap-x snap-mandatory scroll-px-4 gap-4 overflow-x-auto scroll-smooth px-4 pb-4 pt-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {boutiques.map((b) => (
          <Link
            key={b.id}
            to={`/b/${b.slug}`}
            data-carte
            className="group flex w-[78%] shrink-0 snap-start flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm transition hover:-translate-y-1 hover:shadow-lg sm:w-[calc((100%-2rem)/3)] lg:w-[calc((100%-3rem)/4)]"
          >
            {/* Bandeau de couleur de la boutique, avec son logo */}
            <div className="relative flex h-24 items-end px-4" style={{ backgroundColor: b.couleur || "#0b5ed7" }}>
              {b.mise_en_avant && (
                <span className="badge absolute right-3 top-3 bg-white/90 text-amber-700">⭐ À la une</span>
              )}
              <div className="translate-y-1/2 rounded-2xl bg-white p-1 shadow">
                <LogoBoutique boutique={b} taille="h-14 w-14 text-3xl" />
              </div>
            </div>
            {/* Nom, ville, slogan et code marchand */}
            <div className="flex flex-1 flex-col px-4 pb-4 pt-10">
              <p className="truncate text-lg font-extrabold group-hover:text-primary">{b.nom}</p>
              {/* Lieu : « Ville, Pays » (seulement les informations renseignées) */}
              <p className="truncate text-sm text-gray-500">📍 {lieuBoutique(b) || "Ville non précisée"}</p>
              <p className="mt-2 line-clamp-2 min-h-[2.5rem] text-sm text-gray-600">{b.slogan || "Téléphones, accessoires et réparations."}</p>
              <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
                <span className="text-xs text-gray-400">Code <b className="font-mono text-gray-600">{b.code_marchand}</b></span>
                <span className="text-sm font-semibold text-primary">Entrer →</span>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Flèches précédente / suivante (sur les côtés de la piste) */}
      {boutiques.length > 1 && (
        <>
          <button
            type="button"
            onClick={() => defiler(-1)}
            className="absolute -left-2 top-12 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-gray-200 bg-white text-lg shadow-md hover:bg-gray-50 sm:-left-4"
            aria-label="Boutique précédente"
          >
            ←
          </button>
          <button
            type="button"
            onClick={() => defiler(1)}
            className="absolute -right-2 top-12 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-gray-200 bg-white text-lg shadow-md hover:bg-gray-50 sm:-right-4"
            aria-label="Boutique suivante"
          >
            →
          </button>
        </>
      )}
    </div>
  );
}
