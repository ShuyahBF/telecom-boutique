// En-tête standard d'une page du back-office : titre, sous-titre et boutons d'action.
export default function EnTetePage({ titre, sousTitre, children }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-extrabold">{titre}</h1>
        {sousTitre && <p className="text-sm text-gray-500">{sousTitre}</p>}
      </div>
      {children && <div className="no-print flex flex-wrap gap-2">{children}</div>}
    </div>
  );
}
