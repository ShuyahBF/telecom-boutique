import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, montant, prix } from "@/lib/format";
import Chargement from "@/components/Chargement";

// Mise en page propre à l'impression : format A4, marges de 12 mm, couleurs
// conservées ; le filigrane se répète sur chaque page imprimée.
const STYLE_IMPRESSION = `
  @page { size: A4; margin: 12mm; }
  .feuille-a4 { width: 210mm; min-height: 297mm; padding: 14mm 12mm; }
  .filigrane { position: absolute; }
  @media print {
    html, body { background: #fff !important; }
    .feuille-a4 { width: auto; min-height: 0; padding: 0; margin: 0 !important; box-shadow: none !important; border: 0 !important; }
    .fond-impression { background: #fff !important; padding: 0 !important; }
    .filigrane { position: fixed; }
    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    tr { break-inside: avoid; }
  }
`;

// Facture ou proforma au format A4, prête à imprimer ou à enregistrer en PDF
// (bouton « Imprimer » = boîte d'impression du navigateur, choisir « Enregistrer au format PDF »).
export default function DocumentImprimable() {
  const { id } = useParams();
  const { boutique } = useAuth();
  const [doc, setDoc] = useState(null);
  const [erreur, setErreur] = useState("");
  const devise = boutique?.devise || "FCFA";

  // Chargement du document
  useEffect(() => {
    apiClient.get(`/documents/${id}`)
      .then(({ data }) => setDoc(data))
      .catch((err) => setErreur(messageErreur(err, "Document introuvable")));
  }, [id]);

  // Titre de l'onglet = nom du fichier proposé lors de l'enregistrement en PDF
  useEffect(() => {
    if (doc) document.title = `${doc.type_document === "PRO" ? "Proforma" : "Facture"} ${doc.numero || "brouillon"} - ${doc.client?.nom || ""}`;
  }, [doc]);

  if (erreur) return <p className="p-10 text-center text-red-600">{erreur}</p>;
  if (!doc || !boutique) return <Chargement plein />;

  const proforma = doc.type_document === "PRO";
  // Filigrane : facture pas encore validée, ou document annulé
  const filigrane = doc.statut === "ANNULE" ? "ANNULÉ" : !proforma && doc.statut !== "VALIDE" ? "BROUILLON" : "";
  const remiseVisible = doc.lignes.some((l) => l.remise_pct > 0);
  // Adresse de la boutique (la ville n'est ajoutée que si l'adresse ne la contient pas déjà)
  const adresseBoutique = boutique.ville && !(boutique.adresse || "").toLowerCase().includes(boutique.ville.toLowerCase())
    ? [boutique.adresse, boutique.ville].filter(Boolean).join(", ")
    : boutique.adresse || "";

  return (
    <div className="fond-impression min-h-screen bg-gray-200 py-6 print:py-0">
      <style>{STYLE_IMPRESSION}</style>

      {/* Barre d'outils (masquée à l'impression) */}
      <div className="no-print mx-auto mb-4 flex max-w-[210mm] flex-wrap items-center justify-between gap-2 px-4">
        <Link to={`/gestion/documents/${doc.id}`} className="btn-outline btn-sm">← Retour au document</Link>
        <button type="button" className="btn-primary" onClick={() => window.print()}>🖨 Imprimer / Enregistrer en PDF</button>
      </div>

      {/* Feuille A4 (défilement horizontal possible sur téléphone) */}
      <div className="overflow-x-auto print:overflow-visible">
        <article className="feuille-a4 relative mx-auto bg-white text-[12px] leading-snug text-gray-900 shadow-xl">
          {filigrane && (
            <div className="filigrane pointer-events-none inset-0 z-0 flex overflow-hidden items-center justify-center" aria-hidden="true">
              <span className={`-rotate-[30deg] select-none text-[110px] font-black tracking-widest ${filigrane === "ANNULÉ" ? "text-red-500/15" : "text-gray-400/20"}`}>{filigrane}</span>
            </div>
          )}

          <div className="relative z-10">
            {/* En-tête : boutique à gauche, titre du document à droite */}
            <header className="flex items-start justify-between gap-6 border-b-2 border-primary pb-4">
              <div className="flex items-start gap-3">
                {boutique.logo_url && <img src={boutique.logo_url} alt="" className="h-16 w-16 object-contain" />}
                <div>
                  <p className="text-lg font-extrabold text-primary">{boutique.nom}</p>
                  {boutique.slogan && <p className="italic text-gray-600">{boutique.slogan}</p>}
                  {adresseBoutique && <p>{adresseBoutique}</p>}
                  {boutique.telephone && <p>Tél. : {boutique.telephone}</p>}
                  {boutique.email && <p>E-mail : {boutique.email}</p>}
                  <p className="text-gray-600">
                    {[boutique.ifu && `IFU : ${boutique.ifu}`, boutique.rccm && `RCCM : ${boutique.rccm}`].filter(Boolean).join(" · ")}
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-black tracking-wide">{proforma ? "FACTURE PROFORMA" : "FACTURE"}</p>
                <p className="mt-1 text-sm font-bold">N° {doc.numero || "— (brouillon)"}</p>
                <p>Date : {date(doc.date)}</p>
                {doc.date_echeance && <p>{proforma ? "Valable jusqu'au" : "Échéance"} : {date(doc.date_echeance)}</p>}
              </div>
            </header>

            {/* Client (coordonnées figées au moment de la facture) et objet */}
            <section className="mt-5 flex justify-between gap-6">
              <div className="flex-1">
                {doc.objet && <><p className="text-[10px] font-bold uppercase text-gray-500">Objet</p><p className="font-semibold">{doc.objet}</p></>}
                {doc.proforma_origine && <p className="mt-1 text-gray-600">Réf. proforma : {doc.proforma_origine.numero}</p>}
                {doc.commande_origine && <p className="mt-1 text-gray-600">Réf. commande : {doc.commande_origine.numero}</p>}
                {doc.dossier_origine && <p className="mt-1 text-gray-600">Réf. dossier SAV : {doc.dossier_origine.numero}</p>}
              </div>
              <div className="w-[80mm] rounded-lg border border-gray-300 p-3">
                <p className="text-[10px] font-bold uppercase text-gray-500">Client</p>
                <p className="text-sm font-bold">{doc.client?.nom}</p>
                {doc.client?.adresse && <p>{doc.client.adresse}</p>}
                {doc.client?.telephone && <p>Tél. : {doc.client.telephone}</p>}
                {doc.client?.email && <p>{doc.client.email}</p>}
                {doc.client?.ifu && <p>IFU : {doc.client.ifu}</p>}
              </div>
            </section>

            {/* Tableau des lignes (prix unitaires HT) */}
            <table className="mt-5 w-full border-collapse">
              <thead>
                <tr className="bg-primary text-left text-white">
                  <th className="px-2 py-1.5 font-semibold">#</th>
                  <th className="px-2 py-1.5 font-semibold">Désignation</th>
                  <th className="px-2 py-1.5 text-right font-semibold">Qté</th>
                  <th className="px-2 py-1.5 text-right font-semibold">P.U. HT</th>
                  {remiseVisible && <th className="px-2 py-1.5 text-right font-semibold">Remise</th>}
                  <th className="px-2 py-1.5 text-right font-semibold">TVA</th>
                  <th className="px-2 py-1.5 text-right font-semibold">Montant HT</th>
                </tr>
              </thead>
              <tbody>
                {doc.lignes.map((l, i) => (
                  <tr key={i} className="border-b border-gray-200 even:bg-gray-50">
                    <td className="px-2 py-1.5 align-top text-gray-500">{i + 1}</td>
                    <td className="px-2 py-1.5 align-top">
                      <span className="font-medium">{l.designation}</span>
                      {l.reference && <span className="block text-[10px] text-gray-500">Réf. {l.reference}</span>}
                    </td>
                    <td className="px-2 py-1.5 text-right align-top">{l.quantite}</td>
                    <td className="whitespace-nowrap px-2 py-1.5 text-right align-top">{montant(l.prix_unitaire_ht)}</td>
                    {remiseVisible && <td className="px-2 py-1.5 text-right align-top">{l.remise_pct ? `${l.remise_pct} %` : ""}</td>}
                    <td className="px-2 py-1.5 text-right align-top">{l.taux_tva} %</td>
                    <td className="whitespace-nowrap px-2 py-1.5 text-right align-top font-semibold">{montant(l.montant_ht)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Totaux et paiement */}
            <section className="mt-4 flex justify-end" style={{ breakInside: "avoid" }}>
              <table className="w-[80mm]">
                <tbody>
                  <tr><td className="px-2 py-1">Total HT</td><td className="px-2 py-1 text-right font-semibold">{prix(doc.total_ht, devise)}</td></tr>
                  <tr><td className="px-2 py-1">TVA</td><td className="px-2 py-1 text-right font-semibold">{prix(doc.total_tva, devise)}</td></tr>
                  <tr className="bg-primary text-white"><td className="px-2 py-1.5 font-bold">Total TTC</td><td className="px-2 py-1.5 text-right text-sm font-extrabold">{prix(doc.total_ttc, devise)}</td></tr>
                  {!proforma && doc.total_regle > 0 && (
                    <>
                      <tr><td className="px-2 py-1">Déjà réglé</td><td className="px-2 py-1 text-right">{prix(doc.total_regle, devise)}</td></tr>
                      <tr><td className="px-2 py-1 font-bold">Reste à payer</td><td className="px-2 py-1 text-right font-bold">{prix(doc.reste_a_payer, devise)}</td></tr>
                    </>
                  )}
                </tbody>
              </table>
            </section>

            {/* Montant en toutes lettres */}
            <p className="mt-4" style={{ breakInside: "avoid" }}>
              {proforma ? "Arrêtée la présente facture proforma" : "Arrêtée la présente facture"} à la somme de : <b>{doc.total_en_lettres}</b> TTC.
            </p>

            {doc.notes && (
              <div className="mt-4 whitespace-pre-line rounded-lg bg-gray-50 p-3" style={{ breakInside: "avoid" }}>
                <p className="text-[10px] font-bold uppercase text-gray-500">Notes</p>
                {doc.notes}
              </div>
            )}

            {/* Zones de signature */}
            <section className="mt-8 grid grid-cols-2 gap-10" style={{ breakInside: "avoid" }}>
              <div>
                <p className="font-semibold">Le client</p>
                <p className="text-[10px] text-gray-500">{proforma ? "Bon pour accord (date et signature)" : "Signature"}</p>
                <div className="mt-2 h-20 border-b border-dashed border-gray-400" />
              </div>
              <div>
                <p className="font-semibold">Pour {boutique.nom}</p>
                <p className="text-[10px] text-gray-500">Cachet et signature</p>
                <div className="mt-2 h-20 border-b border-dashed border-gray-400" />
              </div>
            </section>

            {/* Pied de page : conditions de la boutique */}
            {boutique.conditions_facture && (
              <footer className="mt-8 whitespace-pre-line border-t border-gray-200 pt-2 text-center text-[10px] text-gray-500">
                {boutique.conditions_facture}
              </footer>
            )}
          </div>
        </article>
      </div>
    </div>
  );
}
