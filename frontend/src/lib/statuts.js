// Libellés et couleurs des statuts (badges), partagés par toutes les pages.

export const STATUTS_DOCUMENT = {
  BROUILLON: { libelle: "Brouillon", classe: "bg-gray-100 text-gray-700" },
  EN_VALIDATION: { libelle: "Validation…", classe: "bg-yellow-100 text-yellow-800" },
  VALIDE: { libelle: "Validé", classe: "bg-green-100 text-green-800" },
  ANNULE: { libelle: "Annulé", classe: "bg-red-100 text-red-700" },
};

export const STATUTS_PAIEMENT = {
  "Payée": "bg-green-100 text-green-800",
  "Partiellement payée": "bg-amber-100 text-amber-800",
  "Non payée": "bg-red-100 text-red-700",
};

export const STATUTS_COMMANDE = {
  RECUE: { libelle: "Reçue", classe: "bg-blue-100 text-blue-800" },
  CONFIRMEE: { libelle: "Confirmée", classe: "bg-indigo-100 text-indigo-800" },
  PREPARATION: { libelle: "En préparation", classe: "bg-amber-100 text-amber-800" },
  PRETE: { libelle: "Prête", classe: "bg-teal-100 text-teal-800" },
  LIVREE: { libelle: "Livrée", classe: "bg-green-100 text-green-800" },
  ANNULEE: { libelle: "Annulée", classe: "bg-red-100 text-red-700" },
};

export const STATUTS_PAIEMENT_COMMANDE = {
  NON_PAYEE: { libelle: "Paiement à la livraison / au retrait", classe: "bg-gray-100 text-gray-700" },
  EN_ATTENTE: { libelle: "Paiement Mobile Money en attente", classe: "bg-amber-100 text-amber-800" },
  PAYEE: { libelle: "Payée (Mobile Money)", classe: "bg-green-100 text-green-800" },
  ECHEC: { libelle: "Paiement échoué", classe: "bg-red-100 text-red-700" },
};

export const STATUTS_SAV = {
  RECU: { libelle: "Appareil reçu", classe: "bg-blue-100 text-blue-800" },
  DIAGNOSTIC: { libelle: "Diagnostic en cours", classe: "bg-indigo-100 text-indigo-800" },
  DEVIS: { libelle: "Devis en attente d'accord", classe: "bg-amber-100 text-amber-800" },
  ATTENTE_PIECE: { libelle: "En attente de pièce", classe: "bg-orange-100 text-orange-800" },
  REPARATION: { libelle: "Réparation en cours", classe: "bg-purple-100 text-purple-800" },
  PRET: { libelle: "Prêt à être retiré", classe: "bg-green-100 text-green-800" },
  IRREPARABLE: { libelle: "Irréparable", classe: "bg-red-100 text-red-700" },
  RESTITUE: { libelle: "Restitué", classe: "bg-gray-100 text-gray-700" },
};

export const STATUTS_CONVERSATION = {
  ATTENTE: { libelle: "En attente de réponse", classe: "bg-amber-100 text-amber-800" },
  REPONDU: { libelle: "Répondu", classe: "bg-green-100 text-green-800" },
  CLOS: { libelle: "Clos", classe: "bg-gray-100 text-gray-700" },
};

export const TYPES_PRODUIT = { TEL: "Téléphone", ACC: "Accessoire", PIE: "Pièce détachée", SER: "Service" };

export const ROLES = { super_admin: "Administrateur plateforme", gerant: "Gérant", vendeur: "Vendeur", technicien: "Technicien" };

/** Badge de statut : <Badge statut={x} table={STATUTS_SAV} /> */
export function classeStatut(table, statut) {
  return table[statut]?.classe || "bg-gray-100 text-gray-700";
}
export function libelleStatut(table, statut) {
  return table[statut]?.libelle || statut || "—";
}
