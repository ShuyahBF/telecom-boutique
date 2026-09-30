import { useEffect } from "react";
import { Link } from "react-router-dom";
import { IconeAdlyn, LogoAdlyn } from "@/components/Marque";
import PoweredBySawali from "@/components/PoweredBySawali";

// Mise en page commune des pages légales publiques d'adLyn
// (Politique de confidentialité, Conditions d'utilisation).
// - titreOnglet : titre de l'onglet du navigateur. Il reprend EXACTEMENT le nom
//   de l'app (« adLyn Privacy Policy », « adLyn Terms of Service ») : c'est ce
//   que vérifient les revues d'applications (TikTok, Meta…).
// - titre / sousTitre : titre affiché en haut de la page
// - miseAJour : date de dernière mise à jour affichée sous le titre
export default function PageLegale({ titreOnglet, titre, sousTitre, miseAJour, children }) {
  // Titre de l'onglet pendant l'affichage de la page, puis retour au titre d'accueil
  useEffect(() => {
    document.title = titreOnglet;
    window.scrollTo(0, 0);
    return () => { document.title = "adLyn"; };
  }, [titreOnglet]);

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      {/* En-tête bleu nuit : logo adLyn (retour à l'accueil) */}
      <header className="bg-nuit-900 text-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-4">
          <Link to="/" aria-label="adLyn, accueil"><LogoAdlyn clair className="h-8 sm:h-9" /></Link>
          <Link to="/" className="text-sm text-gray-300 hover:text-white">← Accueil</Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-10">
        {/* Icône + nom de l'app en tête de page (demandé par les revues d'applications) */}
        <div className="mb-6 flex items-center gap-3">
          <IconeAdlyn className="h-12 w-12 rounded-lg bg-white p-1 shadow-sm ring-1 ring-gray-200" />
          <span className="font-display text-lg font-semibold text-ink">adLyn</span>
        </div>
        <h1 className="font-display text-3xl font-bold text-ink sm:text-4xl">{titre}</h1>
        {sousTitre && <p className="mt-2 text-lg text-gray-600">{sousTitre}</p>}
        <p className="mt-2 text-sm text-gray-500">Dernière mise à jour : {miseAJour}</p>

        {/* Contenu de la page : sections <Section> */}
        <div className="mt-8 space-y-8 rounded-2xl bg-white p-6 text-[15px] leading-relaxed text-gray-700 shadow-sm ring-1 ring-gray-200 sm:p-10">
          {children}
        </div>
      </main>

      {/* Pied de page : liens légaux + mention obligatoire « Powered by Sawali Smart Systems » */}
      <footer className="bg-nuit-950 py-6 text-center text-xs text-gray-500">
        <LiensLegaux className="justify-center" />
        <p className="mt-2">© {new Date().getFullYear()} adLyn</p>
        <PoweredBySawali className="mt-1" />
      </footer>
    </div>
  );
}

// Une section numérotée d'une page légale : titre + paragraphes
export function Section({ titre, children }) {
  return (
    <section>
      <h2 className="mb-3 font-display text-xl font-semibold text-ink">{titre}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

// Liens vers les deux pages légales, réutilisés dans les pieds de page et en-têtes.
// clair = true : liens gris clair pour fond bleu nuit (par défaut) ; false : fond clair.
export function LiensLegaux({ clair = true, className = "" }) {
  const style = clair ? "text-gray-300 hover:text-white" : "text-gray-500 hover:text-ink";
  return (
    <p className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-xs ${className}`}>
      <Link to="/confidentialite" className={`hover:underline ${style}`}>Politique de confidentialité</Link>
      <Link to="/conditions" className={`hover:underline ${style}`}>Conditions d'utilisation</Link>
    </p>
  );
}
