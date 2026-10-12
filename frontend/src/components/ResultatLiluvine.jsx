import { dateHeure } from "@/lib/format";

// ============================================================================
// Lot C — résultat de la lecture de la pièce d'identité par Liluvine (IA)
// ============================================================================
// Affiché :
//   - au commerçant (onglet « Identité & KYC » des Paramètres) : décision + motif,
//     et ce que Liluvine a lu (numéro de pièce TOUJOURS masqué, ex. « B12•••789 ») ;
//   - au super-administrateur (dossier de la boutique), avec `detaille` : en plus,
//     la comparaison mot à mot, le score face au seuil et l'erreur technique éventuelle.
// `ia` = boutique.kyc.ia, renvoyé par le serveur (voir backend/kyc_ia.py).
// Lot D — avec `detaille` (super-admin) : avis de Liluvine sur le selfie (même personne ?
// confiance face au seuil visage, pièce tenue = recto ?, signes de fraude, remarques).
// Le commerçant ne reçoit jamais ces informations (le serveur les retire).
// ============================================================================

// Lot D — réponses « oui / non / incertain » de l'IA : couleur et libellé
const AVIS = {
  oui: { classe: "bg-green-100 text-green-800", libelle: "Oui" },
  non: { classe: "bg-red-100 text-red-800", libelle: "Non" },
  incertain: { classe: "bg-amber-100 text-amber-800", libelle: "Incertain" },
};
function Avis({ valeur }) {
  const a = AVIS[valeur] || AVIS.incertain;
  return <span className={`badge ${a.classe}`}>{a.libelle}</span>;
}

// Présentation de chaque décision : couleur et icône
const DECISIONS = {
  VERIFIE: { icone: "✅", classe: "border-green-300 bg-green-50 text-green-900", titre: "Pièce vérifiée par Liluvine" },
  EN_ATTENTE: { icone: "⏳", classe: "border-amber-300 bg-amber-50 text-amber-900", titre: "Vérification par l'équipe adLyn" },
};

// Champs lus sur la pièce, dans l'ordre d'affichage
const CHAMPS = [
  ["type_document", "Type de document"],
  ["nom", "Nom"],
  ["prenoms", "Prénoms"],
  ["date_naissance", "Date de naissance"],
  ["numero_piece_masque", "Numéro de la pièce"],
  ["date_expiration", "Date d'expiration"],
  ["pays", "Pays"],
];

// Petit indicateur Oui / Non coloré (ok = vert, sinon rouge)
function Indicateur({ ok, oui = "Oui", non = "Non" }) {
  return <span className={`badge ${ok ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`}>{ok ? oui : non}</span>;
}

