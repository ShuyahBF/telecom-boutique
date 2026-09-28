import { useEffect } from "react";

// Fenêtre modale : fond grisé, fermeture par ✕, clic à l'extérieur ou touche Échap.
export default function Modal({ ouvert, titre, onFermer, children, large = false }) {
  useEffect(() => {
    if (!ouvert) return undefined;
    const surTouche = (e) => e.key === "Escape" && onFermer?.();
    window.addEventListener("keydown", surTouche);
    return () => window.removeEventListener("keydown", surTouche);
  }, [ouvert, onFermer]);

  if (!ouvert) return null;
  return (
    <div className="no-print fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4" onClick={onFermer}>
      <div
        className={`max-h-[92vh] w-full animate-slide-up overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-2xl ${large ? "sm:max-w-3xl" : "sm:max-w-lg"}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-4">
          <h2 className="text-lg font-bold">{titre}</h2>
          <button type="button" onClick={onFermer} className="rounded-full p-1 text-gray-500 hover:bg-gray-100" aria-label="Fermer">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}
