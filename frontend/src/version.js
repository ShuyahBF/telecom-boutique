// =============================================================================
// VERSION ET LOT DE LA PLATEFORME adLyn — SOURCE UNIQUE
// =============================================================================
// Ce fichier est le SEUL endroit où l'on déclare la version et le lot.
// Affichage (composant components/VersionApp.jsx) :
//   - page de connexion et espaces connectés (boutique et plateforme) :
//     libellé COURT « Version X · déployée le JJ/MM/AAAA HH:MM » ;
//   - pages de paramétrage / administration (Paramètres) :
//     libellé DÉTAILLÉ « Version X · Lot N · commit · déployée le JJ/MM/AAAA HH:MM ».
//
// À CHAQUE DÉPLOIEMENT (chaque Pull Request fusionnée dans « main ») :
//   1. VERSION : ajouter 1 au nombre ci-dessous (1 → 2 → 3…).
//   2. LOT     : mettre le numéro de la Pull Request GitHub qui sera fusionnée
//                pour ce déploiement (ex. PR #26 → LOT = 26).
//
// Pourquoi ce fichier est dans le dossier « frontend » : sur Render, le site
// (service adlyn-frontend, rootDir: frontend) ne se reconstruit QUE si un
// fichier de ce dossier change. Comme ce fichier change à chaque déploiement,
// le site est toujours reconstruit et l'affichage est toujours à jour, même
// quand la modification ne concerne que le serveur (backend).
//
// Le code court du commit (ex. « 66e6df4 ») et la date de compilation sont,
// eux, calculés AUTOMATIQUEMENT à la compilation (voir vite.config.js) :
// rien à saisir à la main.
// =============================================================================

// Compteur de déploiements : +1 à chaque déploiement
export const VERSION = 6;

// Numéro de la Pull Request GitHub fusionnée pour ce déploiement
export const LOT = 27;

// Valeurs injectées par Vite au moment de « npm run build » (vite.config.js).
// Le « typeof » évite une erreur si le fichier est lu hors de Vite (tests, etc.).
export const COMMIT = typeof __ADLYN_COMMIT__ !== "undefined" ? __ADLYN_COMMIT__ : "local";
export const DATE_COMPILATION = typeof __ADLYN_DATE_COMPILATION__ !== "undefined" ? __ADLYN_DATE_COMPILATION__ : "";

// Date/heure de déploiement au format français court (« 04/10/2026 21:10 »).
// C'est la date de compilation du site : sur Render, le site est recompilé à
// chaque déploiement (ce fichier change à chaque fois), elle est donc fiable.
// Renvoie "" si la date est absente (hors compilation Vite).
export function dateDeploiement() {
  if (!DATE_COMPILATION) return "";
  const d = new Date(DATE_COMPILATION);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

// Construit le libellé de version affiché à l'écran.
//  - detaille = false (par défaut) : « Version 4 · déployée le 04/10/2026 21:10 »
//    → page de connexion, barre latérale, en-tête et pied des pages connectées.
//  - detaille = true : « Version 4 · Lot 26 · 66e6df4 · déployée le 04/10/2026 21:10 »
//    → pages de paramétrage / administration uniquement.
export function libelleVersion(detaille = false) {
  const date = dateDeploiement();
  const morceaux = [`Version ${VERSION}`];
  if (detaille) morceaux.push(`Lot ${LOT}`, COMMIT);
  if (date) morceaux.push(`déployée le ${date}`);
  return morceaux.join(" · ");
}

// Textes prêts à l'emploi (calculés une fois au chargement du site)
export const TEXTE_VERSION = libelleVersion(false);
export const TEXTE_VERSION_DETAILLE = libelleVersion(true);
