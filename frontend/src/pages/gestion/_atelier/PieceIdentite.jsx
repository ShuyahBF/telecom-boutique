import { useEffect, useRef, useState } from "react";
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
//
// Lot D — étape « 🤳 Une photo de vous maintenant » : le commerçant se photographie
// avec la caméra FRONTALE en tenant sa pièce à côté de son visage. Liluvine compare
// ce visage à la photo de la pièce ; au moindre doute, un humain de l'équipe adLyn
// vérifie le dossier (le commerçant n'est prévenu que du résultat, jamais des scores).
// ============================================================================

const TAILLE_MAX = 5 * 1024 * 1024; // 5 Mo par face (comme le serveur)
const FORMATS = ["image/jpeg", "image/png", "image/webp", "application/pdf"];
const COTE_MAX = 2000; // plus grand côté d'une photo de la pièce après réduction (pixels)
const COTE_MAX_SELFIE = 1600; // selfie : suffisant pour comparer les visages, plus léger à envoyer

// Types proposés si le serveur ne répond pas encore (mêmes codes que backend/kyc_ia.py)
const TYPES_PAR_DEFAUT = {
  CNIB: "CNIB (carte nationale d'identité burkinabè)",
  PASSEPORT: "Passeport",
  CARTE_CONSULAIRE: "Carte consulaire",
};

// Dessine une image (fichier, ou image de la caméra) sur une toile réduite et la
// renvoie en JPEG de qualité 0,85 (File), ou null si le navigateur n'y arrive pas.
async function versJpeg(source, largeur, hauteur, coteMax, nom) {
  const echelle = Math.min(1, coteMax / Math.max(largeur, hauteur));
  const toile = document.createElement("canvas");
  toile.width = Math.round(largeur * echelle);
  toile.height = Math.round(hauteur * echelle);
  toile.getContext("2d").drawImage(source, 0, 0, toile.width, toile.height);
  const blob = await new Promise((ok) => toile.toBlob(ok, "image/jpeg", 0.85));
  return blob ? new File([blob], nom, { type: "image/jpeg" }) : null;
}

