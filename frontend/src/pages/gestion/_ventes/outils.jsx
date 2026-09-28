import { STATUTS_PAIEMENT } from "@/lib/statuts";

// Petits éléments partagés par les pages « ventes et relation client ».

/**
 * Numéro WhatsApp : uniquement les chiffres (format international sans « + »).
 * Un numéro local à 8 chiffres (Burkina Faso) reçoit l'indicatif 226.
 */
export function numeroWhatsApp(telephone) {
  const brut = String(telephone || "");
  const chiffres = brut.replace(/\D/g, "");
  if (!brut.trim().startsWith("+") && chiffres.length === 8) return `226${chiffres}`;
  return chiffres;
}

/** Boutons « Appeler » et « WhatsApp » pour contacter quelqu'un. */
export function BoutonsContact({ telephone, email, taille = "btn-sm" }) {
  if (!telephone && !email) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {telephone && <a href={`tel:${telephone}`} className={`btn-outline ${taille}`}>📞 Appeler</a>}
      {telephone && (
        <a href={`https://wa.me/${numeroWhatsApp(telephone)}`} target="_blank" rel="noreferrer"
          className={`btn ${taille} bg-green-600 text-white hover:bg-green-700`}>💬 WhatsApp</a>
      )}
      {email && <a href={`mailto:${email}`} className={`btn-outline ${taille}`}>✉️ E-mail</a>}
    </div>
  );
}

/** Pastille du statut de paiement d'une facture (« Payée », « Non payée »…). */
export function BadgePaiement({ libelle }) {
  if (!libelle || libelle === "—") return <span className="text-gray-400">—</span>;
  return <span className={`badge ${STATUTS_PAIEMENT[libelle] || "bg-gray-100 text-gray-700"}`}>{libelle}</span>;
}

/** Libellé du type de document. */
export function libelleType(type) {
  return type === "PRO" ? "Proforma" : "Facture";
}

/** Numéro affiché d'un document : une facture non validée n'a pas encore de numéro. */
export function numeroDocument(doc) {
  return doc?.numero || "Brouillon";
}

/** Message affiché quand une liste est vide. */
export function ListeVide({ children }) {
  return <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-8 text-center text-gray-500">{children}</div>;
}
