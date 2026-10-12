// Pictogramme « Partager » universel : trois points reliés (celui d'Android, de WhatsApp,
// de YouTube…). Dessiné en SVG pour rester net à toutes les tailles et prendre la
// couleur du texte qui l'entoure (currentColor).
// Règle du propriétaire : tous les pictogrammes affichés doivent être intuitifs et usuels.
export default function IconePartage({ className = "h-4 w-4" }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {/* Les trois points : un en haut à droite, un à gauche, un en bas à droite */}
      <circle cx="18" cy="5" r="3" />
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="19" r="3" />
      {/* Les deux traits qui les relient */}
      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
    </svg>
  );
}
