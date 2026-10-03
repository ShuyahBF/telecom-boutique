import { DATE_COMPILATION, TEXTE_VERSION } from "@/version";

// Petite mention « Version X · Lot N · commit » affichée sur la page de
// connexion et dans les espaces connectés. Les valeurs viennent de la source
// unique src/version.js. Au survol, une bulle donne la date de compilation.
//  - className : classes Tailwind pour adapter la couleur au fond (clair/sombre).
export default function VersionApp({ className = "" }) {
  const infobulle = DATE_COMPILATION
    ? `Compilé le ${new Date(DATE_COMPILATION).toLocaleString("fr-FR")}`
    : "Version de la plateforme adLyn";
  return (
    <p className={`font-mono text-[11px] tracking-wide ${className}`} title={infobulle}>
      {TEXTE_VERSION}
    </p>
  );
}
