// Mention obligatoire en bas de chaque page publique d'adLyn :
// adLyn est un produit de SAWALI SMART SYSTEMS (entité titulaire du compte PawaPay).
// - sombre = true : texte clair pour fond bleu nuit (pieds de page, connexion)
// - sombre = false : texte gris pour fond clair
export default function PoweredBySawali({ sombre = true, className = "" }) {
  return (
    <p className={`text-xs ${sombre ? "text-gray-500" : "text-gray-400"} ${className}`}>
      Powered by{" "}
      <a
        href="https://sawalismartsystems.com"
        target="_blank"
        rel="noopener noreferrer"
        className={`font-semibold hover:underline ${sombre ? "text-gray-300 hover:text-white" : "text-gray-600 hover:text-ink"}`}
      >
        Sawali Smart Systems
      </a>
    </p>
  );
}
