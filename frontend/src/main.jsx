import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.jsx";
// Règle 9 — Ctrl + Espace / double-clic : reprendre le texte par défaut (gris) d'un champ pour le modifier
import { installerValeurParDefaut } from "./lib/valeurParDefaut";

installerValeurParDefaut();

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
