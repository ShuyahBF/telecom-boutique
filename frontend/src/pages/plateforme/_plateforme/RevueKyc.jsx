// ============================================================================
// Lot D — écran de REVUE HUMAINE de l'identité (super-administrateur), dans la
// fenêtre « Dossier de la boutique ».
// ============================================================================
// Affiche côte à côte le recto, le verso et le selfie (photo du DG tenant sa pièce)
// du DERNIER envoi, avec les motifs pour lesquels Liluvine n'a pas validé seule.
// Les images viennent d'une route protégée (super-admin) et sont transformées en
// adresses locales du navigateur (blob:) : aucune adresse publique, aucune clé de
// stockage. Trois décisions :
//   - « ✓ Valider l'identité »          -> KYC vérifié + boutique validée ;
//   - « ✖ Refuser »                      -> KYC rejeté, motif envoyé au commerçant ;
//   - « 📷 Demander une nouvelle photo » -> motif affiché au commerçant, qui renvoie ses photos.
// ============================================================================
import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import { useToast } from "@/components/Toast";
import Patientez from "@/components/Patientez";

// Ordre et libellés des images de la revue
const ORDRE_FACES = { RECTO: 1, VERSO: 2, SELFIE: 3 };
const TITRES = { RECTO: "Recto de la pièce", VERSO: "Verso de la pièce", SELFIE: "🤳 Selfie avec la pièce" };

/** Pièces du dernier envoi « Ma pièce d'identité » (recto, verso, selfie), dans l'ordre. */
export function piecesDuDernierEnvoi(kyc) {
  const documents = kyc?.documents || [];
  const pieces = documents.filter((d) => d.type === "PIECE_IDENTITE_DG");
  const derniere = pieces[pieces.length - 1];
  if (!derniere) return [];
  const groupe = derniere.envoi_id
    ? documents.filter((d) => d.envoi_id === derniere.envoi_id && ["PIECE_IDENTITE_DG", "SELFIE_DG"].includes(d.type))
    : [derniere];
  return [...groupe].sort((a, b) => (ORDRE_FACES[a.face] || 9) - (ORDRE_FACES[b.face] || 9));
}

// Une image protégée : chargée avec le jeton de connexion, affichée via une adresse blob: locale
function ImageProtegee({ url, titre, format }) {
  const [adresse, setAdresse] = useState(null);
  const [erreur, setErreur] = useState(false);
  useEffect(() => {
    let locale = null;
    let annule = false;
    apiClient.get(url, { responseType: "blob" })
      .then(({ data }) => {
        if (annule) return;
        locale = URL.createObjectURL(data);
        setAdresse(locale);
      })
      .catch(() => !annule && setErreur(true));
    // Nettoyage : l'adresse locale est libérée quand on ferme la fenêtre
    return () => { annule = true; if (locale) URL.revokeObjectURL(locale); };
  }, [url]);

  return (
    <figure className="flex flex-col rounded-xl border border-gray-200 bg-white p-2">
      <figcaption className="mb-1 text-xs font-semibold text-gray-600">{titre}</figcaption>
      {erreur ? <p className="py-10 text-center text-xs text-red-600">Image introuvable</p>
        : !adresse ? <p className="py-10 text-center text-xs text-gray-400">Chargement…</p>
          : format === "application/pdf"
            ? <a href={adresse} target="_blank" rel="noreferrer" className="py-10 text-center text-sm text-primary underline">📄 Ouvrir le PDF</a>
            : (
              // Clic : l'image en grand dans un nouvel onglet (adresse locale, jamais publique)
              <a href={adresse} target="_blank" rel="noreferrer" title="Agrandir">
                <img src={adresse} alt={titre} className="h-64 w-full rounded-lg bg-gray-50 object-contain" draggable={false} />
              </a>
            )}
    </figure>
  );
}

