// Formatage des montants et des dates, à la française.

/** 125000 -> « 125 000 » (espace insécable fine entre les milliers) */
export function montant(valeur) {
  const n = Math.round(Number(valeur || 0));
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(n);
}

/** Montant suivi de la devise : « 125 000 FCFA » */
export function prix(valeur, devise = "FCFA") {
  return `${montant(valeur)} ${devise}`;
}

/** « 2026-09-28 » ou ISO complet -> « 28/09/2026 » */
export function date(valeur) {
  if (!valeur) return "—";
  const d = new Date(valeur.length === 10 ? `${valeur}T00:00:00` : valeur);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("fr-FR");
}

/** « 28/09/2026 14:05 » */
export function dateHeure(valeur) {
  if (!valeur) return "—";
  const d = new Date(valeur);
  return Number.isNaN(d.getTime()) ? "—" : `${d.toLocaleDateString("fr-FR")} ${d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`;
}

/** Date du jour au format AAAA-MM-JJ (champs <input type="date">) */
export function aujourdhui() {
  return new Date().toISOString().slice(0, 10);
}
