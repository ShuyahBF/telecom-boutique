// Calculs des lignes de facture / proforma côté navigateur.
// C'est la MÊME formule que backend/services.py (calculer_lignes) : elle sert
// uniquement à afficher un aperçu des totaux pendant la saisie. À
// l'enregistrement, le serveur recalcule tout et c'est lui qui fait foi.

/** Arrondi à l'unité, au plus proche (le FCFA n'a pas de centimes). */
export function arrondi(valeur) {
  const n = Number(valeur) || 0;
  // Math.round arrondit 0,5 vers le haut pour les nombres positifs (comme ROUND_HALF_UP)
  return n >= 0 ? Math.round(n) : -Math.round(-n);
}

/** Convertit une saisie (« 12 », « 12,5 », « ») en nombre ; vide -> valeurParDefaut. */
export function nombre(saisie, valeurParDefaut = 0) {
  if (saisie === "" || saisie === null || saisie === undefined) return valeurParDefaut;
  const n = Number(String(saisie).replace(",", ".").replace(/\s/g, ""));
  return Number.isFinite(n) ? n : valeurParDefaut;
}

/**
 * Calcule chaque ligne (HT après remise, TVA, TTC) et les totaux.
 * - prixTtc = true : les prix saisis sont TTC, la TVA en est extraite ;
 * - prixTtc = false : les prix saisis sont HT, la TVA s'ajoute.
 * Un taux de TVA vide sur une ligne = taux par défaut de la boutique.
 */
export function calculerLignes(lignes, tauxTvaDefaut, prixTtc) {
  let totalHt = 0;
  let totalTva = 0;
  const resultat = lignes.map((l) => {
    const quantite = Math.trunc(nombre(l.quantite, 0));
    const pu = arrondi(nombre(l.prix_unitaire, 0));
    const remise = nombre(l.remise_pct, 0);
    const tva = nombre(l.taux_tva, tauxTvaDefaut);
    // Montant brut après remise
    const brut = pu * quantite * (1 - remise / 100);
    let ht;
    let montantTva;
    if (prixTtc) {
      const ttc = arrondi(brut);
      ht = arrondi((ttc * 100) / (100 + tva));
      montantTva = ttc - ht;
    } else {
      ht = arrondi(brut);
      montantTva = arrondi((ht * tva) / 100);
    }
    totalHt += ht;
    totalTva += montantTva;
    return { ...l, montant_ht: ht, montant_tva: montantTva, montant_ttc: ht + montantTva, taux_effectif: tva };
  });
  return { lignes: resultat, total_ht: totalHt, total_tva: totalTva, total_ttc: totalHt + totalTva };
}
