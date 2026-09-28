import { useState } from "react";

// Champs d'un client (mêmes champs que ClientSaisie côté serveur, backend/routes/tiers.py).
export const CLIENT_VIDE = { type_client: "PART", nom: "", telephone: "", email: "", adresse: "", ifu: "", notes: "", accepte_whatsapp: false };

/** Prépare les données à envoyer : l'e-mail vide doit partir à null (sinon refusé). */
export function payloadClient(f) {
  return {
    type_client: f.type_client || "PART", nom: (f.nom || "").trim(), telephone: (f.telephone || "").trim(),
    email: (f.email || "").trim() || null, adresse: f.adresse || "", ifu: f.ifu || "", notes: f.notes || "",
    accepte_whatsapp: Boolean(f.accepte_whatsapp), // accord pour recevoir les offres par WhatsApp
  };
}

// Formulaire de saisie d'un client (création ou modification).
// initial = valeurs de départ ; onEnregistrer(donnees) renvoie une promesse.
export default function ClientFormulaire({ initial, onEnregistrer, libelleBouton = "Enregistrer" }) {
  // Copie locale des champs, modifiée à chaque frappe
  const [f, setF] = useState({ ...CLIENT_VIDE, ...initial });
  const [enCours, setEnCours] = useState(false);
  const champ = (nom) => ({ value: f[nom] ?? "", onChange: (e) => setF({ ...f, [nom]: e.target.value }) });

  // Envoi : on laisse la page appelante faire l'appel API
  async function soumettre(e) {
    e.preventDefault();
    setEnCours(true);
    try {
      await onEnregistrer(payloadClient(f));
    } finally {
      setEnCours(false);
    }
  }

  return (
    <form onSubmit={soumettre} className="space-y-3">
      {/* Particulier ou entreprise */}
      <div className="flex gap-2">
        {[["PART", "Particulier"], ["ENTR", "Entreprise"]].map(([v, l]) => (
          <button key={v} type="button" onClick={() => setF({ ...f, type_client: v })}
            className={`flex-1 rounded-xl border px-3 py-2 text-sm font-semibold ${f.type_client === v ? "border-primary bg-primary/10 text-primary" : "border-gray-300 text-gray-600"}`}>
            {l}
          </button>
        ))}
      </div>
      <div><label className="label">{f.type_client === "ENTR" ? "Raison sociale" : "Nom et prénom"} *</label><input className="input" required maxLength={150} {...champ("nom")} /></div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div><label className="label">Téléphone *</label><input className="input" required minLength={6} maxLength={30} inputMode="tel" {...champ("telephone")} /></div>
        <div><label className="label">E-mail</label><input className="input" type="email" {...champ("email")} /></div>
      </div>
      <div><label className="label">Adresse</label><input className="input" maxLength={500} {...champ("adresse")} /></div>
      {f.type_client === "ENTR" && <div><label className="label">IFU</label><input className="input" maxLength={50} {...champ("ifu")} /></div>}
      {/* Accord du client pour recevoir les offres de la boutique par WhatsApp (carrousels).
          À cocher UNIQUEMENT si le client l'a demandé ou accepté explicitement. */}
      <label className="flex items-start gap-2 rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm">
        <input type="checkbox" className="mt-0.5" checked={Boolean(f.accepte_whatsapp)}
          onChange={(e) => setF({ ...f, accepte_whatsapp: e.target.checked })} />
        <span>
          <b>Le client accepte de recevoir nos offres par WhatsApp</b>
          <span className="block text-xs text-gray-500">Nouveautés et promotions en carrousel photo. Il peut changer d'avis à tout moment : décochez alors la case.</span>
        </span>
      </label>
      <div><label className="label">Notes internes</label><textarea className="input" rows={3} maxLength={2000} {...champ("notes")} /></div>
      <button className="btn-primary w-full" disabled={enCours}>{enCours ? "Enregistrement…" : libelleBouton}</button>
    </form>
  );
}