export default function ResultatLiluvine({ ia, detaille = false }) {
  if (!ia) return null;
  const decision = DECISIONS[ia.decision] || DECISIONS.EN_ATTENTE;
  const lecture = ia.lecture;
  const comparaison = ia.comparaison;

  return (
    <div className={`rounded-2xl border-2 p-4 text-sm ${decision.classe}`}>
      {/* En-tête : décision, date, motif lisible */}
      <div className="flex flex-wrap items-start gap-3">
        <span className="text-2xl" aria-hidden>{decision.icone}</span>
        <div className="min-w-0 flex-1">
          <p className="font-bold">{decision.titre}</p>
          <p className="mt-0.5">{ia.motif}</p>
          <p className="mt-1 text-xs opacity-75">
            Lecture du {dateHeure(ia.date)} · par {ia.par || "IA (Liluvine)"}
            {ia.relance ? " · relancée par l'administrateur" : ""}
            {detaille && ia.modele ? ` · modèle ${ia.modele}` : ""}
          </p>
        </div>
      </div>

      {/* Ce que Liluvine a lu sur la pièce (tableau : survol et sélection selon les règles globales) */}
      {lecture && (
        <div className="mt-3 overflow-x-auto rounded-xl bg-white/80 text-gray-800">
          <table className="table">
            <thead><tr><th>Champ lu</th><th>Valeur</th></tr></thead>
            <tbody>
              {CHAMPS.map(([cle, libelle]) => (
                <tr key={cle}>
                  <td className="text-gray-500">{libelle}</td>
                  <td className={cle === "numero_piece_masque" ? "font-mono" : "font-semibold"}>{lecture[cle] || "—"}</td>
                </tr>
              ))}
              <tr><td className="text-gray-500">Lisible</td><td><Indicateur ok={lecture.lisible} /></td></tr>
              <tr><td className="text-gray-500">Pièce d'identité</td><td><Indicateur ok={lecture.ressemble_piece_identite} /></td></tr>
              <tr><td className="text-gray-500">En cours de validité</td><td><Indicateur ok={!lecture.expiree && ia.motif_code !== "EXPIREE"} /></td></tr>
              {detaille && (
                <tr>
                  <td className="text-gray-500">Score de confiance</td>
                  <td><b>{Math.round((lecture.confiance || 0) * 100)} %</b> <span className="text-gray-500">(seuil {Math.round((ia.seuil || 0) * 100)} %)</span></td>
                </tr>
              )}
              {detaille && lecture.remarques && (
                <tr><td className="text-gray-500">Remarques</td><td>{lecture.remarques}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Super-admin : concordance du nom (déclaré / lu, mot par mot) */}
      {detaille && comparaison && (
        <div className="mt-3 rounded-xl bg-white/80 p-3 text-gray-800">
          <p className="font-semibold">Concordance du nom</p>
          <p className="mt-1">Déclaré : <b>{comparaison.declare || "—"}</b> <span className="text-xs text-gray-500">({comparaison.source})</span></p>
          <p>Lu sur la pièce : <b>{comparaison.lu || "—"}</b></p>
          <p className="mt-1 flex flex-wrap gap-2">
            <span>Nom de famille <Indicateur ok={comparaison.nom_famille_ok} oui="concorde" non="ne concorde pas" /></span>
            <span>Prénom <Indicateur ok={comparaison.prenom_ok} oui="concorde" non="ne concorde pas" /></span>
          </p>
          {comparaison.correspondances?.length > 0 && (
            <p className="mt-1 text-xs text-gray-500">
              {comparaison.correspondances.map((c) => `${c.declare} ↔ ${c.lu} (${Math.round(c.similarite * 100)} %)`).join(" · ")}
            </p>
          )}
        </div>
      )}
      {/* Lot D — super-admin : avis de Liluvine sur le selfie (aide à la décision, jamais une preuve) */}
      {detaille && ia.selfie_fourni === false && (
        <p className="mt-3 rounded-xl bg-white/80 p-3 text-gray-800">🤳 Aucun selfie dans cet envoi{ia.exiger_selfie ? " (exigé par les réglages)" : ""}.</p>
      )}
      {detaille && ia.visage && (
        <div className="mt-3 overflow-x-auto rounded-xl bg-white/80 text-gray-800">
          <table className="table">
            <thead><tr><th>🤳 Selfie (avis de Liluvine)</th><th>Résultat</th></tr></thead>
            <tbody>
              <tr>
                <td className="text-gray-500">Même personne que sur la pièce</td>
                <td>
                  <Avis valeur={ia.visage.meme_personne} />{" "}
                  <b>{Math.round((ia.visage.confiance_visage || 0) * 100)} %</b>{" "}
                  <span className="text-gray-500">(seuil {Math.round((ia.seuil_visage || 0) * 100)} %)</span>
                </td>
              </tr>
              <tr><td className="text-gray-500">Pièce tenue à côté du visage</td><td><Indicateur ok={ia.visage.piece_tenue_visible} /></td></tr>
              <tr><td className="text-gray-500">Pièce tenue = recto envoyé</td><td><Avis valeur={ia.visage.piece_selfie_correspond} /></td></tr>
              <tr>
                <td className="text-gray-500">Signes de fraude</td>
                <td>{ia.visage.signes_fraude?.length
                  ? <span className="badge bg-red-100 text-red-800">⚠ {ia.visage.signes_fraude.join(", ")}</span>
                  : <span className="badge bg-green-100 text-green-800">Aucun</span>}</td>
              </tr>
              {ia.visage.remarques && <tr><td className="text-gray-500">Remarques</td><td>{ia.visage.remarques}</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {detaille && ia.erreur_ia && <p className="mt-2 text-xs">Détail technique : {ia.erreur_ia}</p>}
    </div>
  );
}