export default function RevueKyc({ boutique, onMaj }) {
  const toast = useToast();
  const [motif, setMotif] = useState(""); // motif du refus ou de la nouvelle photo
  const [occupe, setOccupe] = useState(""); // décision en cours
  const kyc = boutique.kyc || {};
  const base = `/plateforme/boutiques/${boutique.id}`;
  const pieces = piecesDuDernierEnvoi(kyc);
  if (!pieces.length) return null;
  const aVerifier = kyc.revue_humaine_requise && kyc.statut !== "VERIFIE";

  // Exécute une décision, met la boutique à jour dans la liste et affiche le résultat
  async function decider(action) {
    if (action !== "valider" && !motif.trim()) {
      return toast.erreur("Indiquez le motif : il sera affiché au commerçant et envoyé par WhatsApp.");
    }
    if (action === "valider" && !window.confirm(`Valider l'identité du DG de « ${boutique.nom} » et ouvrir la boutique au public ?`)) return;
    setOccupe(action);
    try {
      if (action === "valider") {
        const { data } = await apiClient.post(`${base}/kyc/valider-identite`);
        onMaj(data.boutique);
        toast.succes("Identité validée : la boutique est visible du public et le commerçant est prévenu");
      } else if (action === "refuser") {
        const { data } = await apiClient.post(`${base}/kyc/refuser`, { motif: motif.trim() });
        onMaj({ ...boutique, kyc: data });
        toast.succes("KYC refusé : le commerçant est prévenu");
      } else {
        const { data } = await apiClient.post(`${base}/kyc/nouvelle-photo`, { motif: motif.trim() });
        onMaj({ ...boutique, kyc: data });
        toast.succes("Nouvelle photo demandée : le commerçant est prévenu par WhatsApp");
      }
      setMotif("");
    } catch (err) {
      toast.erreur(messageErreur(err, "Décision impossible"));
    } finally {
      setOccupe("");
    }
  }

  return (
    <section className={`rounded-2xl border-2 p-3 ${aVerifier ? "border-orange-300 bg-orange-50/60" : "border-gray-200 bg-gray-50"}`}>
      {/* Attente d'une décision : toast « Patientez… » + jauge circulaire */}
      <Patientez actif={!!occupe} texte="Patientez… enregistrement de la décision…" />
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-bold">🔍 Revue de l'identité</h3>
        {aVerifier
          ? <span className="badge bg-orange-200 text-orange-900">À vérifier par un humain{kyc.revue?.depuis ? ` depuis le ${dateHeure(kyc.revue.depuis)}` : ""}</span>
          : <span className="badge bg-gray-200 text-gray-700">Dernier envoi du {dateHeure(pieces[0].date)}</span>}
      </div>

      {/* Pourquoi Liluvine n'a pas validé seule */}
      {aVerifier && kyc.revue?.libelles?.length > 0 && (
        <ul className="mb-3 list-disc space-y-0.5 pl-5 text-sm text-orange-900">
          {kyc.revue.libelles.map((l) => <li key={l}>{l}</li>)}
        </ul>
      )}
      {kyc.nouvelle_photo?.motif && (
        <p className="mb-3 rounded-xl bg-white p-2 text-sm">📷 Nouvelle photo demandée le {dateHeure(kyc.nouvelle_photo.date)} : <i>{kyc.nouvelle_photo.motif}</i></p>
      )}

      {/* Recto, verso et selfie côte à côte (images protégées) */}
      <div className="grid gap-3 sm:grid-cols-3">
        {pieces.map((p) => (
          <ImageProtegee key={p.id} url={`${base}/kyc/images/${p.id}`} titre={TITRES[p.face] || p.libelle} format={p.format} />
        ))}
        {!pieces.some((p) => p.type === "SELFIE_DG") && (
          <p className="flex items-center justify-center rounded-xl border border-dashed border-gray-300 p-4 text-center text-sm text-gray-500">
            🤳 Pas de selfie dans cet envoi
          </p>
        )}
      </div>

      {/* Décisions (le dossier vérifié n'a plus besoin de décision) */}
      {kyc.statut !== "VERIFIE" && (
        <div className="mt-3 space-y-2">
          <label className="block text-sm">
            <span className="text-xs text-gray-600">Motif (obligatoire pour refuser ou demander une nouvelle photo — envoyé au commerçant)</span>
            <textarea className="input bg-white" rows={2} maxLength={500} value={motif} onChange={(e) => setMotif(e.target.value)}
              placeholder="Ex. : visage trop sombre, reprenez la photo à la lumière du jour en tenant la pièce à côté du visage." />
          </label>
          <div className="grid gap-2 sm:grid-cols-3">
            <button type="button" className="btn bg-green-600 text-white hover:bg-green-700" disabled={!!occupe}
              onClick={() => decider("valider")}>✓ Valider l'identité</button>
            <button type="button" className="btn-danger" disabled={!!occupe} onClick={() => decider("refuser")}>✖ Refuser</button>
            <button type="button" className="btn-outline bg-white" disabled={!!occupe} onClick={() => decider("photo")}>📷 Demander une nouvelle photo</button>
          </div>
        </div>
      )}
    </section>
  );
}
