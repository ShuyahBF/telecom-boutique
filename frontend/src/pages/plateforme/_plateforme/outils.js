// Outils partagés par les écrans de la plateforme (super-administrateur) :
// listes de valeurs (pays, statuts KYC…) et petites fonctions utilitaires.
import { apiClient, messageErreur } from "@/lib/api";

// ---------------------------------------------------------------------------
// Pays proposés dans les formulaires : Afrique de l'Ouest puis Afrique
// centrale. « Autre » permet de saisir librement un autre pays.
// ---------------------------------------------------------------------------
export const PAYS_AFRIQUE_OUEST = [
  "Burkina Faso", "Bénin", "Cap-Vert", "Côte d'Ivoire", "Gambie", "Ghana", "Guinée", "Guinée-Bissau",
  "Libéria", "Mali", "Mauritanie", "Niger", "Nigeria", "Sénégal", "Sierra Leone", "Togo",
];
export const PAYS_AFRIQUE_CENTRALE = [
  "Cameroun", "Centrafrique", "Congo", "RD Congo", "Gabon", "Guinée équatoriale", "Sao Tomé-et-Principe", "Tchad",
];
export const PAYS_LISTE = [...PAYS_AFRIQUE_OUEST, ...PAYS_AFRIQUE_CENTRALE];
export const PAYS_DEFAUT = "Burkina Faso";

// ---------------------------------------------------------------------------
// Dossier KYC (identification de la boutique) : statuts et types de pièces.
// Mêmes codes que le serveur (backend/kyc.py).
// ---------------------------------------------------------------------------
export const STATUTS_KYC = {
  NON_FOURNI: { libelle: "Non fourni", classe: "bg-gray-100 text-gray-700" },
  EN_ATTENTE: { libelle: "En attente", classe: "bg-amber-100 text-amber-800" },
  VERIFIE: { libelle: "Vérifié", classe: "bg-green-100 text-green-800" },
  REJETE: { libelle: "Rejeté", classe: "bg-red-100 text-red-700" },
};

// ---------------------------------------------------------------------------
// Abonnements : statuts (mêmes codes que backend/abonnements.py) et modes de paiement
// ---------------------------------------------------------------------------
export { MODES_ABONNEMENT, STATUTS_ABONNEMENT } from "@/lib/statuts";

export const TYPES_PIECES_KYC = {
  PIECE_IDENTITE_DG: "Pièce d'identité du DG",
  RCCM: "Registre du commerce (RCCM)",
  IFU: "Attestation IFU",
  CNSS: "Attestation CNSS",
  AUTRE: "Autre justificatif",
};

// Formats acceptés pour les justificatifs (le serveur accepte aussi WebP)
export const FORMATS_JUSTIFICATIFS = "application/pdf,image/jpeg,image/png";

// ---------------------------------------------------------------------------
// Sauvegardes : libellés des déclencheurs et des collections restaurées
// ---------------------------------------------------------------------------
export const DECLENCHEURS = {
  planification: { libelle: "Automatique (00h)", classe: "bg-blue-50 text-blue-800" },
  manuel: { libelle: "Manuel", classe: "bg-indigo-50 text-indigo-800" },
  avant_restauration: { libelle: "Avant restauration", classe: "bg-purple-50 text-purple-800" },
};

export const COLLECTIONS_SAUVEGARDE = {
  categories: "Rayons (catégories)",
  produits: "Produits",
  clients: "Clients",
  fournisseurs: "Fournisseurs",
  mouvements: "Mouvements de stock",
  bons_entree: "Bons d'entrée",
  documents: "Factures et proformas",
  commandes: "Commandes en ligne",
  dossiers: "Dossiers SAV",
  conversations: "Conversations",
  modeles_messages: "Modèles de messages",
  journal_envois: "Journal des envois",
  journal_paiements: "Journal des paiements",
};

// ---------------------------------------------------------------------------
// Petites fonctions utilitaires
// ---------------------------------------------------------------------------

/** Texte saisi -> nombre (ou null si vide / invalide). Accepte la virgule. */
export function versNombre(texte) {
  if (texte === null || texte === undefined || String(texte).trim() === "") return null;
  const n = Number(String(texte).replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

/** Lien OpenStreetMap centré sur un point, ou null si coordonnées incomplètes */
export function lienCarte(latitude, longitude) {
  const lat = versNombre(latitude);
  const lon = versNombre(longitude);
  if (lat === null || lon === null || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17/${lat}/${lon}`;
}

/** 2 345 678 octets -> « 2,2 Mo » */
export function tailleLisible(octets) {
  const n = Number(octets || 0);
  if (n < 1024) return `${n} o`;
  if (n < 1024 * 1024) return `${(n / 1024).toLocaleString("fr-FR", { maximumFractionDigits: 0 })} Ko`;
  return `${(n / 1024 / 1024).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mo`;
}

/**
 * Message d'erreur quand la réponse attendue était un fichier (blob) :
 * le serveur renvoie alors son message JSON… emballé dans un Blob.
 * On le relit pour afficher la vraie phrase en français.
 */
export async function messageErreurFichier(err, repli) {
  const donnees = err?.response?.data;
  if (donnees instanceof Blob) {
    try {
      const detail = JSON.parse(await donnees.text())?.detail;
      return messageErreur({ response: { data: { detail } } }, repli);
    } catch {
      return repli;
    }
  }
  return messageErreur(err, repli);
}

/** Nom du fichier indiqué par le serveur (en-tête Content-Disposition), sinon null */
function nomDepuisEntete(entete) {
  const trouve = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(entete || "");
  return trouve ? decodeURIComponent(trouve[1]) : null;
}

/**
 * Télécharge un fichier PROTÉGÉ (le jeton de connexion est ajouté par
 * apiClient) et le fait enregistrer par le navigateur.
 * Renvoie le nom du fichier enregistré.
 */
export async function telechargerFichier(url, nomRepli) {
  const reponse = await apiClient.get(url, { responseType: "blob", timeout: 300000 });
  const nom = nomDepuisEntete(reponse.headers?.["content-disposition"]) || nomRepli;
  const lien = document.createElement("a");
  lien.href = URL.createObjectURL(reponse.data);
  lien.download = nom;
  document.body.appendChild(lien);
  lien.click();
  lien.remove();
  setTimeout(() => URL.revokeObjectURL(lien.href), 60000);
  return nom;
}

/**
 * Ouvre un fichier PROTÉGÉ (pièce justificative) dans un nouvel onglet.
 * L'onglet est ouvert AVANT le téléchargement (sinon le navigateur le
 * bloquerait comme « fenêtre publicitaire »), puis on y affiche le fichier.
 */
export async function ouvrirFichier(url) {
  const onglet = window.open("", "_blank");
  try {
    const reponse = await apiClient.get(url, { responseType: "blob" });
    const adresse = URL.createObjectURL(reponse.data);
    if (onglet) onglet.location.href = adresse;
    else window.location.assign(adresse); // onglet bloqué : on l'ouvre ici
    setTimeout(() => URL.revokeObjectURL(adresse), 5 * 60000);
  } catch (err) {
    onglet?.close();
    throw err;
  }
}

/** Horodatage pour un nom de fichier : 2026-09-28_1405 */
export function horodatage() {
  const d = new Date();
  const deux = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${deux(d.getMonth() + 1)}-${deux(d.getDate())}_${deux(d.getHours())}${deux(d.getMinutes())}`;
}
