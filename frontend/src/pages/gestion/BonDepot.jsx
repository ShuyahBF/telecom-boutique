import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, dateHeure, prix } from "@/lib/format";
import Chargement from "@/components/Chargement";
import QrCode from "@/components/QrCode";

// Une ligne « libellé : valeur » du bon
function Ligne({ label, children }) {
  return (
    <div className="flex gap-2 border-b border-dotted border-gray-300 py-1">
      <span className="w-28 shrink-0 text-gray-500">{label}</span>
      <span className="flex-1 font-medium">{children || "—"}</span>
    </div>
  );
}

// Bon de dépôt à imprimer (format A5) et à remettre au client.
// Page pleine, sans menu. IMPORTANT : le code de déverrouillage n'y figure JAMAIS.
export default function BonDepot() {
  const { id } = useParams();
  const { boutique } = useAuth();
  const [dossier, setDossier] = useState(null);
  const [erreur, setErreur] = useState("");

  // Chargement du dossier
  useEffect(() => {
    apiClient.get(`/maintenance/${id}`)
      .then(({ data }) => setDossier(data))
      .catch((err) => setErreur(messageErreur(err, "Dossier introuvable")));
  }, [id]);

  // Titre de l'onglet (utilisé aussi comme nom du fichier si on « imprime en PDF »)
  useEffect(() => {
    if (dossier) document.title = `Bon de dépôt ${dossier.numero}`;
  }, [dossier]);

  if (erreur) return <p className="p-10 text-center text-red-600">{erreur}</p>;
  if (!dossier || !boutique) return <Chargement plein />;

  // Adresse de suivi public (encodée dans le QR code)
  const lienSuivi = `${window.location.origin}/b/${boutique.slug}/suivi-reparation?numero=${encodeURIComponent(dossier.numero)}&code=${encodeURIComponent(dossier.code_suivi)}`;
  const lienCourt = `${window.location.host}/b/${boutique.slug}/suivi-reparation`;

  return (
    <div className="min-h-screen bg-gray-100 py-6 print:bg-white print:py-0">
      {/* Format de la page imprimée : A5, marges de 10 mm */}
      <style>{"@page { size: A5; margin: 10mm } @media print { html, body { background: #fff } }"}</style>

      {/* Barre d'actions (non imprimée) */}
      <div className="no-print mx-auto mb-4 flex max-w-[148mm] items-center justify-between gap-2 px-4">
        <button type="button" className="btn-outline btn-sm" onClick={() => window.close()}>✕ Fermer</button>
        <button type="button" className="btn-primary" onClick={() => window.print()}>🖨️ Imprimer le bon</button>
      </div>

      {/* Le bon lui-même : largeur A5 (148 mm) */}
      <div className="mx-auto w-full max-w-[148mm] bg-white p-6 text-[12px] leading-snug text-ink shadow-lg print:max-w-none print:p-0 print:shadow-none">
        {/* En-tête : identité de la boutique */}
        <div className="flex items-start justify-between gap-3 border-b-2 border-ink pb-3">
          <div className="flex items-center gap-3">
            {boutique.logo_url && <img src={boutique.logo_url} alt="" className="h-12 w-12 object-contain" />}
            <div>
              <p className="text-base font-extrabold">{boutique.nom}</p>
              {boutique.adresse && <p>{boutique.adresse}{boutique.ville && `, ${boutique.ville}`}</p>}
              {!boutique.adresse && boutique.ville && <p>{boutique.ville}</p>}
              {boutique.telephone && <p>Tél. {boutique.telephone}</p>}
            </div>
          </div>
          <p className="text-right text-gray-500">Déposé le<br /><b className="text-ink">{dateHeure(dossier.date_depot)}</b></p>
        </div>

        <h1 className="my-3 text-center text-base font-extrabold tracking-wide">BON DE DÉPÔT — MAINTENANCE</h1>

        {/* Numéro de dossier + code de suivi dans un cadre bien visible */}
        <div className="mb-3 grid grid-cols-2 rounded-lg border-2 border-ink text-center">
          <div className="border-r-2 border-ink p-2">
            <p className="text-[10px] font-semibold uppercase text-gray-500">N° de dossier</p>
            <p className="font-mono text-lg font-extrabold">{dossier.numero}</p>
          </div>
          <div className="p-2">
            <p className="text-[10px] font-semibold uppercase text-gray-500">Code de suivi</p>
            <p className="font-mono text-lg font-extrabold tracking-[0.25em]">{dossier.code_suivi}</p>
          </div>
        </div>

        {/* Client et appareil */}
        <div className="mb-3">
          <Ligne label="Client">{dossier.client?.nom}{dossier.client?.telephone && ` — ${dossier.client.telephone}`}</Ligne>
          <Ligne label="Appareil">{dossier.marque} {dossier.modele}{dossier.couleur && ` (${dossier.couleur})`}</Ligne>
          <Ligne label="IMEI">{dossier.imei && <span className="font-mono">{dossier.imei}</span>}</Ligne>
          <Ligne label="Accessoires">{dossier.accessoires_deposes}</Ligne>
          <Ligne label="État visuel">{dossier.etat_visuel}</Ligne>
          <Ligne label="Panne déclarée">{dossier.panne_declaree}</Ligne>
          <Ligne label="Retrait prévu">{dossier.date_prevue ? date(dossier.date_prevue) : "À confirmer"}</Ligne>
          <Ligne label="Acompte versé">{dossier.acompte ? prix(dossier.acompte, boutique.devise) : "Aucun"}</Ligne>
        </div>

        {/* QR code vers la page de suivi public */}
        <div className="mb-3 flex items-center gap-3 rounded-lg bg-gray-50 p-3 print:bg-white print:ring-1 print:ring-gray-300">
          <QrCode valeur={lienSuivi} taille={110} className="shrink-0" />
          <div>
            <p className="font-bold">Suivez votre réparation en scannant ce QR code</p>
            <p>ou sur <b className="break-all">{lienCourt}</b> avec votre n° de dossier et le code de suivi ci-dessus.</p>
          </div>
        </div>

        {/* Mentions légales du dépôt */}
        <div className="mb-4 space-y-1 text-[10px] text-gray-600">
          <p>• Tout appareil non retiré dans un délai de <b>90 jours</b> après l'avis de fin de réparation pourra être considéré comme abandonné.</p>
          <p>• La boutique n'est pas responsable des données (photos, contacts…) présentes dans l'appareil : pensez à les sauvegarder. Une réparation peut entraîner leur perte.</p>
          <p>• Ce bon doit être présenté pour le retrait de l'appareil.</p>
        </div>

        {/* Signatures */}
        <div className="grid grid-cols-2 gap-4 text-center">
          <div><p className="mb-10 font-semibold">Signature du client</p><div className="border-t border-gray-400" /></div>
          <div><p className="mb-10 font-semibold">Pour la boutique</p><div className="border-t border-gray-400" /></div>
        </div>
      </div>
    </div>
  );
}
