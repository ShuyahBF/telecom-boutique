import axios from "axios";
import { API_BASE_URL } from "@/lib/api";

// =============================================================================
// « Mon espace » : appels de l'espace client PUBLIC d'une boutique
// =============================================================================
// Session du CLIENT (pas du personnel) : après le code reçu par WhatsApp, le serveur
// renvoie un jeton chiffré et pose aussi un cookie HttpOnly.
//  - Le jeton est gardé UNIQUEMENT EN MÉMOIRE (variable ci-dessous) : jamais dans le
//    stockage du navigateur. Fermer l'onglet = se déconnecter.
//  - Le cookie HttpOnly prend le relais si la page est rechargée (quand le navigateur
//    l'accepte ; certains bloquent les cookies d'un autre domaine).
// La session expire après 30 minutes sans action (contrôle côté serveur).
// =============================================================================
let jetonSession = "";

export function definirJeton(jeton) {
  jetonSession = jeton || "";
}

// Client HTTP dédié : il n'envoie JAMAIS l'en-tête « X-Boutique-Id » du personnel
export const apiEspace = axios.create({ baseURL: API_BASE_URL, withCredentials: true, headers: { "X-Adlyn": "1" } });

apiEspace.interceptors.request.use((config) => {
  if (jetonSession) config.headers["X-Espace-Client"] = jetonSession;
  return config;
});

// Mémoire de l'onglet : jeton du QR code scanné, pour reconnaître le client sur la
// vitrine de la boutique (le jeton est chiffré : il ne contient aucun numéro en clair)
const CLE_QR = "adlyn_qr_boutique";

export function memoriserQr(slug, jeton) {
  try { sessionStorage.setItem(`${CLE_QR}_${slug}`, jeton); } catch { /* stockage indisponible */ }
}

export function qrMemorise(slug) {
  try { return sessionStorage.getItem(`${CLE_QR}_${slug}`) || ""; } catch { return ""; }
}
