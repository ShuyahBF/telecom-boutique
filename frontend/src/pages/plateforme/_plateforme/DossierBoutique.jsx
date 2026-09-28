// Fenêtre « Dossier de la boutique » (super-administrateur) :
// 1. informations d'identification (modifiables) ;
// 2. pièces justificatives du dossier KYC (voir, ajouter, supprimer) ;
// 3. décision de vérification : Vérifié / Rejeté (avec motif) / en attente.
import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { BadgeKyc, Champ, ChampsIdentification, erreurCoordonnees, identificationVersApi } from "./composants";
import { FORMATS_JUSTIFICATIFS, messageErreurFichier, ouvrirFichier, TYPES_PIECES_KYC } from "./outils";

/** Fiche boutique -> valeurs du formulaire d'identification (textes) */
function versFormulaire(b) {
  return {
    pays: b.pays || "", ville: b.ville || "", adresse: b.adresse || "",
    latitude: b.latitude ?? "", longitude: b.longitude ?? "",
    dg_nom: b.dg_nom || "", ifu: b.ifu || "", cnss: b.cnss || "", rccm: b.rccm || "",
  };
}

/**
 * boutique    : la boutique affichée (null = fenêtre fermée)
 * onMaj(b)    : appelé avec la boutique mise à jour (infos ou KYC), pour
 *               rafraîchir la liste de la page sans tout recharger.
 */
