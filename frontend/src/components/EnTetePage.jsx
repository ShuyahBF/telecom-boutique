// En-tête standard d'une page du back-office : titre, sous-titre et boutons d'action.
// Refonte « Ondes & comptoir » : grand titre en Bricolage Grotesque (classe
// .titre-page de index.css), sous-titre limité en largeur pour rester lisible,
// filet fin sous l'en-tête pour séparer le titre du contenu.
export default function EnTetePage({ titre, sousTitre, children }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-gray-200/80 pb-5">
      <div className="min-w-0">
        <h1 className="titre-page">{titre}</h1>
        {sousTitre && <p className="mt-1 max-w-2xl text-sm text-gray-500">{sousTitre}</p>}
      </div>
      {children && <div className="no-print flex flex-wrap gap-2">{children}</div>}
    </div>
  );
}
