// Barre de progression en étapes (suivi de commande, suivi de réparation).
// - etapes : liste des libellés, ex. ["Reçue", "Confirmée", ...]
// - etape  : numéro de l'étape atteinte (1 = première ; 0 = hors parcours)
// - annule : si vrai, la barre est grisée (commande annulée, appareil irréparable)
export default function BarreEtapes({ etapes, etape, annule = false }) {
  return (
    <ol className="flex items-start">
      {etapes.map((libelle, i) => {
        const numero = i + 1;
        const faite = !annule && numero <= etape; // étape atteinte ou dépassée
        const courante = !annule && numero === etape; // étape en cours
        return (
          <li key={libelle} className="relative flex flex-1 flex-col items-center text-center">
            {/* Trait qui relie cette étape à la précédente */}
            {i > 0 && (
              <span className={`absolute right-1/2 top-4 h-1 w-full -translate-y-1/2 ${faite ? "bg-boutique" : "bg-gray-200"}`} />
            )}
            {/* Pastille numérotée (✓ si l'étape est terminée) */}
            <span
              className={`relative z-10 flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold
                ${faite ? "bg-boutique text-white" : "border-2 border-gray-200 bg-white text-gray-400"}
                ${courante ? "ring-4 ring-gray-200" : ""}`}
            >
              {faite && !courante ? "✓" : numero}
            </span>
            {/* Libellé sous la pastille */}
            <span className={`mt-2 px-0.5 text-[11px] leading-tight sm:text-xs ${courante ? "font-bold text-ink" : faite ? "text-gray-700" : "text-gray-400"}`}>
              {libelle}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
