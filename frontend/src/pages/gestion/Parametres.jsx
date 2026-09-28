import { useSearchParams } from "react-router-dom";
import EnTetePage from "@/components/EnTetePage";
import { Onglets } from "./_atelier/communs";
import ParamBoutique from "./_atelier/ParamBoutique";
import ParamKyc from "./_atelier/ParamKyc";
import ParamQr from "./_atelier/ParamQr";
import ParamMessagerie from "./_atelier/ParamMessagerie";
import ParamModeles from "./_atelier/ParamModeles";
import ParamJournal from "./_atelier/ParamJournal";
import ParamEquipe from "./_atelier/ParamEquipe";
import ParamSecurite from "./_atelier/ParamSecurite";

// Liste des onglets de la page (le code apparaît dans l'adresse : ?onglet=equipe)
const ONGLETS = [
  { code: "boutique", libelle: "🏪 Ma boutique" },
  { code: "kyc", libelle: "🪪 Identité & KYC" },
  { code: "qr", libelle: "📲 QR code & partage" },
  { code: "messagerie", libelle: "✉️ Messagerie" },
  { code: "modeles", libelle: "📝 Modèles de messages" },
  { code: "journal", libelle: "📜 Journal des envois" },
  { code: "equipe", libelle: "👥 Équipe" },
  { code: "securite", libelle: "🛡️ Sécurité & connexions" },
];

// Page « Paramètres » (réservée au DG). Chaque onglet est un composant
// séparé, rangé dans le dossier _atelier pour garder ce fichier court.
export default function Parametres() {
  // L'onglet actif est gardé dans l'adresse : un rechargement reste sur le même onglet
  const [params, setParams] = useSearchParams();
  const onglet = ONGLETS.some((o) => o.code === params.get("onglet")) ? params.get("onglet") : "boutique";
  // Changer d'onglet = changer l'adresse (replace : pas d'entrée en plus dans l'historique)
  const allerA = (code) => setParams({ onglet: code }, { replace: true });

  return (
    <div>
      {/* L'en-tête n'est pas imprimé (seule l'affiche QR l'est, depuis son onglet) */}
      <div className="no-print">
        <EnTetePage titre="Paramètres" sousTitre="Réglages de votre boutique, dossier KYC, messagerie et équipe" />
      </div>
      <Onglets onglets={ONGLETS} actif={onglet} onChange={allerA} />

      {onglet === "boutique" && <ParamBoutique />}
      {onglet === "kyc" && <ParamKyc allerA={allerA} />}
      {onglet === "qr" && <ParamQr />}
      {onglet === "messagerie" && <ParamMessagerie />}
      {onglet === "modeles" && <ParamModeles />}
      {onglet === "journal" && <ParamJournal />}
      {onglet === "equipe" && <ParamEquipe />}
      {onglet === "securite" && <ParamSecurite />}
    </div>
  );
}
