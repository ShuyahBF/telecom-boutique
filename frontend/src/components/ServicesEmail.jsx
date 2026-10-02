// ---------------------------------------------------------------------------
// Services d'envoi des e-mails proposés (plateforme et boutiques) :
// Resend, ZeptoMail (Zoho), Brevo (API HTTPS, port 443) ou SMTP.
// Partagé par l'écran Paramètres de la plateforme et la messagerie des boutiques.
// ---------------------------------------------------------------------------

// Libellés de la liste « Service d'envoi »
export const SERVICES_EMAIL = [
  { code: "resend", libelle: "Resend" },
  { code: "zeptomail", libelle: "ZeptoMail (Zoho)" },
  { code: "brevo", libelle: "Brevo" },
  { code: "smtp", libelle: "SMTP" },
];

// Régions ZeptoMail (hôte de l'API)
export const HOTES_ZEPTOMAIL = [
  { code: "api.zeptomail.com", libelle: "International (.com)" },
  { code: "api.zeptomail.eu", libelle: "Europe (.eu)" },
  { code: "api.zeptomail.in", libelle: "Inde (.in)" },
];

// Ligne d'aide de chaque fournisseur, avec son lien d'inscription
const AIDES = {
  resend: { lien: "https://resend.com", site: "resend.com", texte: "gratuit jusqu'à 3 000 e-mails/mois (100/jour)." },
  zeptomail: { lien: "https://www.zoho.com/zeptomail/", site: "zoho.com/zeptomail",
    texte: "10 000 premiers e-mails offerts, puis 2,50 $ les 10 000 ; boîtes mail possibles avec Zoho Mail." },
  brevo: { lien: "https://www.brevo.com", site: "brevo.com", texte: "gratuit jusqu'à 300 e-mails/jour." },
};

// Nom lisible d'un code de service (« plateforme », « desactive » compris)
export function nomService(code) {
  if (code === "plateforme") return "Service de la plateforme";
  if (code === "desactive") return "Désactivé";
  return SERVICES_EMAIL.find((s) => s.code === code)?.libelle || "Non réglé";
}

// Aide du fournisseur choisi (rien pour SMTP, qui a son avertissement)
export function AideService({ code }) {
  const aide = AIDES[code];
  if (!aide) return null;
  return (
    <p className="text-xs text-gray-600">
      ℹ️ <a href={aide.lien} target="_blank" rel="noreferrer" className="font-semibold text-primary underline">{aide.site}</a>
      {" "}— {aide.texte} L'adresse d'expéditeur doit être sur un domaine validé chez ce fournisseur.
    </p>
  );
}

// Avertissement affiché sous le choix SMTP
export function AvertissementSmtp() {
  return (
    <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
      ⚠️ Bloqué sur les services Render gratuits (ports 25, 465, 587). Fonctionne seulement avec une offre payante (Starter).
    </p>
  );
}
