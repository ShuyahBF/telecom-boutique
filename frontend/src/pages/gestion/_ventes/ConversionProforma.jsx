import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Modal from "@/components/Modal";
import Patientez from "@/components/Patientez";
import { useToast } from "@/components/Toast";
import { apiClient, messageErreur } from "@/lib/api";
import { prix } from "@/lib/format";

// Fenêtre « Convertir la proforma en facture », partagée par la LISTE des documents
// et l'écran d'une proforma. Deux choix :
//   1. « Créer la facture (brouillon) » : la facture s'ouvre et propose aussitôt
//      « Valider la facture » (adresse ?valider=1) ;
//   2. « Convertir et valider » : une seule étape, après confirmation (numéro définitif
//      et sortie du stock). Si la validation est refusée (stock insuffisant…), la
//      facture reste en brouillon et le motif est affiché.
// Propriétés : proforma ({ id, numero, total_ttc }), devise, onFermer,
// avantConversion (facultatif : ex. enregistrer les modifications en cours ; renvoie false pour arrêter).
export default function ConversionProforma({ proforma, devise = "FCFA", onFermer, avantConversion }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [enCours, setEnCours] = useState(false);
  const [confirmerValidation, setConfirmerValidation] = useState(false); // 2e étape du choix « Convertir et valider »

  // Appel du serveur, puis ouverture de la facture créée
  async function convertir(avecValidation) {
    if (avantConversion && (await avantConversion()) === false) return;
    setEnCours(true);
    try {
      const { data } = await apiClient.post(`/documents/${proforma.id}/convertir`, null,
        { params: avecValidation ? { valider_facture: true } : {} });
      if (avecValidation && data.statut === "VALIDE") {
        toast.succes(`Facture validée : n° ${data.numero}`);
        navigate(`/gestion/documents/${data.id}`);
      } else if (avecValidation) {
        // Facture créée, mais validation refusée : elle reste en brouillon
        toast.erreur(`Facture créée en brouillon, validation impossible : ${data.validation_erreur || "erreur"}`);
        navigate(`/gestion/documents/${data.id}`);
      } else {
        toast.succes("Facture créée à partir de la proforma : vérifiez-la puis validez-la");
        navigate(`/gestion/documents/${data.id}?valider=1`);
      }
      onFermer?.();
    } catch (err) {
      toast.erreur(messageErreur(err, "Conversion impossible"));
    } finally {
      setEnCours(false);
    }
  }

  return (
    <Modal ouvert={!!proforma} titre={`Convertir la proforma ${proforma?.numero || ""} en facture`} onFermer={enCours ? undefined : onFermer}>
      <Patientez actif={enCours} />
      {!confirmerValidation ? (
        <div className="space-y-4 text-sm text-gray-700">
          <p>Une <b>facture</b> va être créée avec les mêmes lignes{proforma?.total_ttc != null ? <> ({prix(proforma.total_ttc, devise)} TTC)</> : null}. La proforma sera marquée comme <b>acceptée</b> et reliée à la facture ; elle ne pourra plus être convertie une seconde fois.</p>
          <div className="flex flex-col gap-2">
            <button type="button" className="btn-primary" disabled={enCours} onClick={() => convertir(false)}>
              → Créer la facture (brouillon, à valider ensuite)
            </button>
            <button type="button" className="btn-outline" disabled={enCours} onClick={() => setConfirmerValidation(true)}>
              ✓ Convertir et valider en une étape…
            </button>
            <button type="button" className="btn-outline" disabled={enCours} onClick={onFermer}>Retour</button>
          </div>
        </div>
      ) : (
        <div className="space-y-4 text-sm text-gray-700">
          <p><b>Convertir et valider</b> est <b>définitif</b> :</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>la facture reçoit son <b>numéro définitif</b> (FAC-…) ;</li>
            <li>les articles sont <b>sortis du stock</b> (si un article manque, la facture reste en brouillon) ;</li>
            <li>elle ne pourra plus être modifiée, seulement annulée.</li>
          </ul>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button type="button" className="btn-outline" disabled={enCours} onClick={() => setConfirmerValidation(false)}>Retour</button>
            <button type="button" className="btn-primary" disabled={enCours} onClick={() => convertir(true)}>
              {enCours ? "Patientez…" : "Convertir et valider"}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
