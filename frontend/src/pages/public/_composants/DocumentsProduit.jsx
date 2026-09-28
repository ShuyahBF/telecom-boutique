// Liste des documents qu'une boutique a choisi de montrer à ses clients pour un
// produit (brochure, fiche technique, manuel...). Chaque document est un lien
// de téléchargement qui s'ouvre dans un nouvel onglet.
// documents = [{ titre, type, url }] (renvoyés par l'API publique)

// Icône et libellé affichés selon le type de document
const TYPES = {
  BROCHURE: { icone: "📰", libelle: "Brochure" },
  FICHE_TECHNIQUE: { icone: "📋", libelle: "Fiche technique" },
  MANUEL: { icone: "📘", libelle: "Manuel d'utilisation" },
  CONSEILS: { icone: "💡", libelle: "Conseils d'utilisation" },
  PHOTO: { icone: "🖼️", libelle: "Photo" },
  AUTRE: { icone: "📄", libelle: "Document" },
};

export default function DocumentsProduit({ documents }) {
  if (!documents?.length) return null;
  return (
    <div>
      <h2 className="mb-2 font-bold">Documents à télécharger</h2>
      <ul className="divide-y divide-gray-100 rounded-2xl border border-gray-200 bg-white">
        {documents.map((d) => {
          const type = TYPES[d.type] || TYPES.AUTRE;
          return (
            <li key={d.url}>
              {/* download : propose l'enregistrement du fichier ; target : sinon ouverture dans un nouvel onglet */}
              <a href={d.url} target="_blank" rel="noopener noreferrer" download
                className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50">
                <span className="text-2xl" aria-hidden="true">{type.icone}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-gray-800">{d.titre}</span>
                  <span className="block text-xs text-gray-500">{type.libelle}</span>
                </span>
                <span className="shrink-0 text-sm font-semibold text-boutique">⬇ Télécharger</span>
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
