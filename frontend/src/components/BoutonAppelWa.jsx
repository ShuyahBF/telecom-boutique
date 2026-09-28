// Bouton « Appel WA » (appel WhatsApp vers la boutique), affiché GRISÉ :
// la fonction d'appel par l'API WhatsApp (Calling API de Meta) n'est pas encore
// branchée. Le bouton est visible pour annoncer le service, mais inactif.
// - sombre = true : version pour fond bleu nuit (pied de page de la vitrine)
// - sombre = false : version pour fond clair (fiche produit)
export default function BoutonAppelWa({ sombre = false, className = "" }) {
  return (
    <button
      type="button"
      disabled // inactif tant que les appels WhatsApp ne sont pas disponibles
      title="Bientôt disponible"
      aria-label="Appel WA (bientôt disponible)"
      className={`btn cursor-not-allowed opacity-100 ${sombre
        ? "border border-white/10 bg-white/5 text-gray-500"
        : "border border-gray-200 bg-gray-100 text-gray-400"} ${className}`}
    >
      {/* Pictogramme téléphone + intitulé demandé */}
      <span aria-hidden="true">📞</span> Appel WA
      <span className="text-[10px] font-medium uppercase tracking-wider opacity-80">· bientôt</span>
    </button>
  );
}
