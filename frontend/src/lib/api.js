import axios from "axios";

// Adresse de l'API : VITE_API_BASE_URL si définie au build, sinon le serveur
// local en développement. (En production elle est fixée dans render.yaml.)
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

// Session du personnel : cookie HttpOnly posé par le serveur à la connexion
// (withCredentials = le navigateur l'envoie à chaque appel). Le JavaScript du
// site ne peut pas le lire : ni jeton ni mot de passe dans le stockage local.
// L'en-tête « X-Adlyn » prouve au serveur que l'appel vient bien du site
// (protection contre les requêtes forgées depuis un autre site, CSRF).
export const apiClient = axios.create({ baseURL: API_BASE_URL, withCredentials: true, headers: { "X-Adlyn": "1" } });

// Clés de stockage local du navigateur
export const BOUTIQUE_ACTIVE_KEY = "tlb_boutique_active"; // super-admin : boutique consultée
// Ancien jeton (versions précédentes du site) : effacé, la session est désormais dans le cookie
try { localStorage.removeItem("tlb_token"); } catch { /* stockage indisponible */ }

// --- ID boutique mémorisé (cookie simple, lisible par le site, 1 an) ---
// Seul l'ID boutique est retenu pour préremplir la connexion : jamais le mot de passe.
const COOKIE_ID_BOUTIQUE = "adlyn_id_boutique";

/** ID boutique mémorisé lors de la dernière connexion ("" s'il n'y en a pas). */
export function idBoutiqueMemorise() {
  const trouve = document.cookie.split("; ").find((c) => c.startsWith(`${COOKIE_ID_BOUTIQUE}=`));
  return trouve ? decodeURIComponent(trouve.split("=")[1]) : "";
}

/** Mémorise (ou oublie, si vide) l'ID boutique. */
export function memoriserIdBoutique(code) {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = code
    ? `${COOKIE_ID_BOUTIQUE}=${encodeURIComponent(code)}; Max-Age=${365 * 24 * 3600}; Path=/; SameSite=Lax${secure}`
    : `${COOKIE_ID_BOUTIQUE}=; Max-Age=0; Path=/`;
}

apiClient.interceptors.request.use((config) => {
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
