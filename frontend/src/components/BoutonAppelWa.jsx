// Bouton « WhatsApp » : ouvre la conversation WhatsApp avec la boutique
// (lien wa.me vers son numéro). Sans numéro valable, le bouton n'est pas affiché :
// aucune mention « bientôt » sur les pages publiques (les revues d'applications
// TikTok/Meta refusent les sites qui paraissent inachevés).
// - telephone : numéro de la boutique (ex. « +226 70 00 00 00 » ou « 70 00 00 00 »)
// - sombre = true : version pour fond bleu nuit (pied de page de la vitrine)
export default function BoutonAppelWa({ telephone, sombre = false, className = "" }) {
  const numero = numeroWhatsApp(telephone);
  if (!numero) return null;
  return (
    <a
      href={`https://wa.me/${numero}`}
      target="_blank"
      rel="noopener noreferrer"
      className={`btn ${sombre ? "border border-white/15 bg-white/5 text-gray-200 hover:bg-white/10" : "btn-outline"} ${className}`}
    >
      <span aria-hidden="true">📞</span> WhatsApp
    </a>
  );
}

// Numéro au format wa.me (chiffres seuls, avec indicatif) ; 8 chiffres = Burkina Faso (+226)
function numeroWhatsApp(telephone) {
  const brut = (telephone || "").trim();
  let chiffres = brut.replace(/\D/g, "");
  if (brut.startsWith("00")) chiffres = chiffres.slice(2);
  else if (!brut.startsWith("+") && chiffres.length === 8) chiffres = `226${chiffres}`;
  return chiffres.length >= 10 && chiffres.length <= 15 ? chiffres : "";
}
