import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import Chargement from "@/components/Chargement";
import FeuilleDocument from "@/components/FeuilleDocument";

// Facture ou proforma au format A4, prête à imprimer ou à enregistrer en PDF
// (bouton « Imprimer » = boîte d'impression du navigateur, choisir « Enregistrer au format PDF »).
// En bas de la feuille : QR code chiffré vers la page de la boutique et l'espace client,
// et, à côté, le bloc « Payer par PI-SPI » si la boutique l'a activé (Paramètres).
export default function DocumentImprimable() {
  const { id } = useParams();
  const { boutique } = useAuth();
  const [doc, setDoc] = useState(null);
  const [qrUrl, setQrUrl] = useState("");
  const [pispi, setPispi] = useState(null); // bloc « Payer par PI-SPI » (paramètres de la boutique)
  const [erreur, setErreur] = useState("");

  // Chargement du document, puis de l'adresse de son QR code (jeton chiffré créé par le serveur)
  useEffect(() => {
    apiClient.get(`/documents/${id}`)
      .then(({ data }) => setDoc(data))
      .catch((err) => setErreur(messageErreur(err, "Document introuvable")));
    apiClient.get(`/documents/${id}/qr`)
      .then(({ data }) => { setQrUrl(data.url); setPispi(data.pispi || null); })
      .catch(() => setQrUrl("")); // sans QR code, la feuille reste imprimable
  }, [id]);

  // Titre de l'onglet = nom du fichier proposé lors de l'enregistrement en PDF
  useEffect(() => {
    if (doc) document.title = `${doc.type_document === "PRO" ? "Proforma" : "Facture"} ${doc.numero || "brouillon"} - ${doc.client?.nom || ""}`;
  }, [doc]);

  if (erreur) return <p className="p-10 text-center text-red-600">{erreur}</p>;
  if (!doc || !boutique) return <Chargement plein />;

  return (
    <FeuilleDocument doc={doc} boutique={boutique} qrUrl={qrUrl} pispi={pispi}>
      <Link to={`/gestion/documents/${doc.id}`} className="btn-outline btn-sm">← Retour au document</Link>
      <button type="button" className="btn-primary" onClick={() => window.print()}>🖨 Imprimer / Enregistrer en PDF</button>
    </FeuilleDocument>
  );
}
