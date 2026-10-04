import { libelleVersion } from "@/version";

// Mention de version affichée en petits caractères. Les valeurs viennent de la
// source unique src/version.js.
//  - detaille = false (par défaut) : « Version X · déployée le JJ/MM/AAAA HH:MM »
//    → page de connexion et espaces connectés (barre latérale, en-tête, pied).
//  - detaille = true : « Version X · Lot N · commit · déployée le JJ/MM/AAAA HH:MM »
//    → pages de paramétrage / administration (Paramètres).
//  - className : classes Tailwind pour adapter la couleur au fond (clair/sombre).
export default function VersionApp({ className = "", detaille = false }) {
  return (
    <p className={`font-mono text-[11px] tracking-wide ${className}`} title="Version de la plateforme adLyn">
      {libelleVersion(detaille)}
    </p>
  );
}
