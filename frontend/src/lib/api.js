import axios from "axios";

// Adresse de l'API : VITE_API_BASE_URL si définie au build, sinon le serveur
// local en développement. (En production elle est fixée dans render.yaml.)
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

export const apiClient = axios.create({ baseURL: API_BASE_URL });

// Clés de stockage local du navigateur
export const TOKEN_KEY = "tlb_token";
export const BOUTIQUE_ACTIVE_KEY = "tlb_boutique_active"; // super-admin : boutique consultée

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // Le super-administrateur choisit la boutique qu'il consulte (ignoré pour les autres rôles)
  const boutique = localStorage.getItem(BOUTIQUE_ACTIVE_KEY);
  if (boutique) config.headers["X-Boutique-Id"] = boutique;
  return config;
});

// Messages génériques du framework (toujours en anglais) : jamais affichés tels quels
const MESSAGES_GENERIQUES = new Set([
  "not found", "method not allowed", "internal server error", "unauthorized",
  "forbidden", "unprocessable entity", "bad request",
]);

/**
 * Transforme une erreur d'API en phrase affichable en français.
 * FastAPI renvoie `detail` en texte (nos messages, déjà en français) ou en
 * liste d'erreurs de validation (en anglais, techniques) : dans ce second cas
 * on affiche le message de repli.
 */
export function messageErreur(err, repli = "Une erreur est survenue") {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") {
    return MESSAGES_GENERIQUES.has(detail.trim().toLowerCase()) ? repli : detail;
  }
  if (!err?.response) return "Serveur injoignable. Vérifiez votre connexion.";
  return repli;
}
