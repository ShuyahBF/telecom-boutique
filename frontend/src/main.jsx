import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.jsx";
// Règle 9 — Ctrl + Espace / double-clic : reprendre le texte par défaut (gris) d'un champ pour le modifier
import { installerValeurParDefaut } from "./lib/valeurParDefaut";

installerValeurParDefaut();

// Application installable (Android / PWABuilder) : service worker enregistré DÈS le démarrage du site
// (il affiche la page « Pas de connexion » quand le réseau est coupé ; rien d'autre n'est mis en cache).
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

// Garde de côté l'invitation d'installation de Chrome (événement « beforeinstallprompt »),
// même si elle arrive avant l'affichage du bouton « Installer l'application ».
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); window.__adlynInvite = e; });

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
