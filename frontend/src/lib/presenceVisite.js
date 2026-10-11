// =============================================================================
// Lot 39 — VISITES DU SITE SIGNALÉES À SAWALI (alerte WhatsApp du propriétaire)
// =============================================================================
// À l'ouverture du site, si PERSONNE n'est connecté, le navigateur prévient le
// serveur adLyn (POST /api/presence/visite), qui relaie un signal signé à SAWALI.
//  - au plus UNE fois toutes les 30 minutes par navigateur ;
//  - identifiant ANONYME tiré au hasard (aucune donnée personnelle), gardé dans
//    le stockage local du navigateur avec l'heure du dernier signal ;
//  - silencieux : aucune erreur n'est jamais montrée ni remontée (try/catch).
// Le serveur filtre aussi les robots et limite à 1 signal / 30 min par visiteur ou IP.
// =============================================================================
import { apiClient } from "@/lib/api";

const CLE_VISITEUR = "adlyn_visiteur";           // identifiant anonyme du navigateur
const CLE_DERNIERE = "adlyn_visite_signalee";    // heure (ms) du dernier signal
const INTERVALLE_MS = 30 * 60 * 1000;           // 30 minutes

/** Identifiant anonyme du navigateur (créé au premier passage). */
function identifiantVisiteur() {
  let id = localStorage.getItem(CLE_VISITEUR);
  if (!id || !/^[A-Za-z0-9_-]{8,64}$/.test(id)) {
    // Tirage aléatoire : crypto.randomUUID si disponible, sinon Math.random
    id = (window.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`)
      .replace(/[^A-Za-z0-9_-]/g, "");
    localStorage.setItem(CLE_VISITEUR, id);
  }
  return id;
}

/** Signale la visite (si le dernier signal date de plus de 30 minutes). Ne lève jamais d'erreur. */
export function signalerVisite(page) {
  try {
    const derniere = Number(localStorage.getItem(CLE_DERNIERE) || 0);
    if (Date.now() - derniere < INTERVALLE_MS) return;
    // Heure notée AVANT l'appel : pas de second envoi si la page est rechargée aussitôt
    localStorage.setItem(CLE_DERNIERE, String(Date.now()));
    apiClient
      .post("/presence/visite", { visiteur: identifiantVisiteur(), page: String(page || "/").slice(0, 200) })
      .catch(() => { /* serveur injoignable : sans importance */ });
  } catch {
    /* stockage indisponible (navigation privée…) : on ne signale rien */
  }
}
