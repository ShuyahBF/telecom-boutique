import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Case, Champ, ChoixImage } from "./communs";

// Champs de la fiche modifiables par le gérant (PATCH /boutique)
const CHAMPS = ["slogan", "adresse", "ville", "telephone", "email", "ifu", "rccm", "devise", "taux_tva_defaut",
  "prix_ttc", "validite_proforma_jours", "conditions_facture", "couleur", "paiement_mobile_money"];

// Onglet « Ma boutique » : fiche d'identité, réglages de facturation et logo.
export default function ParamBoutique() {
  const { boutique, setBoutique } = useAuth();
  const toast = useToast();

  // Copie modifiable de la fiche (initialisée avec les valeurs actuelles)
  const [fiche, setFiche] = useState(() => Object.fromEntries(CHAMPS.map((c) => [c, boutique[c] ?? ""])));
  const [envoi, setEnvoi] = useState(false);
  const maj = (champ, valeur) => setFiche((f) => ({ ...f, [champ]: valeur }));

  // Enregistrement de la fiche, puis mise à jour de la boutique en mémoire (menu, couleurs…)
  async function enregistrer(e) {
    e.preventDefault();
    setEnvoi(true);
    try {
      const { data } = await apiClient.patch("/boutique", {
        ...fiche,
        email: fiche.email || null, // e-mail vide : on n'envoie rien (l'API refuse un texte vide)
        taux_tva_defaut: Number(fiche.taux_tva_defaut) || 0,
        validite_proforma_jours: Number(fiche.validite_proforma_jours) || 15,
      });
      setBoutique(data);
      toast.succes("Fiche de la boutique enregistrée");
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez les champs (e-mail, couleur, taux de TVA…)"));
    } finally {
      setEnvoi(false);
    }
  }

  // Envoi du logo (multipart/form-data, champ « fichier »)
  async function envoyerLogo(fichier) {
    const f = new FormData();
    f.append("fichier", fichier);
    try {
      const { data } = await apiClient.post("/boutique/logo", f);
      setBoutique({ ...boutique, logo_url: data.logo_url });
      toast.succes("Logo enregistré");
    } catch (err) {
      toast.erreur(messageErreur(err, "Image refusée (JPEG, PNG ou WebP, 5 Mo maximum)"));
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <form onSubmit={enregistrer} className="space-y-5 lg:col-span-2">
        {/* Identité : nom et code marchand en lecture seule */}
        <div className="card grid gap-4 sm:grid-cols-2">
          <h2 className="font-bold sm:col-span-2">Identité</h2>
          <Champ label="Nom de la boutique" aide="Modifiable par l'administrateur de la plateforme."><input className="input bg-gray-50" value={boutique.nom} disabled /></Champ>
          <Champ label="Code marchand" aide="Modifiable par l'administrateur de la plateforme."><input className="input bg-gray-50 font-mono" value={boutique.code_marchand} disabled /></Champ>
          <Champ label="Slogan" className="sm:col-span-2"><input className="input" maxLength={200} value={fiche.slogan} onChange={(e) => maj("slogan", e.target.value)} placeholder="ex. Le meilleur prix sur vos smartphones" /></Champ>
          <Champ label="Adresse" className="sm:col-span-2"><input className="input" maxLength={500} value={fiche.adresse} onChange={(e) => maj("adresse", e.target.value)} placeholder="ex. Avenue Kwame Nkrumah, en face de la pharmacie" /></Champ>
          <Champ label="Ville"><input className="input" maxLength={80} value={fiche.ville} onChange={(e) => maj("ville", e.target.value)} /></Champ>
          <Champ label="Téléphone"><input className="input" maxLength={30} value={fiche.telephone} onChange={(e) => maj("telephone", e.target.value)} /></Champ>
          <Champ label="E-mail de contact"><input className="input" type="email" value={fiche.email} onChange={(e) => maj("email", e.target.value)} /></Champ>
          <Champ label="Couleur de la boutique" aide="Utilisée sur votre vitrine en ligne.">
            <div className="flex items-center gap-3">
              <input type="color" className="h-11 w-16 cursor-pointer rounded-lg border border-gray-300 bg-white p-1" value={fiche.couleur || "#0b5ed7"} onChange={(e) => maj("couleur", e.target.value)} />
              <span className="font-mono text-sm text-gray-600">{fiche.couleur}</span>
            </div>
          </Champ>
        </div>

        {/* Mentions légales et facturation */}
        <div className="card grid gap-4 sm:grid-cols-2">
          <h2 className="font-bold sm:col-span-2">Facturation</h2>
          <Champ label="IFU"><input className="input" maxLength={50} value={fiche.ifu} onChange={(e) => maj("ifu", e.target.value)} /></Champ>
          <Champ label="RCCM"><input className="input" maxLength={50} value={fiche.rccm} onChange={(e) => maj("rccm", e.target.value)} /></Champ>
          <Champ label="Devise"><input className="input" maxLength={10} value={fiche.devise} onChange={(e) => maj("devise", e.target.value)} /></Champ>
          <Champ label="Taux de TVA par défaut (%)"><input className="input" type="number" min={0} max={100} step="0.01" value={fiche.taux_tva_defaut} onChange={(e) => maj("taux_tva_defaut", e.target.value)} /></Champ>
          <Champ label="Validité des proformas (jours)"><input className="input" type="number" min={1} max={365} value={fiche.validite_proforma_jours} onChange={(e) => maj("validite_proforma_jours", e.target.value)} /></Champ>
          <div className="sm:col-span-2"><Case label="Prix du catalogue exprimés TTC" aide="Coché : les prix de vente saisis incluent la TVA. Décoché : ils sont hors taxes." checked={fiche.prix_ttc} onChange={(v) => maj("prix_ttc", v)} /></div>
          <div className="sm:col-span-2"><Case label="Paiement Mobile Money activé" aide="Les clients peuvent payer leurs commandes en ligne par Orange Money, Moov Money…" checked={fiche.paiement_mobile_money} onChange={(v) => maj("paiement_mobile_money", v)} /></div>
          <Champ label="Mentions en pied de facture" className="sm:col-span-2"><textarea className="input" rows={3} maxLength={1000} value={fiche.conditions_facture} onChange={(e) => maj("conditions_facture", e.target.value)} /></Champ>
        </div>

        <button className="btn-primary w-full sm:w-auto" disabled={envoi}>{envoi ? "Enregistrement…" : "💾 Enregistrer la fiche"}</button>
      </form>

      {/* Logo */}
      <div className="card h-fit">
        <h2 className="mb-3 font-bold">Logo</h2>
        <ChoixImage image={boutique.logo_url} onEnvoyer={envoyerLogo} />
        <p className="mt-3 text-center text-xs text-gray-500">Affiché sur vos factures, votre vitrine et l'affiche QR code. Un format carré sur fond clair rend mieux.</p>
      </div>
    </div>
  );
}