export default function DossierBoutique({ boutique, onFermer, onMaj }) {
  const toast = useToast();
  const [infos, setInfos] = useState(null); // formulaire d'identification
  const [ajout, setAjout] = useState({ type_piece: "PIECE_IDENTITE_DG", fichier: null });
  const [motif, setMotif] = useState(""); // motif du rejet
  const [occupe, setOccupe] = useState(""); // action en cours ("infos", "ajout", "decision"…)
  const [cleFichier, setCleFichier] = useState(0); // pour vider le champ « fichier » après un envoi

  // À l'ouverture (ou au changement de boutique) : on remplit le formulaire
  const idBoutique = boutique?.id;
  useEffect(() => {
    if (!boutique) return;
    setInfos(versFormulaire(boutique));
    setMotif(boutique.kyc?.motif_rejet || "");
    setAjout({ type_piece: "PIECE_IDENTITE_DG", fichier: null });
  }, [idBoutique]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!boutique || !infos) return null;
  const kyc = boutique.kyc || { statut: "NON_FOURNI", documents: [] };
  const base = `/plateforme/boutiques/${boutique.id}`;

  // --- 1. Enregistrer les informations d'identification (PATCH) ---
  async function enregistrerInfos(e) {
    e.preventDefault();
    const erreur = erreurCoordonnees(infos);
    if (erreur) return toast.erreur(erreur);
    if (infos.dg_nom.trim().length < 2) return toast.erreur("Indiquez le nom du DG.");
    const donnees = identificationVersApi(infos);
    setOccupe("infos");
    try {
      const { data } = await apiClient.patch(base, donnees);
      onMaj({ ...boutique, ...data });
      toast.succes("Informations d'identification enregistrées");
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible : vérifiez les champs"));
    } finally {
      setOccupe("");
    }
  }

  // --- 2a. Ouvrir un justificatif (fichier protégé) dans un nouvel onglet ---
  async function ouvrir(piece) {
    try {
      await ouvrirFichier(`${base}/kyc/documents/${piece.id}`);
    } catch (err) {
      toast.erreur(await messageErreurFichier(err, "Impossible d'ouvrir ce justificatif"));
    }
  }

  // --- 2b. Ajouter un justificatif (envoi du fichier en « multipart ») ---
  async function ajouter(e) {
    e.preventDefault();
    if (!ajout.fichier) return toast.erreur("Choisissez un fichier (PDF, JPEG ou PNG).");
    const formulaire = new FormData();
    formulaire.append("type_piece", ajout.type_piece);
    formulaire.append("fichier", ajout.fichier);
    setOccupe("ajout");
    try {
      const { data } = await apiClient.post(`${base}/kyc/documents`, formulaire);
      onMaj({ ...boutique, kyc: data });
      setAjout({ ...ajout, fichier: null });
      setCleFichier((n) => n + 1);
      toast.succes("Justificatif ajouté : le dossier repasse « En attente » de vérification");
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi du justificatif impossible"));
    } finally {
      setOccupe("");
    }
  }

  // --- 2c. Supprimer un justificatif (après confirmation) ---
  async function supprimer(piece) {
    if (!window.confirm(`Supprimer définitivement « ${piece.libelle} » (${piece.nom_fichier || "fichier"}) ?`)) return;
    setOccupe(`suppr-${piece.id}`);
    try {
      const { data } = await apiClient.delete(`${base}/kyc/documents/${piece.id}`);
      onMaj({ ...boutique, kyc: data });
      toast.succes("Justificatif supprimé");
    } catch (err) {
      toast.erreur(messageErreur(err, "Suppression impossible"));
    } finally {
      setOccupe("");
    }
  }

  // --- 3. Décision : VERIFIE, REJETE (motif obligatoire) ou EN_ATTENTE ---
  async function decider(statut) {
    if (statut === "REJETE" && !motif.trim()) return toast.erreur("Indiquez le motif du rejet : il sera affiché au DG.");
    setOccupe("decision");
    try {
      const { data } = await apiClient.post(`${base}/kyc/decision`, { statut, motif_rejet: statut === "REJETE" ? motif.trim() : "" });
      onMaj({ ...boutique, kyc: data });
      if (statut !== "REJETE") setMotif("");
      toast.succes({ VERIFIE: "Dossier vérifié", REJETE: "Dossier rejeté", EN_ATTENTE: "Dossier remis en attente" }[statut]);
    } catch (err) {
      toast.erreur(messageErreur(err, "Décision impossible"));
    } finally {
      setOccupe("");
    }
  }

  const maj = (champ, valeur) => setInfos((v) => ({ ...v, [champ]: valeur }));

  return (
    <Modal ouvert titre={`Dossier — ${boutique.nom}`} onFermer={onFermer} large>
      <div className="space-y-6">
        {/* Résumé de l'état du dossier KYC */}
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-gray-50 p-3 text-sm">
          <BadgeKyc statut={kyc.statut} />
          <span className="text-gray-600">{kyc.documents?.length || 0} justificatif(s)</span>
          {kyc.date_verification && kyc.statut !== "NON_FOURNI" && (
            <span className="text-gray-500">· décision du {dateHeure(kyc.date_verification)}{kyc.verifie_par ? ` par ${kyc.verifie_par}` : ""}</span>
          )}
          {kyc.statut === "REJETE" && kyc.motif_rejet && (
            <p className="w-full text-red-700">Motif du rejet : {kyc.motif_rejet}</p>
          )}
        </div>

        {/* ===== 1. Identification & localisation ===== */}
        <section>
          <h3 className="mb-3 text-base font-bold">1. Identification & localisation</h3>
          <form onSubmit={enregistrerInfos} className="grid gap-3 sm:grid-cols-2">
            <Champ label="Nom du DG *" className="sm:col-span-2" aide="Directeur Général (responsable légal de la boutique).">
              <input className="input" required minLength={2} maxLength={120} value={infos.dg_nom} onChange={(e) => maj("dg_nom", e.target.value)} />
            </Champ>
            <ChampsIdentification valeurs={infos} maj={maj} />
            <div className="sm:col-span-2 sm:text-right">
              <button className="btn-primary w-full sm:w-auto" disabled={occupe === "infos"}>{occupe === "infos" ? "Enregistrement…" : "Enregistrer les informations"}</button>
            </div>
          </form>
        </section>

        {/* ===== 2. Pièces justificatives ===== */}
        <section className="border-t border-gray-200 pt-5">
          <h3 className="mb-1 text-base font-bold">2. Pièces justificatives</h3>
          <p className="mb-3 text-xs text-gray-500">Documents confidentiels : visibles uniquement par vous et par le DG de la boutique.</p>

          {/* Liste des pièces déjà fournies */}
          {kyc.documents?.length ? (
            <ul className="mb-4 divide-y divide-gray-100 rounded-xl border border-gray-200">
              {kyc.documents.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-3 p-3">
                  <span className="text-2xl">{d.format === "application/pdf" ? "📄" : "🖼️"}</span>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">{d.libelle}</p>
                    <p className="truncate text-xs text-gray-500">{d.nom_fichier || "fichier"} · ajouté le {dateHeure(d.date)}{d.ajoute_par ? ` par ${d.ajoute_par}` : ""}</p>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" className="btn-outline btn-sm" onClick={() => ouvrir(d)}>Ouvrir ↗</button>
                    <button type="button" className="btn-outline btn-sm text-red-600" disabled={occupe === `suppr-${d.id}`} onClick={() => supprimer(d)}>Supprimer</button>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mb-4 rounded-xl border border-dashed border-gray-300 p-4 text-center text-sm text-gray-500">Aucun justificatif pour l'instant.</p>
          )}

          {/* Ajout d'une pièce : type + fichier */}
          <form onSubmit={ajouter} className="grid gap-3 rounded-xl bg-gray-50 p-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <Champ label="Type de pièce">
              <select className="input bg-white" value={ajout.type_piece} onChange={(e) => setAjout({ ...ajout, type_piece: e.target.value })}>
                {Object.entries(TYPES_PIECES_KYC).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
              </select>
            </Champ>
            <Champ label="Fichier">
              <input key={cleFichier} type="file" accept={FORMATS_JUSTIFICATIFS} className="input bg-white py-2 text-sm"
                onChange={(e) => setAjout({ ...ajout, fichier: e.target.files?.[0] || null })} />
            </Champ>
            <button className="btn-primary" disabled={occupe === "ajout" || !ajout.fichier}>{occupe === "ajout" ? "Envoi…" : "Ajouter"}</button>
          </form>
          <p className="mt-1 text-xs text-gray-500">Formats acceptés : PDF, JPEG ou PNG (15 Mo maximum).</p>
        </section>

        {/* ===== 3. Décision de vérification ===== */}
        <section className="border-t border-gray-200 pt-5">
          <h3 className="mb-1 text-base font-bold">3. Décision</h3>
          <p className="mb-3 text-xs text-gray-500">Contrôlez les pièces (identité du DG, IFU, RCCM…) puis indiquez votre décision. Le DG la voit dans ses paramètres.</p>
          <Champ label="Motif du rejet (obligatoire pour rejeter)">
            <textarea className="input" rows={2} maxLength={500} value={motif} onChange={(e) => setMotif(e.target.value)}
              placeholder="Ex. : pièce d'identité illisible, merci d'envoyer une photo nette." />
          </Champ>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <button type="button" className="btn bg-green-600 text-white hover:bg-green-700" disabled={!!occupe || !kyc.documents?.length}
              title={!kyc.documents?.length ? "Aucun justificatif à vérifier" : ""} onClick={() => decider("VERIFIE")}>✅ Vérifié</button>
            <button type="button" className="btn-danger" disabled={!!occupe} onClick={() => decider("REJETE")}>✖ Rejeter</button>
            <button type="button" className="btn-outline" disabled={!!occupe} onClick={() => decider("EN_ATTENTE")}>Remettre en attente</button>
          </div>
        </section>
      </div>
    </Modal>
  );
}
