// ============================================================================
// VOCABULAIRE PAR SECTEUR D'ACTIVITÉ (lot A)
// ============================================================================
// adLyn sert tout type de commerce : une boutique de prêt-à-porter parle
// d'« Articles » rangés en « Rayons », une quincaillerie de « Familles »…
// Le serveur envoie avec la boutique (/auth/me, /boutique) :
//   - boutique.secteur          : code du secteur (ex. « pret_a_porter ») ;
//   - boutique.secteur_info     : { libelle, icone, catalogue_telecom } ;
//   - boutique.vocabulaire      : { article, articles, nouvel_article, categorie,
//                                   categories, catalogue, stock, caracteristiques } ;
//   - boutique.champs_secteur   : champs propres au secteur (fiche article).
// Ce fichier lit ces informations, avec des valeurs de REPLI égales aux termes
// actuels de l'interface (boutique télécom ou ancienne réponse du serveur).
// Usage : const v = useVocabulaire();  <h1>{v.catalogue}</h1>  {v.minuscule("article")}
// ============================================================================
import { useMemo } from "react";
import { useAuth } from "@/context/AuthContext";

// Termes actuels de l'interface (identiques à VOCABULAIRE_DEFAUT de backend/secteurs.py)
export const VOCABULAIRE_DEFAUT = {
  article: "Produit",
  articles: "Produits",
  nouvel_article: "Nouveau produit",
  categorie: "Catégorie",
  categories: "Catégories",
  catalogue: "Catalogue",
  stock: "Stock",
  caracteristiques: "Caractéristiques",
};

// Pictogramme du menu « Catalogue » quand le secteur n'en précise pas (télécom)
export const ICONE_DEFAUT = "📱";

/**
 * Vocabulaire d'une boutique (fonction simple, utilisable hors composant React).
 * Renvoie les termes + quelques aides :
 *   - icone, telecom (vrai si fiche technique / catalogue de téléphones), champs ;
 *   - minuscule(cle) : le terme en minuscules (« article », « rayon ») pour une phrase.
 */
export function vocabulaireDe(boutique) {
  const termes = { ...VOCABULAIRE_DEFAUT };
  // Seuls les termes non vides envoyés par le serveur remplacent les termes actuels
  Object.entries(boutique?.vocabulaire || {}).forEach(([cle, valeur]) => {
    if (typeof valeur === "string" && valeur.trim()) termes[cle] = valeur.trim();
  });
  const info = boutique?.secteur_info || {};
  return {
    ...termes,
    secteur: boutique?.secteur || "telecom",
    libelleSecteur: info.libelle || "Télécom",
    icone: info.icone || ICONE_DEFAUT,
    // Pas d'information du serveur (ancienne réponse) : on reste en mode télécom
    telecom: info.catalogue_telecom !== undefined ? !!info.catalogue_telecom : true,
    champs: Array.isArray(boutique?.champs_secteur) ? boutique.champs_secteur : [],
    minuscule: (cle) => (termes[cle] || cle).toLocaleLowerCase("fr-FR"),
  };
}

/** Hook React : vocabulaire de la boutique connectée (ou consultée par le super-admin). */
export function useVocabulaire() {
  const { boutique } = useAuth();
  return useMemo(() => vocabulaireDe(boutique), [boutique]);
}

/**
 * Valeur d'un attribut (champ du secteur) prête à afficher :
 * liste -> « S, M », date AAAA-MM-JJ -> JJ/MM/AAAA, nombre -> écriture française.
 */
export function valeurAttribut(champ, valeur) {
  if (valeur === undefined || valeur === null || valeur === "") return "";
  if (Array.isArray(valeur)) return valeur.join(", ");
  if (champ?.type === "date" && /^\d{4}-\d{2}-\d{2}$/.test(String(valeur))) {
    const [a, m, j] = String(valeur).split("-");
    return `${j}/${m}/${a}`;
  }
  if (typeof valeur === "number") return valeur.toLocaleString("fr-FR");
  return String(valeur);
}

/** Lignes « Libellé : valeur » des attributs d'un article, dans l'ordre des champs du secteur. */
export function lignesAttributs(champs, attributs) {
  return (champs || [])
    .map((c) => ({ cle: c.cle, libelle: c.libelle, valeur: valeurAttribut(c, attributs?.[c.cle]) }))
    .filter((l) => l.valeur);
}
