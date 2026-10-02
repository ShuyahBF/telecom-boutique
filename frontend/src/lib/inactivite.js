import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api";

// ---------------------------------------------------------------------------
// Déconnexion après inactivité (durée réglée par l'administrateur adLyn et le DG,
// lue sur /auth/inactivite). La dernière activité (souris, clavier, toucher,
// défilement, retour sur l'onglet) est PARTAGÉE entre les onglets ouverts via
// le stockage local : une activité dans un onglet garde les autres connectés.
// Le serveur fait le même contrôle (au plus une minute de marge) : l'activité
// lui est signalée au plus toutes les 30 secondes (POST /auth/activite).
// ---------------------------------------------------------------------------
export const CLE_ACTIVITE = "adlyn_derniere_activite";
export const CLE_DECONNEXION = "adlyn_deconnexion_inactivite"; // prévient les autres onglets
const EVENEMENTS = ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "wheel"];
const INTERVALLE_SIGNAL_MS = 30000;

function lireStockage(cle) {
  try { return Number(localStorage.getItem(cle)) || 0; } catch { return 0; }
}

function ecrireStockage(cle, valeur) {
  try { localStorage.setItem(cle, String(valeur)); } catch { /* stockage indisponible */ }
}

/**
 * secondes       : durée d'inactivité tolérée (0 = désactivée)
 * avertissement  : secondes avant la déconnexion où l'avertissement s'affiche
 * onDeconnexion  : appelée à l'échéance (ou quand un autre onglet a déconnecté)
 * Renvoie { restant, resterConnecte } : restant = secondes restantes pendant l'avertissement, sinon null.
 */
export function useInactivite({ secondes, avertissement, onDeconnexion }) {
  const [restant, setRestant] = useState(null);
  const derniere = useRef(Date.now()); // dernière activité vue dans CET onglet
  const dernierSignal = useRef(0);
  const enAvertissement = useRef(false);
  const rappel = useRef(onDeconnexion);
  useEffect(() => { rappel.current = onDeconnexion; }, [onDeconnexion]);

  // Note une activité (partagée entre onglets) et la signale au serveur, au plus toutes les 30 s
  const marquer = useCallback(() => {
    const t = Date.now();
    derniere.current = t;
    ecrireStockage(CLE_ACTIVITE, t);
    if (t - dernierSignal.current > INTERVALLE_SIGNAL_MS) {
      dernierSignal.current = t;
      apiClient.post("/auth/activite").catch(() => { /* session déjà fermée : géré ailleurs */ });
    }
  }, []);

  useEffect(() => {
    if (!secondes) {
      setRestant(null);
      return undefined;
    }
    let fini = false;
    const verifier = () => {
      if (fini) return true;
      const derniereActivite = Math.max(derniere.current, lireStockage(CLE_ACTIVITE));
      const reste = secondes - (Date.now() - derniereActivite) / 1000;
      if (reste <= 0) {
        fini = true;
        setRestant(null);
        rappel.current?.(true);
        return true;
      }
      enAvertissement.current = reste <= avertissement;
      setRestant(enAvertissement.current ? Math.ceil(reste) : null);
      return false;
    };
    // Activité : ignorée pendant l'avertissement (il faut cliquer « Rester connecté »)
    let derniereNote = 0;
    const surActivite = () => {
      if (enAvertissement.current || Date.now() - derniereNote < 1000) return;
      derniereNote = Date.now();
      marquer();
    };
    // Retour sur l'onglet : d'abord vérifier l'échéance (minuteries ralenties en arrière-plan)
    const surVisibilite = () => {
      if (document.visibilityState === "visible" && !verifier() && !enAvertissement.current) marquer();
    };
    // Autre onglet déconnecté pour inactivité : celui-ci aussi
    const surStockage = (e) => {
      if (e.key === CLE_DECONNEXION && e.newValue && !fini) {
        fini = true;
        rappel.current?.(false);
      }
    };
    marquer();
    EVENEMENTS.forEach((ev) => window.addEventListener(ev, surActivite, { passive: true }));
    document.addEventListener("visibilitychange", surVisibilite);
    window.addEventListener("storage", surStockage);
    const tic = setInterval(verifier, 1000);
    return () => {
      fini = true;
      clearInterval(tic);
      EVENEMENTS.forEach((ev) => window.removeEventListener(ev, surActivite));
      document.removeEventListener("visibilitychange", surVisibilite);
      window.removeEventListener("storage", surStockage);
    };
  }, [secondes, avertissement, marquer]);

  const resterConnecte = useCallback(() => {
    enAvertissement.current = false;
    dernierSignal.current = 0; // signale tout de suite l'activité au serveur
    marquer();
    setRestant(null);
  }, [marquer]);

  return { restant, resterConnecte };
}

/** Durée affichée « 15 min », « 1 h 30 min », « 45 s ». */
export function dureeTexte(secondes) {
  const s = Number(secondes) || 0;
  if (!s) return "désactivée";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return [h && `${h} h`, m && `${m} min`, r && `${r} s`].filter(Boolean).join(" ");
}
