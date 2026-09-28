// Image d'un produit, ou à défaut un grand emoji selon son type :
// 📱 pour un téléphone (TEL), 🎧 pour un accessoire (ACC), 🔧 pour une pièce, 🛠️ pour un service.
const EMOJIS = { TEL: "📱", ACC: "🎧", PIE: "🔧", SER: "🛠️" };

export default function VisuelProduit({ produit, className = "", tailleEmoji = "text-5xl" }) {
  // Cas 1 : le produit a une photo -> on l'affiche en entier (object-contain)
  if (produit.image_url) {
    return (
      <div className={`flex items-center justify-center bg-white ${className}`}>
        <img src={produit.image_url} alt={produit.nom} loading="lazy" className="h-full w-full object-contain p-2" />
      </div>
    );
  }
  // Cas 2 : pas de photo -> emoji sur un fond gris clair
  return (
    <div className={`flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 ${className}`}>
      <span className={tailleEmoji} aria-hidden="true">{EMOJIS[produit.type_produit] || "📦"}</span>
    </div>
  );
}
