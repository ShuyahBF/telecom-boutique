import { Link } from "react-router-dom";
import { peut } from "@/context/AuthContext";
import { optionActive } from "@/lib/options";

// ============================================================================
// Lot B — boutique EN ATTENTE DE VALIDATION (validee = false) : créée par
// l'inscription en ligne (ou par le webhook / le parrainage) et pas encore
// vérifiée par l'équipe adLyn. Le commerçant peut déjà préparer sa boutique
// (paramètres, dossier d'identité, catalogue…), mais sa vitrine n'est pas
// visible du public tant qu'elle n'est pas validée.
//   - <BandeauAttenteValidation> : bandeau en haut de toutes les pages du back-office ;
//   - <CarteAttenteValidation>   : carte détaillée en tête du tableau de bord.
// Le dossier d'identité (KYC) est l'onglet « Identité & KYC » des Paramètres.
// Lot C : Liluvine (IA) y lit la pièce d'identité ; si le nom concorde avec le
// propriétaire déclaré, la boutique est validée sur-le-champ. Sinon, la carte
// affiche le motif (photo floue, nom différent…) et invite à renvoyer une photo.
// ============================================================================
export const LIEN_KYC = "/gestion/parametres?onglet=kyc";

/** Vrai si la boutique attend la validation de l'équipe adLyn. */
export function enAttenteValidation(boutique) {
  return !!boutique && boutique.validee === false;
}

/** Vrai si cet utilisateur peut ouvrir le dossier d'identité (DG, option « Paramètres » active). */
function peutCompleterDossier(user, boutique) {
  return peut(user, "parametres") && optionActive(boutique, "parametres");
}

export function BandeauAttenteValidation({ user, boutique }) {
  if (!enAttenteValidation(boutique)) return null;
  return (
    <div className="no-print flex flex-wrap items-center justify-between gap-2 bg-amber-50 px-4 py-2 text-sm text-amber-900">
      <span>⏳ Votre boutique est en cours de validation par l'équipe adLyn : elle n'est pas encore visible du public.</span>
      {peutCompleterDossier(user, boutique) && (
        <Link to={LIEN_KYC} className="font-semibold underline">Compléter mon dossier (pièce d'identité) →</Link>
      )}
    </div>
  );
}

// Étapes affichées sur la carte, selon le statut du dossier KYC
function etapeDossier(kyc) {
  switch (kyc?.statut) {
    case "VERIFIE": return { fait: true, texte: "Dossier d'identité vérifié" };
    case "EN_ATTENTE":
      // Lot C : motif donné par Liluvine (ex. photo floue) -> le commerçant peut renvoyer une photo
      if (kyc.ia?.motif) return { fait: false, texte: `Pièce d'identité reçue, vérification par l'équipe adLyn : ${kyc.ia.motif}` };
      return { fait: true, texte: "Dossier d'identité envoyé : vérification en cours" };
    case "REJETE": return { fait: false, texte: `Dossier d'identité à reprendre${kyc.motif_rejet ? ` : ${kyc.motif_rejet}` : ""}` };
    default: return { fait: false, texte: "Envoyez la photo de votre pièce d'identité (CNIB ou passeport)" };
  }
}

export function CarteAttenteValidation({ user, boutique, bienvenue = false }) {
  if (!enAttenteValidation(boutique)) return null;
  const dossier = etapeDossier(boutique.kyc);
  const etapes = [
    { fait: true, texte: boutique.origine === "inscription" ? "Compte créé, numéro WhatsApp vérifié" : "Compte créé" },
    dossier,
    { fait: false, texte: "Validation : immédiate dès que Liluvine confirme votre pièce, sinon par l'équipe adLyn. Votre vitrine devient alors visible du public" },
  ];
  return (
    <section className="card mb-6 border-amber-200 bg-amber-50/60">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="surtitre text-amber-800">{bienvenue ? "Bienvenue sur adLyn 🎉" : "Boutique en attente de validation"}</p>
          <h2 className="mt-1 text-xl font-extrabold">Votre boutique est en cours de validation…</h2>
          <p className="mt-1 text-sm text-gray-700">
            L'équipe adLyn vérifie chaque nouvelle boutique avant de l'ouvrir au public. En attendant, vous pouvez déjà
            la préparer : paramètres, logo, articles…
          </p>
          <ol className="mt-4 space-y-2 text-sm">
            {etapes.map((e, i) => (
              <li key={e.texte} className="flex items-start gap-2">
                <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${e.fait ? "bg-green-600 text-white" : "bg-white text-amber-800 ring-1 ring-amber-300"}`}>
                  {e.fait ? "✓" : i + 1}
                </span>
                <span className={e.fait ? "text-gray-700" : "font-semibold text-ink"}>{e.texte}</span>
              </li>
            ))}
          </ol>
        </div>
        {/* ID boutique : utile pour la connexion par mot de passe et pour l'assistance */}
        <div className="rounded-xl border border-amber-200 bg-white px-4 py-3 text-center">
          <p className="text-xs text-gray-500">Votre ID boutique</p>
          <p className="font-mono text-xl font-bold tracking-[0.2em]">{boutique.code_marchand}</p>
        </div>
      </div>
      {peutCompleterDossier(user, boutique) && !dossier.fait && (
        <Link to={LIEN_KYC} className="btn-primary mt-4 inline-flex">
          {boutique.kyc?.ia ? "📷 Renvoyer une photo de ma pièce d'identité" : "🪪 Compléter mon dossier (pièce d'identité)"}
        </Link>
      )}
    </section>
  );
}
