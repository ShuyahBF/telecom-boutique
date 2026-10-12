import { useEffect, useState } from "react";

// ============================================================================
// Lot B — petits éléments communs aux écrans « code WhatsApp »
// (connexion par téléphone et inscription « Créer ma boutique »).
// ============================================================================

/**
 * Compte à rebours avant de pouvoir redemander un code (1 envoi par minute).
 * Usage : const [reste, demarrer] = useCompteARebours(); demarrer(60);
 */
export function useCompteARebours() {
  const [reste, setReste] = useState(0);
  useEffect(() => {
    if (reste <= 0) return undefined;
    const t = setTimeout(() => setReste((r) => r - 1), 1000);
    return () => clearTimeout(t);
  }, [reste]);
  return [reste, (secondes) => setReste(Math.max(0, Number(secondes) || 60))];
}

/**
 * Champ du code à 6 chiffres : grand, centré, chiffres seulement, rempli
 * automatiquement par le téléphone (autoComplete « one-time-code »).
 */
export function ChampCode({ id = "code", value, onChange, autoFocus = true }) {
  return (
    <input id={id} className="input bg-papier text-center font-mono text-2xl font-semibold tracking-[0.6em]"
      inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required
      placeholder="••••••" autoFocus={autoFocus}
      value={value} onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))} />
  );
}

/** Pictogramme WhatsApp (bulle verte), sans dépendance externe. */
export function IconeWhatsapp({ className = "h-5 w-5" }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <path fill="#25D366" d="M16 3C9 3 3.3 8.6 3.3 15.6c0 2.4.7 4.7 1.9 6.7L3 29l6.9-2.1c1.9 1 4 1.6 6.1 1.6 7 0 12.7-5.6 12.7-12.6S23 3 16 3z" />
      <path fill="#fff" d="M23.1 19.2c-.4-.2-2.3-1.1-2.6-1.2-.4-.1-.6-.2-.9.2-.3.4-1 1.2-1.2 1.4-.2.2-.4.3-.8.1-.4-.2-1.6-.6-3-1.9-1.1-1-1.9-2.2-2.1-2.6-.2-.4 0-.6.2-.8l.6-.7c.2-.2.3-.4.4-.7.1-.3 0-.5 0-.7l-1.2-2.8c-.3-.7-.6-.6-.9-.6h-.7c-.2 0-.6.1-1 .5-.3.4-1.3 1.3-1.3 3.1s1.3 3.6 1.5 3.9c.2.2 2.6 4 6.3 5.6 2.2.9 3 1 4.1.8.7-.1 2.3-.9 2.6-1.8.3-.9.3-1.7.2-1.8-.1-.2-.3-.3-.7-.5z" />
    </svg>
  );
}
