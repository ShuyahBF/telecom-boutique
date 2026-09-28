import { useEffect, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { prix } from "@/lib/format";

// Statuts « définitifs » : une fois atteints, on arrête d'interroger le serveur
const STATUTS_FINAUX = ["paye", "echec", "montant_incoherent"];
const INTERVALLE = 3000; // on redemande l'état toutes les 3 secondes
const DUREE_MAX = 2 * 60 * 1000; // pendant 2 minutes au maximum

// RETOUR DE PAIEMENT (/b/:slug/paiement?depot=..&commande=..) : page où
// PawaPay renvoie le client après le paiement Mobile Money. On interroge le
// serveur (qui vérifie lui-même auprès de PawaPay) jusqu'à un état définitif.
export default function RetourPaiement() {
  const { boutique } = useOutletContext();
  const [params] = useSearchParams();
  const depot = params.get("depot") || "";
  const numeroCommande = params.get("commande") || "";

  // Dernier état connu du paiement : { statut, montant, devise, commande_numero, api_message }
  const [paiement, setPaiement] = useState(null);
  const [erreur, setErreur] = useState("");
  // Vrai quand les 2 minutes sont écoulées sans réponse définitive
  const [delaiDepasse, setDelaiDepasse] = useState(false);

  // Interrogation répétée : GET /paiements/{depot}?refresh=true toutes les 3 s
  useEffect(() => {
    if (!depot) {
      setErreur("Lien de paiement incomplet.");
      return undefined;
    }
    let actif = true;
    let minuterie = null;
    const debut = Date.now();

    const interroger = async () => {
      try {
        const { data } = await apiClient.get(`/paiements/${encodeURIComponent(depot)}`, { params: { refresh: true } });
        if (!actif) return;
        setPaiement(data);
        if (STATUTS_FINAUX.includes(data.statut)) return; // état définitif : on s'arrête
      } catch (err) {
        if (!actif) return;
        // Paiement inconnu : inutile d'insister
        if (err?.response?.status === 404) {
          setErreur(messageErreur(err, "Paiement introuvable."));
          return;
        }
        // Autre erreur (réseau...) : on réessaie au prochain tour
      }
      if (Date.now() - debut >= DUREE_MAX) {
        setDelaiDepasse(true);
        return;
      }
      minuterie = setTimeout(interroger, INTERVALLE);
    };
    interroger();

    // Nettoyage quand on quitte la page : on arrête les interrogations
    return () => { actif = false; clearTimeout(minuterie); };
  }, [depot]);

  const numero = paiement?.commande_numero || numeroCommande;
  const lienSuivi = `/b/${boutique.slug}/suivi-commande?numero=${encodeURIComponent(numero)}`;
  const statut = paiement?.statut;

  // Choix de l'affichage selon l'état du paiement
  let icone = "⏳";
  let titre = "En attente de confirmation…";
  let texte = "Validez le paiement sur votre téléphone si ce n'est pas déjà fait. Cette page se met à jour toute seule.";
  let couleur = "bg-amber-100";
  if (erreur) {
    icone = "⚠️"; titre = "Paiement introuvable"; texte = erreur; couleur = "bg-gray-100";
  } else if (statut === "paye") {
    icone = "✅"; titre = "Paiement confirmé"; couleur = "bg-green-100";
    texte = "Merci ! Votre paiement a bien été reçu. La boutique prépare votre commande.";
  } else if (statut === "echec") {
    icone = "❌"; titre = "Paiement échoué"; couleur = "bg-red-100";
    texte = "Le paiement n'a pas abouti. Pas d'inquiétude : votre commande reste enregistrée et vous pourrez la payer au retrait ou à la livraison.";
  } else if (statut === "montant_incoherent") {
    icone = "⚠️"; titre = "Paiement à vérifier"; couleur = "bg-amber-100";
    texte = "Le montant reçu ne correspond pas à celui de la commande. Contactez la boutique pour régulariser.";
  } else if (delaiDepasse) {
    texte = "La confirmation prend plus de temps que prévu. Elle sera enregistrée automatiquement dès réception : vous pouvez suivre votre commande pour vérifier.";
  }

  return (
    <div className="mx-auto max-w-lg">
      <div className="card text-center">
        {/* Grande icône d'état (tourne pendant l'attente) */}
        <div className={`mx-auto flex h-20 w-20 items-center justify-center rounded-full text-4xl ${couleur}`}>
          <span className={!statut || (!STATUTS_FINAUX.includes(statut) && !erreur && !delaiDepasse) ? "animate-pulse" : ""}>{icone}</span>
        </div>
        <h1 className="mt-4 text-2xl font-extrabold">{titre}</h1>
        <p className="mt-2 text-gray-600">{texte}</p>

        {/* Motif de l'échec renvoyé par l'opérateur */}
        {statut === "echec" && paiement?.api_message && (
          <p className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">Motif : {paiement.api_message}</p>
        )}

        {/* Coordonnées de la boutique en cas de problème de montant */}
        {statut === "montant_incoherent" && (boutique.telephone || boutique.email) && (
          <p className="mt-3 rounded-xl bg-gray-50 p-3 text-sm text-gray-700">
            📞 {[boutique.telephone, boutique.email].filter(Boolean).join(" · ")}
          </p>
        )}

        {/* Rappel du numéro de commande et du montant */}
        {numero && (
          <div className="mt-5 rounded-2xl bg-gray-50 p-4 text-sm">
            <p className="text-gray-500">Commande</p>
            <p className="font-mono text-2xl font-extrabold text-boutique">{numero}</p>
            {paiement?.montant != null && <p className="mt-1 text-gray-600">Montant : <b>{prix(paiement.montant, boutique.devise)}</b></p>}
          </div>
        )}

        <div className="mt-6 flex flex-col gap-2">
          {numero && <Link to={lienSuivi} className="btn-boutique py-3">📦 Suivre ma commande</Link>}
          <Link to={`/b/${boutique.slug}`} className="btn-outline">Retour au catalogue</Link>
        </div>
        {numero && <p className="mt-3 text-xs text-gray-500">Pour le suivi, munissez-vous du téléphone indiqué lors de la commande.</p>}
      </div>
    </div>
  );
}
