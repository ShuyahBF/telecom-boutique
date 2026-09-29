import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import Chargement from "@/components/Chargement";
import { LogoAdlyn } from "@/components/Marque";
import PoweredBySawali from "@/components/PoweredBySawali";
import { LiensLegaux } from "@/components/PageLegale";
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
    // Titre EXACT de l'app (vérifié par les revues TikTok) : « adLyn »
    document.title = "adLyn";
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

  // Chiffres clés affichés dans le bandeau (comme les cartes « 25+ / 50+ » de Sawali)
  const villes = new Set((boutiques || []).map((b) => b.ville).filter(Boolean));
  const chiffres = [
    [boutiques ? `${boutiques.length}` : "…", "Boutiques partenaires"],
    [boutiques ? `${villes.size || 1}` : "…", villes.size > 1 ? "Villes couvertes" : "Ville couverte"],
    ["24/7", "Commande en ligne"],
    ["100 %", "Suivi en direct"],
  ];

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      {/* ================= BANDEAU D'ACCUEIL (bleu nuit, style Sawali) ================= */}
      <header className="relative overflow-hidden bg-nuit-900 text-white">
        {/* Halo bleu et quadrillage discret en arrière-plan (décor) */}
        <div className="pointer-events-none absolute -right-40 -top-40 h-[32rem] w-[32rem] rounded-full bg-primary/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-48 -left-32 h-96 w-96 rounded-full bg-accent/20 blur-3xl" />
        <div className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(#fff_1px,transparent_1px),linear-gradient(90deg,#fff_1px,transparent_1px)] [background-size:48px_48px]" />

        {/* Barre de navigation : logo + nom, sous-titre espacé, lien vers l'espace boutique */}
        <div className="relative border-b border-white/10">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4">
            {/* Logo officiel adLyn (version claire pour le fond bleu nuit) */}
            <Link to="/" className="flex min-w-0 items-center gap-4" aria-label="adLyn, accueil">
              <LogoAdlyn clair className="h-8 sm:h-10" />
              <span className="hidden border-l border-white/15 pl-4 text-[10px] font-semibold uppercase leading-normal tracking-[0.3em] text-primary-clair md:block">Boutiques de téléphonie</span>
            </Link>
            {/* Libellé court sur téléphone pour laisser la place au nom de la plateforme */}
            <Link to="/connexion" className="btn-clair btn-sm whitespace-nowrap">
              <span className="sm:hidden">Connexion</span><span className="hidden sm:inline">Espace boutique →</span>
            </Link>
          </div>
        </div>

        <div className="relative mx-auto grid max-w-6xl gap-10 px-4 pb-16 pt-10 lg:grid-cols-[1.4fr_1fr] lg:items-center lg:pt-16">
          {/* Colonne gauche : sur-titre, titre, texte, recherche */}
          <div>
            <span className="puce text-primary-clair">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Boutiques ouvertes · commande 24/7
            </span>
            <h1 className="mt-5 text-4xl font-bold leading-[1.05] sm:text-6xl">
              Votre boutique de téléphonie, <span className="text-primary-clair">à portée de main</span>.
            </h1>
            <p className="mt-5 max-w-xl text-lg text-gray-300">
              Téléphones, accessoires et réparations : commandez en ligne, suivez votre commande et votre réparation, posez vos questions.
            </p>

            {/* Formulaire de recherche : nom de la boutique ou code marchand */}
            <form onSubmit={chercher} className="mt-8 flex max-w-xl flex-col gap-3 sm:flex-row">
              <input
                className="input flex-1 border-white/10 bg-white py-3 text-ink"
                placeholder="Nom de la boutique ou code marchand"
                value={recherche}
                onChange={(e) => setRecherche(e.target.value)}
                aria-label="Nom de la boutique ou code marchand"
              />
              <button type="submit" className="btn-primary py-3" disabled={recherchant}>
                {recherchant ? "Recherche…" : "Rechercher →"}
              </button>
            </form>
            <button type="button" onClick={() => setScannerOuvert(true)} className="btn-clair mt-3">
              📷 Scanner un QR code
            </button>
            {/* Liens légaux visibles dès l'accueil, sans ouvrir de menu (exigé par les revues TikTok) */}
            <LiensLegaux className="mt-6" />
          </div>

          {/* Colonne droite : chiffres clés dans des cartes sombres */}
          <div className="grid grid-cols-2 gap-4">
            {chiffres.map(([valeur, libelle]) => (
              <div key={libelle} className="card-nuit">
                <p className="font-display text-4xl font-bold text-primary-clair">{valeur}</p>
                <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.25em] text-gray-400">{libelle}</p>
              </div>
            ))}
          </div>
        </div>
      </header>

      <main className="w-full flex-1">
        <div className="mx-auto max-w-6xl px-4 py-14">
          {/* ---------- Résultats de la recherche (affichés seulement après une recherche) ---------- */}
          {resultats && (
            <section className="mb-12">
              <div className="mb-4 flex items-end justify-between gap-3">
                <div>
                  <p className="surtitre">Recherche</p>
                  <h2 className="mt-1 text-2xl font-bold">
                    {resultats.length === 0
                      ? "Aucune boutique trouvée"
                      : `${resultats.length} boutique${resultats.length > 1 ? "s" : ""} trouvée${resultats.length > 1 ? "s" : ""}`}
                  </h2>
                </div>
                <button type="button" className="text-sm font-semibold text-primary" onClick={() => { setResultats(null); setRecherche(""); }}>
                  Effacer ×
                </button>
              </div>
              {resultats.length === 0 ? (
                <p className="card text-gray-500">Vérifiez l'orthographe ou le code marchand (affiché en boutique et sur vos factures).</p>
              ) : (
                <ul className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-200 bg-white">
                  {resultats.map((b) => (
                    <li key={b.id}>
                      <Link to={`/b/${b.slug}`} className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50">
                        <LogoBoutique boutique={b} taille="h-12 w-12 text-2xl" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-semibold">{b.nom}</p>
                          <p className="truncate text-sm text-gray-500">{[lieuBoutique(b), b.slogan].filter(Boolean).join(" · ") || "Boutique de téléphonie"}</p>
                        </div>
                        <span className="puce text-gray-500">{b.code_marchand}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {/* ---------- Carrousel de toutes les boutiques ---------- */}
          <section>
            <p className="surtitre">Notre réseau</p>
            <div className="mb-6 mt-1 flex flex-wrap items-end justify-between gap-2">
              <h2 className="text-3xl font-bold sm:text-4xl">Nos boutiques partenaires</h2>
              <p className="text-sm text-gray-500">Faites glisser, puis touchez une boutique pour entrer.</p>
            </div>
            {boutiques === null && <Chargement texte="Chargement des boutiques…" />}
            {boutiques?.length === 0 && <p className="card text-gray-500">Aucune boutique n'est encore ouverte.</p>}
            {boutiques?.length > 0 && <Carrousel boutiques={boutiques} />}
          </section>
        </div>

        {/* ---------- Comment ça marche (section sombre, cartes façon « Spécialisations ») ---------- */}
        <section className="bg-nuit-800 text-white">
          <div className="mx-auto max-w-6xl px-4 py-16">
            <p className="surtitre text-primary-clair">Comment ça marche</p>
            <h2 className="mt-1 text-3xl font-bold sm:text-4xl">Trois étapes, zéro déplacement inutile</h2>
            <div className="mt-8 grid gap-4 sm:grid-cols-3">
              {[
                ["🏪", "Choisissez votre boutique", "Par son nom, son code marchand ou en scannant son QR code."],
                ["🛒", "Commandez en ligne", "Retrait en boutique ou livraison, paiement à la réception ou par Mobile Money."],
                ["🔧", "Suivez tout en direct", "L'avancement de votre commande et de votre réparation, à tout moment."],
              ].map(([emoji, titre, texte], i) => (
                <div key={titre} className="card-nuit transition hover:border-primary/40">
                  <div className="flex items-center justify-between">
                    <span className="text-2xl">{emoji}</span>
                    <span className="font-mono text-xs text-gray-500">0{i + 1}</span>
                  </div>
                  <p className="mt-4 font-display text-lg font-bold">{titre}</p>
                  <p className="mt-2 text-sm leading-relaxed text-gray-400">{texte}</p>
                </div>
              ))}
            </div>

            {/* Encadré d'appel à l'action (comme « Got a project in mind? » sur Sawali) */}
            <div className="mt-14 flex flex-col items-start justify-between gap-6 rounded-2xl border border-white/15 bg-gradient-to-br from-nuit-700 to-nuit-800 p-8 sm:flex-row sm:items-center">
              <div>
                <p className="font-display text-2xl font-bold">Vous tenez une boutique de téléphonie ?</p>
                <p className="mt-1 text-gray-300">Vitrine en ligne, caisse, stock et SAV : 14 jours d'essai gratuit.</p>
              </div>
              <Link to="/connexion" className="btn-primary whitespace-nowrap px-8 py-3">Accéder à mon espace →</Link>
            </div>
          </div>
        </section>
      </main>

      {/* ---------- Pied de page (bleu nuit très foncé, colonnes façon Sawali) ---------- */}
      <footer className="bg-nuit-950 text-gray-400">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 text-sm sm:grid-cols-3">
          <div>
            <LogoAdlyn clair className="h-9" />
            <p className="mt-2 text-xs text-gray-300">Le SaaS qui fait grandir votre boutique de téléphonie</p>
            <p className="mt-3 leading-relaxed">La plateforme qui relie les boutiques de téléphonie à leurs clients : catalogue, commandes et réparations.</p>
          </div>
          <div>
            <p className="font-display font-semibold text-white">Clients</p>
            <ul className="mt-3 space-y-2">
              <li><a href="#top" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }} className="hover:text-white">Trouver une boutique</a></li>
              <li><button type="button" onClick={() => setScannerOuvert(true)} className="hover:text-white">Scanner un QR code</button></li>
            </ul>
          </div>
          <div>
            <p className="font-display font-semibold text-white">Boutiques</p>
            <ul className="mt-3 space-y-2">
              <li><Link to="/connexion" className="hover:text-white">Espace boutique</Link></li>
            </ul>
          </div>
        </div>
        {/* Bas de page : copyright + mention obligatoire « Powered by Sawali Smart Systems » */}
        <div className="space-y-1 border-t border-white/5 py-5 text-center text-xs text-gray-500">
          <LiensLegaux className="mb-2 justify-center" />
          <p>© {new Date().getFullYear()} adLyn</p>
          <PoweredBySawali />
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
      style={{ backgroundColor: boutique.couleur || "#1e90ff" }}
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
            <div className="relative flex h-24 items-end px-4" style={{ backgroundColor: b.couleur || "#1e90ff" }}>
              {b.mise_en_avant && (
                <span className="badge absolute right-3 top-3 bg-white/90 text-amber-700">⭐ À la une</span>
              )}
              <div className="translate-y-1/2 rounded-2xl bg-white p-1 shadow">
                <LogoBoutique boutique={b} taille="h-14 w-14 text-3xl" />
              </div>
            </div>
            {/* Nom, ville, slogan et code marchand */}
            <div className="flex flex-1 flex-col px-4 pb-4 pt-10">
              <p className="truncate font-display text-lg font-bold group-hover:text-primary">{b.nom}</p>
              {/* Lieu : « Ville, Pays » (seulement les informations renseignées) */}
              <p className="truncate text-sm text-gray-500">📍 {lieuBoutique(b) || "Ville non précisée"}</p>
              <p className="mt-2 line-clamp-2 min-h-[2.5rem] text-sm text-gray-600">{b.slogan || "Téléphones, accessoires et réparations."}</p>
              <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
                <span className="puce text-gray-500">{b.code_marchand}</span>
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
