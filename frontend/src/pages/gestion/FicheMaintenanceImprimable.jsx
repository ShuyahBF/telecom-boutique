import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, montant, prix } from "@/lib/format";
import { baseApi, ETATS, materiel, STATUTS } from "@/lib/maintenanceEquipements";
import Chargement from "@/components/Chargement";
import { LogoAdlyn } from "@/components/Marque";

// Coordonnées affichées sur les documents de la plateforme (mêmes que les pages légales)
const EDITEUR = { nom: "SAWALI SMART SYSTEMS", email: "contact@sawalismartsystems.com", telephone: "+226 25 65 81 65" };

// Une ligne « libellé : valeur »
function Ligne({ label, children }) {
  return (
    <div className="flex gap-2 border-b border-dotted border-gray-300 py-1">
      <span className="w-40 shrink-0 text-gray-500">{label}</span>
      <span className="flex-1 whitespace-pre-line font-medium">{children || "—"}</span>
    </div>
  );
}

// En-tête : la boutique (espace boutique) ou adLyn (espace plateforme)
function EnTete({ espace, boutique, droite }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b-2 border-ink pb-3">
      {espace === "plateforme" ? (
        <div>
          <LogoAdlyn className="h-8" />
          <p className="mt-1">{EDITEUR.nom}</p>
          <p>{EDITEUR.email} · {EDITEUR.telephone}</p>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          {boutique.logo_url && <img src={boutique.logo_url} alt="" className="h-12 w-12 object-contain" />}
          <div>
            <p className="text-base font-extrabold">{boutique.nom}</p>
            {(boutique.adresse || boutique.ville) && <p>{[boutique.adresse, boutique.ville].filter(Boolean).join(", ")}</p>}
            {boutique.telephone && <p>Tél. {boutique.telephone}</p>}
          </div>
        </div>
      )}
      <div className="text-right text-gray-500">{droite}</div>
    </div>
  );
}

