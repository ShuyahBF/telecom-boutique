import { useEffect } from "react";

// Fenêtre modale : fond grisé, fermeture par ✕, clic à l'extérieur ou touche Échap.
// Charte « Ondes & comptoir » : voile bleu nuit, fenêtre aux angles plus ronds
// que les cartes (rounded-3xl) et seule ombre portée marquée de l'interface.
export default function Modal({ ouvert, titre, onFermer, children, large = false }) {
  useEffect(() => {
    if (!ouvert) return undefined;
    const surTouche = (e) => e.key === "Escape" && onFermer?.();
    window.addEventListener("keydown", surTouche);
    return () => window.removeEventListener("keydown", surTouche);
  }, [ouvert, onFermer]);

  if (!ouvert) return null;
  return (
    <div className="no-print fixed inset-0 z-50 flex items-end justify-center bg-ink/50 p-0 backdrop-blur-[2px] sm:items-center sm:p-4" onClick={onFermer}>
      <div
        className={`max-h-[92vh] w-full animate-slide-up overflow-y-auto rounded-t-3xl bg-white p-5 shadow-[0_24px_60px_-12px_rgba(18,26,44,0.45)] sm:rounded-3xl sm:p-6 ${large ? "sm:max-w-3xl" : "sm:max-w-lg"}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-4 border-b border-gray-100 pb-3">
          <h2 className="text-xl font-bold">{titre}</h2>
          <button type="button" onClick={onFermer} className="flex h-8 w-8 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 hover:text-ink" aria-label="Fermer">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}
