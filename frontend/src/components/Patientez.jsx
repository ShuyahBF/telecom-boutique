// ============================================================================
// « PATIENTEZ… » (règle permanente du propriétaire, comme sur SAWALI) — lot 25
// ============================================================================
// Pendant une attente longue (recherche, chargement d'une liste…) : un petit
// toast « Patientez… » en haut de l'écran ET une jauge circulaire transparente
// (un arc qui tourne) au centre. Rien n'est affiché quand `actif` est faux.
// Usage : <Patientez actif={chargement} />
// ============================================================================
export default function Patientez({ actif, texte = "Patientez…" }) {
  if (!actif) return null;
  return (
    <>
      {/* Toast en haut de l'écran */}
      <div className="no-print pointer-events-none fixed inset-x-0 top-4 z-[90] flex justify-center px-4" role="status" aria-live="polite">
        <div className="rounded-full bg-ink/90 px-5 py-2.5 text-sm font-semibold text-white shadow-xl backdrop-blur">
          {texte}
        </div>
      </div>
      {/* Jauge circulaire transparente : anneau pâle + arc coloré qui tourne */}
      <div className="no-print pointer-events-none fixed inset-0 z-[85] flex items-center justify-center" aria-hidden="true">
        <span className="h-14 w-14 animate-spin rounded-full border-4 border-primary/15 border-t-primary/80" />
      </div>
    </>
  );
}