// Réduit une photo trop grande ou dans un format non accepté (ex. HEIC d'iPhone)
// en JPEG de qualité 0,85. Un PDF ou une petite photo sont envoyés tels quels.
async function preparerPhoto(fichier, coteMax = COTE_MAX) {
  if (fichier.type === "application/pdf") return fichier;
  const petite = FORMATS.includes(fichier.type) && fichier.size <= 1.5 * 1024 * 1024;
  if (petite) return fichier;
  try {
    const image = await createImageBitmap(fichier);
    const nom = (fichier.name || "piece").replace(/\.[^.]+$/, "") + ".jpg";
    return (await versJpeg(image, image.width, image.height, coteMax, nom)) || fichier;
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

// ----------------------------------------------------------------------------
// Lot D — « 🤳 Une photo de vous maintenant » (caméra frontale)
//   - si le navigateur le permet : aperçu EN DIRECT (getUserMedia) + bouton « Prendre la photo » ;
//   - sinon (ou en secours) : <input capture="user"> qui ouvre la caméra frontale du téléphone.
// Pas de choix dans la galerie : la photo doit être prise sur le moment.
// ----------------------------------------------------------------------------
function PriseSelfie({ fichier, onChange, obligatoire }) {
  const video = useRef(null);
  const flux = useRef(null); // flux de la caméra en cours (à couper après la prise)
  const secours = useRef(null);
  const [direct, setDirect] = useState(false); // aperçu en direct affiché ?
  const [erreurCamera, setErreurCamera] = useState("");
  const apercu = fichier ? URL.createObjectURL(fichier) : null;
  const cameraDisponible = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  // Coupe la caméra (voyant éteint) : après la prise, à l'annulation et en quittant la page
  function arreter() {
    flux.current?.getTracks().forEach((piste) => piste.stop());
    flux.current = null;
    setDirect(false);
  }
  useEffect(() => () => flux.current?.getTracks().forEach((piste) => piste.stop()), []);

  // Ouvre la caméra frontale et affiche l'aperçu en direct
  async function ouvrirCamera() {
    setErreurCamera("");
    try {
      flux.current = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 960 } }, audio: false,
      });
      setDirect(true);
      // L'élément <video> est affiché au prochain rendu : on lui branche le flux juste après
      setTimeout(() => {
        if (video.current && flux.current) {
          video.current.srcObject = flux.current;
          video.current.play().catch(() => {});
        }
      }, 0);
    } catch {
      setErreurCamera("Caméra inaccessible (autorisation refusée ?). Utilisez le bouton « Ouvrir l'appareil photo ».");
      arreter();
    }
  }

  // Capture l'image affichée, réduite en JPEG, puis coupe la caméra
  async function prendrePhoto() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const photo = await versJpeg(v, v.videoWidth, v.videoHeight, COTE_MAX_SELFIE, "selfie.jpg");
    arreter();
    if (photo) onChange(photo);
  }

  const choisir = (e) => { onChange(e.target.files?.[0] || null); e.target.value = ""; };

  return (
    <div className="rounded-xl border-2 border-dashed border-sky-300 bg-sky-50/40 p-3">
      <p className="font-semibold">
        🤳 Une photo de vous maintenant {!obligatoire && <span className="text-xs font-normal text-gray-500">(conseillée)</span>}
      </p>
      <p className="text-xs text-gray-600">
        Tenez votre pièce d'identité <b>à côté de votre visage</b>, photo de la pièce tournée vers la caméra, puis prenez la photo.
      </p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-gray-600">
        <li>Visage bien éclairé, de face, en entier dans l'image.</li>
        <li>Sans lunettes de soleil, sans casquette ni chapeau, sans masque.</li>
        <li>Pas de photo d'écran ni de photo d'une photo : l'équipe adLyn vérifie.</li>
      </ul>

      {/* Aperçu en direct de la caméra frontale (effet miroir pour se placer facilement) */}
      {direct && (
        <div className="mt-2 space-y-2">
          <video ref={video} playsInline muted className="w-full max-w-sm -scale-x-100 rounded-xl bg-black" aria-label="Aperçu de la caméra" />
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-primary btn-sm" onClick={prendrePhoto}>📷 Prendre la photo</button>
            <button type="button" className="btn-outline btn-sm" onClick={arreter}>Annuler</button>
          </div>
        </div>
      )}

      {/* capture="user" : ouvre directement la caméra FRONTALE du téléphone */}
      <input ref={secours} type="file" accept="image/*" capture="user" className="hidden" onChange={choisir} />
      {!direct && (
        <div className="mt-2 flex flex-wrap gap-2">
          {cameraDisponible && (
            <button type="button" className="btn-outline btn-sm" onClick={ouvrirCamera}>📷 Ouvrir la caméra</button>
          )}
          <button type="button" className="btn-outline btn-sm" onClick={() => secours.current?.click()}>📷 Ouvrir l'appareil photo</button>
          {fichier && <button type="button" className="btn-sm text-red-600" onClick={() => onChange(null)}>Reprendre</button>}
        </div>
      )}
      {erreurCamera && <p className="mt-1 text-xs text-red-700">{erreurCamera}</p>}
      {fichier && !direct && (
        <img src={apercu} alt="Aperçu de votre photo" className="mt-2 h-28 w-28 rounded-xl object-cover ring-1 ring-gray-200"
          onLoad={() => URL.revokeObjectURL(apercu)} />
      )}
    </div>
  );
}

