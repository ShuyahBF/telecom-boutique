import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, dateHeure } from "@/lib/format";
import { useToast } from "@/components/Toast";
import { Champ, Vide } from "./communs";

// Présentation de chaque statut du dossier KYC : couleurs, icône et explication
const PRESENTATION_STATUTS = {
  NON_FOURNI: { icone: "📂", classe: "border-gray-300 bg-gray-50 text-gray-800", texte: "Aucun justificatif envoyé pour l'instant. Ajoutez vos pièces ci-dessous." },
  EN_ATTENTE: { icone: "⏳", classe: "border-amber-300 bg-amber-50 text-amber-900", texte: "Vos justificatifs ont bien été reçus. L'administrateur de la plateforme va les vérifier." },
  VERIFIE: { icone: "✅", classe: "border-green-300 bg-green-50 text-green-900", texte: "Votre boutique est identifiée. Pour retirer un justificatif, contactez l'administrateur." },
  REJETE: { icone: "⛔", classe: "border-red-300 bg-red-50 text-red-900", texte: "Votre dossier a été refusé. Corrigez les points signalés puis envoyez de nouveaux justificatifs." },
};

// Formats acceptés pour les justificatifs, et taille maximale (15 Mo, comme le serveur)
const FORMATS_ACCEPTES = ["application/pdf", "image/jpeg", "image/png"];
const TAILLE_MAX = 15 * 1024 * 1024;

// Taille lisible d'un fichier : 245 Ko, 3,2 Mo…
function taille(octets) {
  if (octets < 1024 * 1024) return `${Math.max(1, Math.round(octets / 1024))} Ko`;
  return `${(octets / 1024 / 1024).toFixed(1).replace(".", ",")} Mo`;
}