// Documents imprimables d'une fiche de « Maintenance des équipements » (page pleine, sans menu) :
//   ?doc=bon     -> bon de dépôt (ou de restitution si la date de sortie est portée) ;
//   ?doc=facture -> facture adLyn (espace plateforme ; côté boutique, la facture est dans
//                   « Factures & proformas »).
export default function FicheMaintenanceImprimable({ espace = "boutique" }) {
  const { id } = useParams();
  const [params] = useSearchParams();
  const doc = params.get("doc") === "facture" ? "facture" : "bon";
  const { boutique } = useAuth();
  const [fiche, setFiche] = useState(null);
  const [erreur, setErreur] = useState("");

  useEffect(() => {
    apiClient.get(`${baseApi(espace)}/${id}`)
      .then(({ data }) => setFiche(data))
      .catch((err) => setErreur(messageErreur(err, "Fiche introuvable")));
  }, [espace, id]);

  // Titre de l'onglet (utilisé aussi comme nom du fichier si on « imprime en PDF »)
  const facture = doc === "facture" ? fiche?.facture : null;
  const titre = !fiche ? "" : facture ? `Facture ${facture.numero}` : `${fiche.date_sortie ? "Bon de restitution" : "Bon de dépôt"} ${fiche.numero}`;
  useEffect(() => { if (titre) document.title = titre; }, [titre]);

  if (erreur) return <p className="p-10 text-center text-red-600">{erreur}</p>;
  if (!fiche || (espace === "boutique" && !boutique)) return <Chargement plein />;
  if (doc === "facture" && !facture) return <p className="p-10 text-center text-gray-600">Cette fiche n'a pas encore de facture.</p>;
  const devise = espace === "boutique" ? (boutique?.devise || "FCFA") : "FCFA";

  return (
    <div className="min-h-screen bg-gray-100 py-6 print:bg-white print:py-0">
      <style>{"@page { size: A4; margin: 12mm } @media print { html, body { background: #fff } }"}</style>

      {/* Barre d'actions (non imprimée) */}
      <div className="no-print mx-auto mb-4 flex max-w-[210mm] items-center justify-between gap-2 px-4">
        <button type="button" className="btn-outline btn-sm" onClick={() => window.close()}>✕ Fermer</button>
        <button type="button" className="btn-primary" onClick={() => window.print()}>🖨️ Imprimer / PDF</button>
      </div>

      <div className="mx-auto w-full max-w-[210mm] bg-white p-8 text-[12px] leading-snug text-ink shadow-lg print:max-w-none print:p-0 print:shadow-none">
        {facture ? (
          <>
            {/* ---- Facture adLyn adressée à la boutique cliente ---- */}
            <EnTete espace={espace} boutique={boutique} droite={<>Date<br /><b className="text-ink">{date(facture.date)}</b></>} />
            <div className="my-4 flex flex-wrap items-start justify-between gap-4">
              <div>
                <h1 className="text-xl font-extrabold">FACTURE {facture.numero}</h1>
                <p className="text-gray-500">Maintenance — fiche {fiche.numero}</p>
              </div>
              <div className="min-w-[45%] rounded-lg border border-gray-300 p-3">
                <p className="text-[10px] font-semibold uppercase text-gray-500">Facturé à</p>
                <p className="font-bold">{facture.client.nom}</p>
                {facture.client.code_marchand && <p>ID boutique : {facture.client.code_marchand}</p>}
                {facture.client.adresse && <p>{facture.client.adresse}</p>}
                {facture.client.telephone && <p>Tél. {facture.client.telephone}</p>}
                {facture.client.ifu && <p>IFU : {facture.client.ifu}</p>}
                {facture.client.rccm && <p>RCCM : {facture.client.rccm}</p>}
              </div>
            </div>
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b-2 border-ink"><th className="py-1.5">Désignation</th><th className="py-1.5 text-right">Qté</th><th className="py-1.5 text-right">Prix unitaire</th><th className="py-1.5 text-right">Montant</th></tr>
              </thead>
              <tbody>
                {facture.lignes.map((l, i) => (
                  <tr key={i} className="border-b border-gray-200">
                    <td className="py-1.5">{l.designation}</td>
                    <td className="py-1.5 text-right">{l.quantite}</td>
                    <td className="py-1.5 text-right">{montant(l.prix_unitaire)}</td>
                    <td className="py-1.5 text-right">{montant(l.montant)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-right text-base font-extrabold">Total à payer : {prix(facture.montant, facture.devise)}</p>
            {fiche.lien_paiement?.paye && <p className="mt-1 text-right font-semibold text-emerald-700">Payé par Mobile Money le {date(fiche.lien_paiement.paye_le)}</p>}
            {fiche.lien_paiement && !fiche.lien_paiement.paye && (
              <p className="mt-3 text-gray-600">Paiement Mobile Money : <b className="break-all">{fiche.lien_paiement.url}</b></p>
            )}
          </>
        ) : (
          <>
            {/* ---- Bon de dépôt / de restitution ---- */}
            <EnTete espace={espace} boutique={boutique} droite={<>Reçu le<br /><b className="text-ink">{date(fiche.date_reception)}</b></>} />
            <h1 className="my-3 text-center text-base font-extrabold tracking-wide">
              {fiche.date_sortie ? "BON DE RESTITUTION" : "BON DE DÉPÔT"} — MAINTENANCE DES ÉQUIPEMENTS
            </h1>
            <div className="mb-3 rounded-lg border-2 border-ink p-2 text-center">
              <p className="text-[10px] font-semibold uppercase text-gray-500">N° de fiche</p>
              <p className="font-mono text-lg font-extrabold">{fiche.numero}</p>
            </div>
            <div className="mb-3">
              <Ligne label="Client">{fiche.client_nom}{fiche.client_telephone && ` — ${fiche.client_telephone}`}</Ligne>
              <Ligne label="Matériel">{materiel(fiche)}</Ligne>
              <Ligne label="N° de série">{fiche.numero_serie}</Ligne>
              <Ligne label="État à la réception">{ETATS[fiche.etat_materiel]?.[0]}</Ligne>
              <Ligne label="Motif">{fiche.motif}</Ligne>
              <Ligne label="Diagnostic">{fiche.diagnostic}</Ligne>
              <Ligne label="Remplacement de pièces">{fiche.remplacement_pieces ? `Oui — ${fiche.pieces || ""}` : "Non"}</Ligne>
              <Ligne label="Entrée en atelier">{fiche.date_entree ? date(fiche.date_entree) : ""}</Ligne>
              <Ligne label="Sortie">{fiche.date_sortie ? date(fiche.date_sortie) : ""}</Ligne>
              <Ligne label="Statut">{STATUTS[fiche.statut]?.[0]}</Ligne>
              <Ligne label="Équipe">{fiche.equipe}</Ligne>
              <Ligne label="Prix du diagnostic">{prix(fiche.prix_diagnostic, devise)}</Ligne>
              <Ligne label="Observations">{fiche.observations}</Ligne>
            </div>
            {/* Photos de l'équipement ou des pièces */}
            {(fiche.photos || []).length > 0 && (
              <div className="mb-4 flex flex-wrap gap-2">
                {fiche.photos.map((p) => <img key={p.id} src={p.url} alt="" className="h-28 w-28 rounded object-cover" />)}
              </div>
            )}
            <div className="mb-4 space-y-1 text-[10px] text-gray-600">
              <p>• Tout matériel non retiré dans un délai de <b>90 jours</b> après l'avis de fin de réparation pourra être considéré comme abandonné.</p>
              <p>• Pensez à sauvegarder vos données : une réparation peut entraîner leur perte.</p>
              <p>• Ce bon doit être présenté pour le retrait du matériel.</p>
            </div>
            <div className="grid grid-cols-2 gap-4 pt-4 text-center">
              <div><p className="mb-10 font-semibold">Signature du client</p><div className="border-t border-gray-400" /></div>
              <div><p className="mb-10 font-semibold">Signature du technicien</p><div className="border-t border-gray-400" /></div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