export default function PieceIdentite({ typesDocuments, exigerSelfie = true }) {
  const { boutique, setBoutique } = useAuth();
  const toast = useToast();
  const formulaire = useRef(null);
  const types = typesDocuments && Object.keys(typesDocuments).length ? typesDocuments : TYPES_PAR_DEFAUT;
  const [typeDocument, setTypeDocument] = useState("CNIB");
  const [recto, setRecto] = useState(null);
  const [verso, setVerso] = useState(null);
  const [selfie, setSelfie] = useState(null); // lot D : photo du DG tenant sa pièce
  const [envoi, setEnvoi] = useState(false); // toast « Liluvine vérifie votre pièce… » + jauge
  const [resultat, setResultat] = useState(null); // réponse du serveur après l'envoi

  const kyc = boutique.kyc || {};
  const ia = kyc.ia;
  const verifiee = kyc.statut === "VERIFIE";
  // Lot D — états posés par l'équipe adLyn : revue humaine en cours / nouvelle photo demandée
  const nouvellePhoto = kyc.nouvelle_photo?.motif ? kyc.nouvelle_photo : null;
  const enRevue = !verifiee && kyc.revue_humaine_requise && !nouvellePhoto;

  // Contrôle d'une photo choisie : format, réduction éventuelle, taille
  async function surFace(fichier, ranger, coteMax = COTE_MAX) {
    if (!fichier) return ranger(null);
    const pret = await preparerPhoto(fichier, coteMax);
    if (!FORMATS.includes(pret.type)) return toast.erreur("Format non accepté : photo JPEG, PNG ou WebP, ou PDF.");
    if (pret.size > TAILLE_MAX) return toast.erreur("Fichier trop lourd : 5 Mo au maximum. Reprenez la photo.");
    ranger(pret);
  }

  // Lot D — le selfie doit être une PHOTO (jamais un PDF)
  async function surSelfie(fichier) {
    if (fichier && !fichier.type.startsWith("image/")) return toast.erreur("Prenez une photo de vous (pas un PDF).");
    return surFace(fichier, setSelfie, COTE_MAX_SELFIE);
  }

  // Envoi : recto (+ verso) + selfie + type -> lecture et comparaison immédiates par Liluvine
  async function envoyer(e) {
    e.preventDefault();
    if (!recto) return toast.erreur("Ajoutez la photo du recto de votre pièce d'identité.");
    if (exigerSelfie && !selfie) return toast.erreur("Ajoutez une photo de vous tenant votre pièce à côté de votre visage.");
    const donnees = new FormData();
    donnees.append("recto", recto);
    if (verso) donnees.append("verso", verso);
    if (selfie) donnees.append("selfie", selfie);
    donnees.append("type_document", typeDocument);
    setEnvoi(true);
    try {
      // Délai généreux : la vérification par l'IA prend en général 10 à 40 secondes
      const { data } = await apiClient.post("/boutique/kyc/piece-identite", donnees, { timeout: 180000 });
      setResultat(data);
      // Dossier à jour ; boutique validée sur-le-champ : le bandeau d'attente disparaît
      setBoutique((b) => ({ ...b, kyc: data.kyc, validee: data.boutique_validee ? true : b.validee }));
      if (data.decision === "VERIFIE") toast.succes(data.message);
      else toast.info(data.message);
      setRecto(null);
      setVerso(null);
      setSelfie(null);
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi impossible : vérifiez votre connexion et réessayez."));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <section className="card space-y-4">
      {/* Attente : toast + jauge circulaire (règle du propriétaire) */}
      <Patientez actif={envoi} texte="Patientez… Liluvine vérifie votre pièce et votre photo…" />
      <div>
        <h2 className="text-lg font-bold">🪪 Ma pièce d'identité</h2>
        <p className="text-sm text-gray-600">
          Photographiez votre pièce d'identité (CNIB, passeport, carte consulaire…), puis prenez une photo de vous en la tenant
          à côté de votre visage. Liluvine, l'assistante d'adLyn, vérifie que la pièce est bien la vôtre : si tout est clair,
          votre boutique est validée tout de suite ; sinon l'équipe adLyn vérifie votre dossier.
        </p>
      </div>

      {/* Message juste après l'envoi : validée / en revue humaine */}
      {resultat && (
        <p className={`rounded-xl px-3 py-2 text-sm font-semibold ${resultat.decision === "VERIFIE" ? "bg-green-100 text-green-900" : "bg-amber-100 text-amber-900"}`}>
          {resultat.decision === "VERIFIE" ? "✅ " : "🔍 "}{resultat.message}
        </p>
      )}

      {/* Lot D — dossier en revue humaine (après rechargement de la page) : aucun score affiché */}
      {!resultat && enRevue && (
        <p className="rounded-xl bg-amber-100 px-3 py-2 text-sm font-semibold text-amber-900">
          🔍 Notre équipe vérifie votre dossier, vous serez prévenu par WhatsApp.
        </p>
      )}

      {/* Lot D — l'équipe adLyn demande une nouvelle photo : motif + bouton pour renvoyer */}
      {nouvellePhoto && !verifiee && (
        <div className="rounded-xl border-2 border-orange-300 bg-orange-50 p-3 text-sm text-orange-900">
          <p className="font-bold">📷 L'équipe adLyn vous demande une nouvelle photo</p>
          <p className="mt-1">{nouvellePhoto.motif}</p>
          <button type="button" className="btn-primary btn-sm mt-2"
            onClick={() => formulaire.current?.scrollIntoView({ behavior: "smooth", block: "start" })}>
            📤 Renvoyer mes photos
          </button>
        </div>
      )}

      {/* Dernière lecture par Liluvine (numéro de pièce masqué, sans score) */}
      {ia && <ResultatLiluvine ia={ia} />}

      {verifiee ? (
        <p className="text-sm text-gray-600">Votre pièce est vérifiée. Pour la remplacer (nouvelle pièce), contactez l'équipe adLyn.</p>
      ) : (
        <form ref={formulaire} onSubmit={envoyer} className="space-y-3">
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
          {/* Lot D — étape du selfie */}
          <PriseSelfie fichier={selfie} onChange={surSelfie} obligatoire={exigerSelfie} />
          <p className="text-xs text-gray-500">
            🔒 Vos photos servent uniquement à vérifier votre identité. Elles sont rangées dans un espace privé et ne sont
            visibles que par l'équipe adLyn.
          </p>
          <button className="btn-primary w-full sm:w-auto" disabled={envoi || !recto || (exigerSelfie && !selfie)}>
            {envoi ? "Patientez…" : ia ? "📤 Renvoyer ma pièce et ma photo" : "📤 Envoyer ma pièce et ma photo"}
          </button>
        </form>
      )}
    </section>
  );
}
