// Outils de la page « Historique des paiements » (privés à ce dossier).

// Canaux d'encaissement enregistrés par le serveur (backend/journal_paiements.py)
export const CANAUX = {
  PAWAPAY: "PawaPay en ligne",
  CAISSE: "Caisse",
};

// Couleurs des badges de statut (les libellés viennent du serveur : Réussi, Échoué…)
export const COULEURS_STATUTS = {
  SUCCES: "bg-green-100 text-green-800",
  ECHEC: "bg-red-100 text-red-700",
  EN_ATTENTE: "bg-amber-100 text-amber-800",
  ANNULE: "bg-gray-200 text-gray-700",
};

// Libellés par défaut (utilisés tant que la réponse du serveur n'est pas arrivée)
export const STATUTS_DEFAUT = { SUCCES: "Réussi", ECHEC: "Échoué", EN_ATTENTE: "En attente", ANNULE: "Annulé" };

// Raccourcis de période proposés au-dessus de la liste
export const PERIODES = [
  { code: "jour", libelle: "Aujourd'hui" },
  { code: "7j", libelle: "7 derniers jours" },
  { code: "mois", libelle: "Ce mois-ci" },
  { code: "mois_prec", libelle: "Mois dernier" },
  { code: "annee", libelle: "Cette année" },
  { code: "perso", libelle: "Personnalisée" },
];

// Date au format AAAA-MM-JJ, en heure LOCALE (toISOString donnerait l'heure de Londres)
export function isoLocal(d) {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const jj = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${jj}`;
}

/**
 * Transforme un raccourci de période en dates { du, au } (format AAAA-MM-JJ).
 * Pour « perso », on garde les dates déjà choisies (ou le mois en cours par défaut).
 */
export function bornesPeriode(code, duPerso = "", auPerso = "") {
  const auj = new Date();
  const a = auj.getFullYear();
  const m = auj.getMonth();
  switch (code) {
    case "jour":
      return { du: isoLocal(auj), au: isoLocal(auj) };
    case "7j":
      return { du: isoLocal(new Date(a, m, auj.getDate() - 6)), au: isoLocal(auj) };
    case "mois_prec":
      // Jour 0 du mois en cours = dernier jour du mois précédent
      return { du: isoLocal(new Date(a, m - 1, 1)), au: isoLocal(new Date(a, m, 0)) };
    case "annee":
      return { du: `${a}-01-01`, au: isoLocal(auj) };
    case "perso":
      return { du: duPerso || isoLocal(new Date(a, m, 1)), au: auPerso || isoLocal(auj) };
    default: // « mois » : du 1er du mois à aujourd'hui
      return { du: isoLocal(new Date(a, m, 1)), au: isoLocal(auj) };
  }
}
