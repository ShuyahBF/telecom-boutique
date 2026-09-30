// Maintenance des équipements : constantes et adresses partagées par les écrans
// (liste des fiches, actions, fiche imprimable) des deux espaces :
//   - « boutique »   : /api/maintenance-equipements (fonction activée par adLyn) ;
//   - « plateforme » : /api/plateforme/maintenance-equipements (super-admin, clients = boutiques).

// Statuts de suivi : [libellé, classes du badge]
export const STATUTS = {
  recu: ["Reçu", "bg-slate-100 text-slate-700"],
  diagnostic: ["En diagnostic", "bg-sky-100 text-sky-700"],
  reparation: ["En réparation", "bg-amber-100 text-amber-800"],
  pret: ["Prêt à rendre", "bg-emerald-100 text-emerald-700"],
  rendu: ["Rendu", "bg-indigo-100 text-indigo-700"],
};

// État du matériel à la réception : [libellé, couleur du texte]
export const ETATS = { mauvais: ["Mauvais", "text-rose-700"], moyen: ["Moyen", "text-amber-700"], bon: ["Bon", "text-emerald-700"] };

/** Adresse de l'API selon l'espace. */
export function baseApi(espace) {
  return espace === "plateforme" ? "/plateforme/maintenance-equipements" : "/maintenance-equipements";
}

/** Page imprimable (bon de dépôt / de restitution, ou facture adLyn) ouverte dans un nouvel onglet. */
export function lienImpression(espace, id, doc = "bon") {
  const racine = espace === "plateforme" ? "/plateforme" : "/gestion";
  return `${racine}/maintenance-equipements/${id}/imprimer?doc=${doc}`;
}

/** « Imprimante HP LaserJet » : type + marque / modèle. */
export function materiel(f) {
  return `${f.type_materiel}${f.marque_modele ? ` — ${f.marque_modele}` : ""}`;
}
