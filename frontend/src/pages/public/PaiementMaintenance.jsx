import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { prix } from "@/lib/format";
import { LogoAdlyn } from "@/components/Marque";
import PoweredBySawali from "@/components/PoweredBySawali";

// Statuts « définitifs » d'un paiement : on arrête alors d'interroger le serveur
const STATUTS_FINAUX = ["paye", "echec", "montant_incoherent"];
const INTERVALLE = 3000; // état redemandé toutes les 3 secondes
const DUREE_MAX = 2 * 60 * 1000; // pendant 2 minutes au maximum

// LIEN DE PAIEMENT d'une fiche de « Maintenance des équipements »
// (/paiement/maintenance/:jeton), envoyé au client par WhatsApp ou copié :
//   1. résumé (émetteur, fiche, matériel, montant) et bouton « Payer par Mobile Money »,
//      qui ouvre la page sécurisée PawaPay (le site ne collecte jamais de code PIN) ;
//   2. au retour de PawaPay (?depot=...), l'état du paiement est suivi jusqu'à sa fin.
export default function PaiementMaintenance() {
  const { jeton } = useParams();
  const [params] = useSearchParams();
  const depot = params.get("depot") || "";
  const [lien, setLien] = useState(undefined); // undefined = chargement, null = lien invalide
  const [telephone, setTelephone] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState("");
  const [paiement, setPaiement] = useState(null);

  // Résumé de la fiche à payer
  useEffect(() => {
    document.title = "Paiement — adLyn";
    apiClient.get(`/public/maintenance-paiement/${encodeURIComponent(jeton)}`)
      .then(({ data }) => setLien(data)).catch(() => setLien(null));
  }, [jeton, paiement?.statut]);

  // Retour de PawaPay : interrogation répétée jusqu'à un état définitif
  useEffect(() => {
    if (!depot) return undefined;
    let actif = true;
    let minuterie = null;
    const debut = Date.now();
    const interroger = async () => {
      try {
        const { data } = await apiClient.get(`/paiements/${encodeURIComponent(depot)}`, { params: { refresh: true } });
        if (!actif) return;
        setPaiement(data);
        if (STATUTS_FINAUX.includes(data.statut)) return;
      } catch (err) {
        if (err?.response?.status === 404) return; // paiement inconnu : inutile d'insister
      }
      if (actif && Date.now() - debut < DUREE_MAX) minuterie = setTimeout(interroger, INTERVALLE);
    };
    interroger();
    return () => { actif = false; clearTimeout(minuterie); };
  }, [depot]);

  // Ouverture de la page de paiement PawaPay
  const payer = async (e) => {
    e.preventDefault();
    setErreur("");
    setEnvoi(true);
    try {
      const { data } = await apiClient.post(`/public/maintenance-paiement/${encodeURIComponent(jeton)}`, { telephone });
      window.location.href = data.url;
    } catch (err) {
      setErreur(messageErreur(err, "Paiement impossible pour le moment"));
      setEnvoi(false);
    }
  };

  const statut = paiement?.statut;
  return (
    <div className="fond-ondes flex min-h-screen flex-col items-center px-4 py-10">{/* fond « ondes » de la charte */}
      <Link to="/" aria-label="adLyn, accueil"><LogoAdlyn clair className="h-10" /></Link>
      <div className="mt-6 w-full max-w-md carte-acces">
        {lien === undefined && <p className="text-center text-gray-500">Chargement…</p>}
        {lien === null && (
          <div className="space-y-2 text-center">
            <h1 className="text-xl font-bold">Lien de paiement invalide</h1>
            <p className="text-sm text-gray-600">Ce lien n'existe pas ou a été remplacé. Demandez un nouveau lien à votre prestataire.</p>
          </div>
        )}
        {lien && (
          <div className="space-y-4">
            <div>
              <p className="text-sm text-gray-500">{lien.emetteur}</p>
              <h1 className="text-xl font-bold">Maintenance — fiche {lien.numero}</h1>
              <p className="text-sm text-gray-600">{lien.materiel}{lien.client_nom && ` · ${lien.client_nom}`}</p>
            </div>
            <p className="rounded-xl bg-gray-50 p-4 text-center text-2xl font-extrabold">{prix(lien.montant, lien.devise)}</p>

            {/* État du paiement au retour de PawaPay */}
            {depot && !lien.paye && (
              <p className={`rounded-lg p-3 text-sm ${statut === "echec" || statut === "montant_incoherent" ? "bg-red-50 text-red-800" : "bg-amber-50 text-amber-900"}`}>
                {statut === "echec" || statut === "montant_incoherent"
                  ? `❌ Le paiement n'a pas abouti${paiement?.api_message ? ` (${paiement.api_message})` : ""}. Vous pouvez réessayer.`
                  : "⏳ En attente de confirmation… Validez le paiement sur votre téléphone. Cette page se met à jour toute seule."}
              </p>
            )}

            {lien.paye ? (
              <p className="rounded-lg bg-emerald-50 p-3 text-center font-semibold text-emerald-800">✅ Paiement reçu. Merci !</p>
            ) : !lien.disponible ? (
              <p className="rounded-lg bg-gray-100 p-3 text-center text-sm text-gray-600">Le paiement en ligne est momentanément indisponible.</p>
            ) : (
              <form onSubmit={payer} className="space-y-3">
                <label className="block">
                  <span className="label">Numéro Mobile Money (facultatif)</span>
                  <input className="input" inputMode="tel" maxLength={30} placeholder="ex. 70 12 34 56" value={telephone} onChange={(e) => setTelephone(e.target.value)} />
                </label>
                {erreur && <p className="text-sm text-red-600">{erreur}</p>}
                <button className="btn-primary w-full" disabled={envoi}>{envoi ? "Ouverture…" : "Payer par Mobile Money"}</button>
                <p className="text-center text-xs text-gray-500">Orange Money, Moov Money… sur la page sécurisée de notre partenaire PawaPay.</p>
              </form>
            )}
          </div>
        )}
      </div>
      <PoweredBySawali className="mt-6" />
    </div>
  );
}
