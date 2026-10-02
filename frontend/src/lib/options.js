// Options de la barre latérale activées boutique par boutique par l'administrateur
// adLyn (voir backend/options_sidebar.py). Le serveur envoie leur état réel avec la
// boutique : boutique.options_actives = { clients: true, stock: false, ... }.
// « Tableau de bord » et « Caisse Aizenta » sont toujours actives.

/**
 * Vrai si l'option (ou l'une des options d'une liste) est active pour la boutique.
 * Une boutique sans « options_actives » (ancienne réponse du serveur) : tout est actif.
 * Exemples : optionActive(boutique, "clients"), optionActive(boutique, ["documents", "commandes"]).
 */
export function optionActive(boutique, option) {
  if (!option) return true;
  const actives = boutique?.options_actives;
  if (!actives) return true;
  const liste = Array.isArray(option) ? option : [option];
  return liste.some((cle) => actives[cle] !== false);
}