// Onglet « Identité & KYC » : dossier d'identification de la boutique.
// Le DG y envoie les justificatifs (pièce d'identité, RCCM, IFU, CNSS…) que
// l'administrateur de la plateforme vérifie. Les fichiers sont PRIVÉS.
export default function ParamKyc({ allerA }) {
  const { boutique, setBoutique } = useAuth();
  const toast = useToast();
  const champFichier = useRef(null);

  const kyc = boutique.kyc || { statut: "NON_FOURNI", documents: [] };
  const presentation = PRESENTATION_STATUTS[kyc.statut] || PRESENTATION_STATUTS.NON_FOURNI;

  // Types de pièces proposés (GET /boutique/kyc/types → { types: { CODE: "Libellé" } })
  const [types, setTypes] = useState({});
  // Formulaire d'ajout : type de pièce choisi + fichier sélectionné
  const [typePiece, setTypePiece] = useState("");
  const [fichier, setFichier] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const [enCours, setEnCours] = useState(""); // id du justificatif en cours d'ouverture / suppression

  // Chargement de la liste des types au premier affichage de l'onglet
  useEffect(() => {
    apiClient.get("/boutique/kyc/types")
      .then(({ data }) => {
        setTypes(data.types || {});
        setTypePiece((t) => t || Object.keys(data.types || {})[0] || "");
      })
      .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger les types de justificatifs")));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Le serveur renvoie le dossier KYC à jour : on le range dans la boutique en mémoire
  const majKyc = (nouveau) => setBoutique((b) => ({ ...b, kyc: nouveau }));

  // Choix du fichier : contrôle du format et de la taille AVANT l'envoi
  function surChoixFichier(e) {
    const f = e.target.files?.[0] || null;
    if (f && !FORMATS_ACCEPTES.includes(f.type)) {
      toast.erreur("Format non accepté : choisissez un PDF, un JPEG ou un PNG.");
      e.target.value = "";
      setFichier(null);
      return;
    }
    if (f && f.size > TAILLE_MAX) {
      toast.erreur(`Fichier trop lourd (${taille(f.size)}) : 15 Mo maximum.`);
      e.target.value = "";
      setFichier(null);
      return;
    }
    setFichier(f);
  }

  // Envoi du justificatif (POST multipart : champs « fichier » et « type_piece »)
  async function envoyer(e) {
    e.preventDefault();
    if (!fichier || !typePiece) return;
    const formulaire = new FormData();
    formulaire.append("fichier", fichier);
    formulaire.append("type_piece", typePiece);
    setEnvoi(true);
    try {
      const { data } = await apiClient.post("/boutique/kyc/documents", formulaire);
      majKyc(data);
      toast.succes(`« ${types[typePiece] || "Justificatif"} » envoyé : il sera vérifié par l'administrateur`);
      setFichier(null);
      if (champFichier.current) champFichier.current.value = "";
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi impossible (PDF, JPEG ou PNG, 15 Mo maximum)"));
    } finally {
      setEnvoi(false);
    }
  }

  // Ouverture d'un justificatif : le fichier est protégé (il faut être connecté),
  // on le télécharge donc avec le jeton puis on l'affiche dans un nouvel onglet.
  async function ouvrir(piece) {
    // L'onglet est ouvert TOUT DE SUITE (sinon le navigateur le bloque comme une publicité)
    const onglet = window.open("", "_blank");
    setEnCours(piece.id);
    try {
      const { data } = await apiClient.get(`/boutique/kyc/documents/${piece.id}`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      if (onglet) {
        onglet.location.href = url;
      } else {
        // Fenêtre bloquée : on propose le fichier en téléchargement
        const lien = document.createElement("a");
        lien.href = url;
        lien.download = piece.nom_fichier || "justificatif";
        lien.click();
      }
      // L'adresse temporaire est libérée au bout d'une minute (le fichier reste affiché)
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      onglet?.close();
      toast.erreur(messageErreur(err, "Impossible d'ouvrir ce justificatif"));
    } finally {
      setEnCours("");
    }
  }

  // Suppression d'un justificatif (refusée par le serveur si le dossier est vérifié)
  async function supprimer(piece) {
    if (!window.confirm(`Supprimer « ${piece.libelle} » (${piece.nom_fichier}) ?`)) return;
    setEnCours(piece.id);
    try {
      const { data } = await apiClient.delete(`/boutique/kyc/documents/${piece.id}`);
      majKyc(data);
      toast.succes("Justificatif supprimé");
    } catch (err) {
      toast.erreur(messageErreur(err, "Suppression impossible"));
    } finally {
      setEnCours("");
    }
  }

  // Informations légales rappelées (modifiables dans l'onglet « Ma boutique »)
  const infosLegales = [
    { libelle: "Nom du DG", valeur: boutique.dg_nom },
    { libelle: "IFU", valeur: boutique.ifu },
    { libelle: "CNSS", valeur: boutique.cnss },
    { libelle: "RCCM", valeur: boutique.rccm },
  ];

  return (
    <div className="space-y-5">
      {/* Statut du dossier, en grand et en couleur */}
      <div className={`flex flex-col gap-3 rounded-2xl border-2 p-5 sm:flex-row sm:items-center ${presentation.classe}`}>
        <span className="text-4xl" aria-hidden>{presentation.icone}</span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide opacity-70">Statut du dossier KYC</p>
          <p className="text-2xl font-extrabold">{kyc.statut_libelle || "Non fourni"}</p>
          <p className="mt-1 text-sm">{presentation.texte}</p>
          {/* Motif du refus, donné par l'administrateur */}
          {kyc.motif_rejet && (
            <p className="mt-2 rounded-xl bg-white/70 px-3 py-2 text-sm"><b>Motif du refus :</b> {kyc.motif_rejet}</p>
          )}
          {kyc.statut === "VERIFIE" && kyc.date_verification && (
            <p className="mt-1 text-xs opacity-80">Vérifié le {date(kyc.date_verification)}{kyc.verifie_par ? ` par ${kyc.verifie_par}` : ""}</p>
          )}
        </div>
      </div>

      {/* min-w-0 : empêche un nom de fichier très long d'élargir la page sur téléphone */}
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="min-w-0 space-y-5 lg:col-span-2">
          {/* Liste des justificatifs déjà envoyés */}
          <section className="card p-0">
            <div className="border-b border-gray-100 px-5 py-3">
              <h2 className="font-bold">Justificatifs envoyés <span className="ml-1 rounded-full bg-gray-100 px-2 text-xs text-gray-600">{kyc.documents?.length || 0}</span></h2>
            </div>
            {!kyc.documents?.length ? <Vide icone="📎">Aucun justificatif pour l'instant.</Vide> : (
              <ul className="divide-y divide-gray-100">
                {kyc.documents.map((piece) => (
                  <li key={piece.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-lg" aria-hidden>
                      {piece.format === "application/pdf" ? "📄" : "🖼️"}
                    </span>
                    {/* Largeur minimale : sur téléphone, les boutons passent à la ligne au lieu d'écraser le texte */}
                    <div className="min-w-[11rem] flex-1">
                      <p className="font-semibold">{piece.libelle}</p>
                      <p className="break-words text-sm text-gray-500">{piece.nom_fichier || "Fichier"} · ajouté le {dateHeure(piece.date)}{piece.ajoute_par ? ` par ${piece.ajoute_par}` : ""}</p>
                    </div>
                    <div className="flex gap-2">
                      <button type="button" className="btn-outline btn-sm" disabled={enCours === piece.id} onClick={() => ouvrir(piece)}>👁️ Ouvrir</button>
                      <button type="button" className="btn-outline btn-sm text-red-600" disabled={enCours === piece.id} onClick={() => supprimer(piece)}>Supprimer</button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Formulaire d'ajout d'un justificatif */}
          <form onSubmit={envoyer} className="card grid gap-4 sm:grid-cols-2">
            <h2 className="font-bold sm:col-span-2">Ajouter un justificatif</h2>
            <Champ label="Type de pièce">
              <select className="input" value={typePiece} onChange={(e) => setTypePiece(e.target.value)} required>
                {Object.entries(types).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
              </select>
            </Champ>
            <Champ label="Fichier" aide={fichier ? `${fichier.name} · ${taille(fichier.size)}` : "PDF, JPEG ou PNG · 15 Mo maximum"}>
              <input ref={champFichier} type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" required
                className="input py-2 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-primary/10 file:px-3 file:py-1 file:font-semibold file:text-primary"
                onChange={surChoixFichier} />
            </Champ>
            <div className="sm:col-span-2">
              <button className="btn-primary w-full sm:w-auto" disabled={envoi || !fichier || !typePiece}>{envoi ? "Envoi…" : "📤 Envoyer le justificatif"}</button>
            </div>
          </form>
        </div>

        {/* Colonne de droite : confidentialité + rappel des informations légales */}
        <div className="min-w-0 space-y-5">
          <div className="card border-primary/30 bg-primary/5 text-sm">
            <h2 className="mb-2 font-bold">🔒 Documents privés</h2>
            <p>Ces documents sont privés, visibles seulement par vous et l'administrateur de la plateforme. Ils ne sont jamais affichés sur votre vitrine.</p>
            <p className="mt-2 text-gray-600">Chaque nouveau justificatif remet le dossier « en attente de vérification ».</p>
          </div>

          <div className="card">
            <h2 className="mb-3 font-bold">Informations légales</h2>
            <dl className="space-y-2 text-sm">
              {infosLegales.map((i) => (
                <div key={i.libelle} className="flex justify-between gap-3">
                  <dt className="text-gray-500">{i.libelle}</dt>
                  <dd className={`text-right font-semibold ${i.valeur ? "" : "text-amber-700"}`}>{i.valeur || "Non renseigné"}</dd>
                </div>
              ))}
            </dl>
            <button type="button" className="mt-4 text-sm font-semibold text-primary" onClick={() => allerA?.("boutique")}>Modifier dans « Ma boutique » →</button>
          </div>
        </div>
      </div>
    </div>
  );
}
