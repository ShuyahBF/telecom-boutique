// Panier d'achat du portail, rangé dans le navigateur (localStorage), UN
// panier par boutique : { produit_id: { produit, quantite } }.

const cle = (slug) => `tlb_panier_${slug}`;

export function lirePanier(slug) {
  try {
    return JSON.parse(localStorage.getItem(cle(slug))) || {};
  } catch {
    return {};
  }
}

function ecrire(slug, panier) {
  localStorage.setItem(cle(slug), JSON.stringify(panier));
  // Prévient les autres composants (compteur du panier dans l'en-tête)
  window.dispatchEvent(new CustomEvent("panier-change", { detail: slug }));
}

export function ajouterAuPanier(slug, produit, quantite = 1) {
  const panier = lirePanier(slug);
  const actuel = panier[produit.id]?.quantite || 0;
  let nouvelle = actuel + quantite;
  // Jamais plus que le stock disponible (stock_max est null pour les services)
  if (produit.stock_max != null) nouvelle = Math.min(nouvelle, produit.stock_max);
  if (nouvelle > 0) panier[produit.id] = { produit, quantite: nouvelle };
  ecrire(slug, panier);
}

export function changerQuantite(slug, produitId, quantite) {
  const panier = lirePanier(slug);
  if (!panier[produitId]) return;
  const max = panier[produitId].produit.stock_max;
  const q = max != null ? Math.min(quantite, max) : quantite;
  if (q <= 0) delete panier[produitId];
  else panier[produitId].quantite = q;
  ecrire(slug, panier);
}

export function viderPanier(slug) {
  ecrire(slug, {});
}

export function nombreArticles(slug) {
  return Object.values(lirePanier(slug)).reduce((s, l) => s + l.quantite, 0);
}
