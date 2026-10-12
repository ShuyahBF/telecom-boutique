// ============================================================================
// CHAMPS DU SECTEUR D'ACTIVITÉ sur la fiche article (lot A)
// ============================================================================
// Chaque secteur (prêt-à-porter, cosmétiques, quincaillerie…) définit ses propres
// champs dans « Plateforme > Secteurs d'activité » : Taille, Couleur, Date de
// péremption, ISBN… Ils arrivent avec la boutique (boutique.champs_secteur) et
// leurs valeurs sont enregistrées sur l'article dans `attributs = {cle: valeur}`.
// Types gérés : texte, nombre, date, liste (un choix), multi_liste (plusieurs choix).
// Le serveur refait les contrôles (obligatoire, type, valeurs proposées).
// ============================================================================
import { Champ } from "../_atelier/communs";

/**
 * Section « Caractéristiques » (titre selon le vocabulaire du secteur).
 * Props : champs (liste du secteur), attributs (valeurs), onChange(nouveauxAttributs),
 *         titre (texte de l'en-tête), desactive (lecture seule).
 */
export default function ChampsSecteur({ champs, attributs, onChange, titre, desactive = false }) {
  if (!champs?.length) return null;
  const valeurs = attributs || {};
  // Change la valeur d'un champ en gardant les autres
  const maj = (cle, valeur) => onChange({ ...valeurs, [cle]: valeur });

  return (
    <div className="card grid gap-4 sm:grid-cols-2">
      <h2 className="font-bold sm:col-span-2">{titre}</h2>
      {champs.map((c) => {
        const libelle = `${c.libelle}${c.obligatoire ? " *" : ""}`;
        const valeur = valeurs[c.cle];

        // Plusieurs choix : une case à cocher par valeur proposée (pastilles)
        if (c.type === "multi_liste") {
          const choisis = Array.isArray(valeur) ? valeur : [];
          const basculer = (option) => maj(c.cle, choisis.includes(option)
            ? choisis.filter((o) => o !== option) : [...choisis, option]);
          return (
            <div key={c.cle} className="sm:col-span-2">
              <p className="label">{libelle}</p>
              <div className="flex flex-wrap gap-2">
                {(c.options || []).map((option) => (
                  <label key={option} className={`cursor-pointer rounded-full border px-3 py-1 text-sm ${choisis.includes(option) ? "border-primary bg-primary/10 font-semibold text-primary" : "border-gray-300 text-gray-700"}`}>
                    <input type="checkbox" className="sr-only" disabled={desactive} checked={choisis.includes(option)} onChange={() => basculer(option)} />
                    {option}
                  </label>
                ))}
              </div>
            </div>
          );
        }

        // Un seul choix : liste déroulante des valeurs proposées
        if (c.type === "liste") {
          return (
            <Champ key={c.cle} label={libelle}>
              <select className="input" disabled={desactive} required={c.obligatoire} value={valeur || ""} onChange={(e) => maj(c.cle, e.target.value)}>
                <option value="">— Choisir —</option>
                {(c.options || []).map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            </Champ>
          );
        }

        // Texte, nombre ou date : zone de saisie du type correspondant
        const typeSaisie = c.type === "date" ? "date" : c.type === "nombre" ? "number" : "text";
        return (
          <Champ key={c.cle} label={libelle}>
            <input className="input" type={typeSaisie} step={c.type === "nombre" ? "any" : undefined} disabled={desactive}
              required={c.obligatoire} maxLength={c.type === "texte" ? 500 : undefined}
              value={valeur ?? ""} onChange={(e) => maj(c.cle, e.target.value)} />
          </Champ>
        );
      })}
    </div>
  );
}
