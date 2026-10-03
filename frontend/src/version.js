// =============================================================================
// VERSION ET LOT DE LA PLATEFORME adLyn — SOURCE UNIQUE
// =============================================================================
// Ce fichier est le SEUL endroit où l'on déclare la version et le lot.
// Ils sont affichés sur la page de connexion et dans tous les espaces connectés
// (boutique et plateforme) par le composant components/VersionApp.jsx.
//
// À CHAQUE DÉPLOIEMENT (chaque Pull Request fusionnée dans « main ») :
//   1. VERSION : ajouter 1 au nombre ci-dessous (1 → 2 → 3…).
//   2. LOT     : mettre le numéro de la Pull Request GitHub qui sera fusionnée
//                pour ce déploiement (ex. PR #22 → LOT = 22).
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
export const VERSION = 1;

// Numéro de la Pull Request GitHub fusionnée pour ce déploiement
export const LOT = 22;

// Valeurs injectées par Vite au moment de « npm run build » (vite.config.js).
// Le « typeof » évite une erreur si le fichier est lu hors de Vite (tests, etc.).
export const COMMIT = typeof __ADLYN_COMMIT__ !== "undefined" ? __ADLYN_COMMIT__ : "local";
export const DATE_COMPILATION = typeof __ADLYN_DATE_COMPILATION__ !== "undefined" ? __ADLYN_DATE_COMPILATION__ : "";

// Texte affiché à l'écran : « Version 1 · Lot 22 · 66e6df4 »
export const TEXTE_VERSION = `Version ${VERSION} · Lot ${LOT} · ${COMMIT}`;
