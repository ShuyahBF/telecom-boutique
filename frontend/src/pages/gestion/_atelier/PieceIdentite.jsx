import { useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { useToast } from "@/components/Toast";
import Patientez from "@/components/Patientez";
import ResultatLiluvine from "@/components/ResultatLiluvine";
import { Champ } from "./communs";

// ============================================================================
// Lot C — formulaire « Ma pièce d'identité » (onglet « Identité & KYC »)
// ============================================================================
// Le commerçant photographie le RECTO de sa pièce (appareil photo du téléphone ou
// fichier), le VERSO s'il le souhaite, choisit le type de pièce et envoie.
// Liluvine (IA) lit aussitôt la pièce : si le nom correspond au propriétaire
// déclaré, la boutique est validée sur-le-champ ; sinon un message d'attente
// explique pourquoi et le commerçant peut renvoyer une meilleure photo.
// Les grosses photos sont réduites dans le navigateur avant l'envoi (plus rapide
// sur un réseau mobile, et sous la limite de 5 Mo du serveur).
// ============================================================================

const TAILLE_MAX = 5 * 1024 * 1024; // 5 Mo par face (comme le serveur)
const FORMATS = ["image/jpeg", "image/png", "image/webp", "application/pdf"];
const COTE_MAX = 2000; // plus grand côté d'une photo après réduction (pixels)

// Types proposés si le serveur ne répond pas encore (mêmes codes que backend/kyc_ia.py)
const TYPES_PAR_DEFAUT = {
  CNIB: "CNIB (carte nationale d'identité burkinabè)",
  PASSEPORT: "Passeport",
  CARTE_CONSULAIRE: "Carte consulaire",
};

// Réduit une photo trop grande ou dans un format non accepté (ex. HEIC d'iPhone)
// en JPEG de qualité 0,85. Un PDF ou une petite photo sont envoyés tels quels.
async function preparerPhoto(fichier) {
  if (fichier.type === "application/pdf") return fichier;
  const petite = FORMATS.includes(fichier.type) && fichier.size <= 1.5 * 1024 * 1024;
  if (petite) return fichier;
  try {
    const image = await createImageBitmap(fichier);
    const echelle = Math.min(1, COTE_MAX / Math.max(image.width, image.height));
    const toile = document.createElement("canvas");
    toile.width = Math.round(image.width * echelle);
    toile.height = Math.round(image.height * echelle);
    toile.getContext("2d").drawImage(image, 0, 0, toile.width, toile.height);
    const blob = await new Promise((ok) => toile.toBlob(ok, "image/jpeg", 0.85));
    if (!blob) return fichier;
    const nom = (fichier.name || "piece").replace(/\.[^.]+$/, "") + ".jpg";
    return new File([blob], nom, { type: "image/jpeg" });
  } catch {
    return fichier; // navigateur incapable de lire l'image : le serveur dira si le format convient
  }
}

// Une face de la pièce : deux boutons (appareil photo / fichier) et l'aperçu
function ChoixFace({ titre, aide, fichier, onChange, facultatif = false }) {
  const appareil = useRef(null);
  const galerie = useRef(null);
  const apercu = fichier && fichier.type.startsWith("image/") ? URL.createObjectURL(fichier) : null;
  const choisir = (e) => { onChange(e.target.files?.[0] || null); e.target.value = ""; };
  return (
    <div className="rounded-xl border border-dashed border-gray-300 bg-white p-3">
      <p className="font-semibold">{titre} {facultatif && <span className="text-xs font-normal text-gray-500">(facultatif)</span>}</p>
      <p className="text-xs text-gray-500">{aide}</p>
      {/* capture="environment" : ouvre directement l'appareil photo arrière du téléphone */}
      <input ref={appareil} type="file" accept="image/*" capture="environment" className="hidden" onChange={choisir} />
      <input ref={galerie} type="file" accept="image/jpeg,image/png,image/webp,application/pdf,image/*" className="hidden" onChange={choisir} />
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className="btn-outline btn-sm" onClick={() => appareil.current?.click()}>📷 Prendre une photo</button>
        <button type="button" className="btn-outline btn-sm" onClick={() => galerie.current?.click()}>📁 Choisir un fichier</button>
        {fichier && <button type="button" className="btn-sm text-red-600" onClick={() => onChange(null)}>Retirer</button>}
      </div>
      {fichier && (
        <div className="mt-2 flex items-center gap-3">
          {apercu
            ? <img src={apercu} alt={`Aperçu ${titre.toLowerCase()}`} className="h-20 w-32 rounded-lg object-cover ring-1 ring-gray-200" onLoad={() => URL.revokeObjectURL(apercu)} />
            : <span className="text-3xl" aria-hidden>📄</span>}
          <span className="min-w-0 break-words text-xs text-gray-600">{fichier.name}</span>
        </div>
      )}
    </div>
  );
}

export default function PieceIdentite({ typesDocuments }) {
  const { boutique, setBoutique } = useAuth();
  const toast = useToast();
  const types = typesDocuments && Object.keys(typesDocuments).length ? typesDocuments : TYPES_PAR_DEFAUT;
  const [typeDocument, setTypeDocument] = useState("CNIB");
  const [recto, setRecto] = useState(null);
  const [verso, setVerso] = useState(null);
  const [envoi, setEnvoi] = useState(false); // toast « Liluvine vérifie votre pièce… » + jauge
  const [resultat, setResultat] = useState(null); // réponse du serveur après l'envoi

  const kyc = boutique.kyc || {};
  const ia = kyc.ia;
  const verifiee = kyc.statut === "VERIFIE";

  // Contrôle d'une face choisie : format, réduction éventuelle, taille
  async function surFace(fichier, ranger) {
    if (!fichier) return ranger(null);
    const pret = await preparerPhoto(fichier);
    if (!FORMATS.includes(pret.type)) return toast.erreur("Format non accepté : photo JPEG, PNG ou WebP, ou PDF.");
    if (pret.size > TAILLE_MAX) return toast.erreur("Fichier trop lourd : 5 Mo au maximum. Reprenez la photo.");
    ranger(pret);
  }

  // Envoi : recto (+ verso) + type -> lecture immédiate par Liluvine
  async function envoyer(e) {
    e.preventDefault();
    if (!recto) return toast.erreur("Ajoutez la photo du recto de votre pièce d'identité.");
    const formulaire = new FormData();
    formulaire.append("recto", recto);
    if (verso) formulaire.append("verso", verso);
    formulaire.append("type_document", typeDocument);
    setEnvoi(true);
    try {
      // Délai généreux : la lecture par l'IA prend en général 10 à 30 secondes
      const { data } = await apiClient.post("/boutique/kyc/piece-identite", formulaire, { timeout: 180000 });
      setResultat(data);
      // Dossier à jour ; boutique validée sur-le-champ : le bandeau d'attente disparaît
      setBoutique((b) => ({ ...b, kyc: data.kyc, validee: data.boutique_validee ? true : b.validee }));
      if (data.decision === "VERIFIE") toast.succes(data.message);
      else toast.info(data.message);
      setRecto(null);
      setVerso(null);
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi impossible : vérifiez votre connexion et réessayez."));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <section className="card space-y-4">
      {/* Attente : toast + jauge circulaire (règle du propriétaire) */}
      <Patientez actif={envoi} texte="Patientez… Liluvine vérifie votre pièce…" />
      <div>
        <h2 className="text-lg font-bold">🪪 Ma pièce d'identité</h2>
        <p className="text-sm text-gray-600">
          Photographiez votre pièce d'identité (CNIB, passeport, carte consulaire…). Liluvine, l'assistante d'adLyn,
          vérifie que le nom correspond au propriétaire de la boutique : si c'est le cas, votre boutique est validée tout de suite.
        </p>
      </div>

      {/* Message juste après l'envoi */}
      {resultat && (
        <p className={`rounded-xl px-3 py-2 text-sm font-semibold ${resultat.decision === "VERIFIE" ? "bg-green-100 text-green-900" : "bg-amber-100 text-amber-900"}`}>
          {resultat.message}
        </p>
      )}

      {/* Dernière lecture par Liluvine (numéro de pièce masqué) */}
      {ia && <ResultatLiluvine ia={ia} />}

      {verifiee ? (
        <p className="text-sm text-gray-600">Votre pièce est vérifiée. Pour la remplacer (nouvelle pièce), contactez l'équipe adLyn.</p>
      ) : (
        <form onSubmit={envoyer} className="space-y-3">
          <Champ label="Type de pièce">
            <select className="input" value={typeDocument} onChange={(e) => setTypeDocument(e.target.value)}>
              {Object.entries(types).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
            </select>
          </Champ>
          <div className="grid gap-3 sm:grid-cols-2">
            <ChoixFace titre="Recto" aide="Face avec votre photo et votre nom." fichier={recto} onChange={(f) => surFace(f, setRecto)} />
            <ChoixFace titre="Verso" aide="Utile pour une CNIB ou une carte consulaire." facultatif fichier={verso} onChange={(f) => surFace(f, setVerso)} />
          </div>
          <ul className="list-disc space-y-0.5 pl-5 text-xs text-gray-600">
            <li>Posez la pièce à plat, bien éclairée, sans reflet ni doigt sur le texte.</li>
            <li>Les quatre coins doivent être visibles et le nom lisible.</li>
            <li>Photo JPEG, PNG ou WebP, ou PDF · 5 Mo maximum par face.</li>
          </ul>
          <button className="btn-primary w-full sm:w-auto" disabled={envoi || !recto}>
            {envoi ? "Patientez…" : ia ? "📤 Renvoyer ma pièce" : "📤 Envoyer ma pièce"}
          </button>
        </form>
      )}
    </section>
  );
}
