import Modal from "@/components/Modal";

// Fenêtre de confirmation (« Êtes-vous sûr ? ») avant une action importante.
// Exemple : <Confirmation ouvert titre="Valider ?" onConfirmer={...} onFermer={...}>texte</Confirmation>
export default function Confirmation({ ouvert, titre, children, libelleBouton = "Confirmer", danger = false, enCours = false, onConfirmer, onFermer }) {
  return (
    <Modal ouvert={ouvert} titre={titre} onFermer={onFermer}>
      <div className="space-y-4 text-sm text-gray-700">{children}</div>
      <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" className="btn-outline" onClick={onFermer} disabled={enCours}>Retour</button>
        <button type="button" className={danger ? "btn-danger" : "btn-primary"} onClick={onConfirmer} disabled={enCours}>
          {enCours ? "Patientez…" : libelleBouton}
        </button>
      </div>
    </Modal>
  );
}
