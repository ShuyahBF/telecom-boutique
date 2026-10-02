import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/components/Toast";
import { apiClient, messageErreur } from "@/lib/api";
import { formatDecompte, heureLocale, signalerChangementMaintenance, useEtatMaintenance } from "@/lib/maintenancePlateforme";

// ---------------------------------------------------------------------------
// Surveillance de la maintenance de la plateforme, montée une seule fois dans
// App.jsx pour TOUT utilisateur connecté (rien pour les visiteurs du portail).
//
// Personnel des boutiques :
//   - annonce      : modale (message + décompte) qu'on peut fermer ; fermée, un
//                    bandeau rouge reste affiché avec le décompte ;
//   - verrouillage : écran entièrement verrouillé (ni Échap, ni clic dehors,
//                    ni tabulation vers la page), message + décompte mm:ss ;
//   - échéance     : déconnexion forcée et retour à la page de connexion.
// Super-administrateur (jamais déconnecté) : bandeau de suivi avec « Annuler »
// avant l'échéance, puis « Maintenance en cours — connexions bloquées » avec
// « Réactiver les connexions ».
// ---------------------------------------------------------------------------
export default function SurveillanceMaintenance() {
  const { user } = useAuth();
  const suivi = useEtatMaintenance(!!user);
  if (!user || !suivi.etat || suivi.phase === "aucune") return null;
  return user.role === "super_admin" ? <BandeauSuperAdmin {...suivi} /> : <AlertePersonnel {...suivi} />;
}

// ---------------------------------------------------------------------------
// Personnel : modale, bandeau, verrouillage puis déconnexion forcée
// ---------------------------------------------------------------------------
function AlertePersonnel({ etat, phase, secondes }) {
  const { deconnexion } = useAuth();
  const navigate = useNavigate();
  // Modale fermée pour CETTE annonce (une nouvelle annonce la rouvre)
  const [fermeePour, setFermeePour] = useState(null);
  const deconnecte = useRef(false);

  const echeanceAtteinte = phase === "maintenance" || secondes <= 0;
  useEffect(() => {
    if (!echeanceAtteinte || deconnecte.current) return;
    deconnecte.current = true;
    (async () => {
      await deconnexion(); // efface la session (cookie) et l'utilisateur courant
      navigate("/connexion", { replace: true, state: { maintenance: true } });
    })();
  }, [echeanceAtteinte, deconnexion, navigate]);

  if (phase === "verrouillage" || echeanceAtteinte) {
    return <EcranVerrouille etat={etat} secondes={secondes} deconnexionEnCours={echeanceAtteinte} />;
  }
  if (fermeePour !== etat.annonce_le) {
    return (
      <div className="no-print fixed inset-0 z-[110] flex items-center justify-center bg-black/50 p-4"
        onClick={() => setFermeePour(etat.annonce_le)}>
        <div role="alertdialog" aria-modal="true" aria-labelledby="maintenance-titre"
          className="w-full max-w-md animate-slide-up rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
          <div className="mb-3 flex items-start justify-between gap-4">
            <h2 id="maintenance-titre" className="text-lg font-bold text-red-700">⚠️ Déconnexion programmée</h2>
            <button type="button" onClick={() => setFermeePour(etat.annonce_le)} aria-label="Fermer"
              className="rounded-full p-1 text-gray-500 hover:bg-gray-100">✕</button>
          </div>
          <p className="whitespace-pre-line text-gray-800">{etat.message}</p>
          <Decompte secondes={secondes} />
          <p className="text-sm text-gray-600">
            Enregistrez votre travail en cours. L'écran sera verrouillé à {heureLocale(etat.debut_verrouillage)},
            puis vous serez déconnecté à {heureLocale(etat.echeance)}. Vous pourrez vous reconnecter quand
            l'administrateur aura rétabli l'accès.
          </p>
          <button type="button" className="btn-primary mt-4 w-full" onClick={() => setFermeePour(etat.annonce_le)}>
            J'ai compris
          </button>
        </div>
      </div>
    );
  }
  // Modale fermée : bandeau rouge persistant
  return (
    <div role="status" className="no-print fixed inset-x-0 bottom-0 z-[90] bg-red-600 px-4 py-2 text-sm text-white shadow-lg">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-center gap-x-3 gap-y-1 text-center">
        <span className="font-semibold">⚠️ Déconnexion de tous les utilisateurs dans <span className="font-mono">{formatDecompte(secondes)}</span></span>
        <span className="truncate opacity-90">{etat.message}</span>
        <button type="button" className="underline" onClick={() => setFermeePour(null)}>Revoir le message</button>
      </div>
    </div>
  );
}

function Decompte({ secondes, clair = false }) {
  return (
    <div className={`my-4 rounded-xl p-3 text-center ${clair ? "bg-white/10" : "bg-red-50"}`}>
      <p className={`text-xs font-semibold uppercase tracking-wider ${clair ? "text-red-200" : "text-red-700"}`}>Déconnexion forcée dans</p>
      <p className={`font-mono text-4xl font-extrabold tabular-nums ${clair ? "text-white" : "text-red-700"}`} aria-live="off">
        {formatDecompte(secondes)}
      </p>
    </div>
  );
}

/** Écran verrouillé, impossible à fermer : la page en dessous est rendue inerte. */
function EcranVerrouille({ etat, secondes, deconnexionEnCours }) {
  useEffect(() => {
    const racine = document.getElementById("root");
    racine?.setAttribute("inert", "");
    const debordement = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Échap n'a aucun effet (ni sur cet écran, ni sur une fenêtre ouverte dessous)
    const bloquer = (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); } };
    window.addEventListener("keydown", bloquer, true);
    return () => {
      racine?.removeAttribute("inert");
      document.body.style.overflow = debordement;
      window.removeEventListener("keydown", bloquer, true);
    };
  }, []);

  return createPortal(
    <div role="alertdialog" aria-modal="true" aria-labelledby="verrou-titre"
      className="no-print fixed inset-0 z-[1000] flex items-center justify-center bg-ink/95 p-4 text-white backdrop-blur-sm">
      <div className="w-full max-w-lg text-center">
        <p className="text-5xl" aria-hidden="true">🔒</p>
        <h2 id="verrou-titre" className="mt-3 text-2xl font-extrabold">Plateforme en cours de maintenance</h2>
        <p className="mt-4 whitespace-pre-line text-lg text-gray-100">{etat.message}</p>
        {deconnexionEnCours ? (
          <p className="mt-6 text-lg font-semibold text-red-200">Déconnexion en cours…</p>
        ) : (
          <Decompte secondes={secondes} clair />
        )}
        <p className="text-sm text-gray-300">
          Votre session sera fermée à {heureLocale(etat.echeance)}. Vous pourrez vous reconnecter dès que
          l'administrateur aura rétabli l'accès à la plateforme.
        </p>
      </div>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// Super-administrateur : suivi, annulation et réactivation
// ---------------------------------------------------------------------------
function BandeauSuperAdmin({ etat, phase, secondes }) {
  const toast = useToast();
  const [envoi, setEnvoi] = useState(false);

  async function agir(action, succes) {
    setEnvoi(true);
    try {
      await apiClient.post(`/plateforme/deconnexion-generale/${action}`);
      toast.succes(succes);
      signalerChangementMaintenance();
    } catch (err) {
      toast.erreur(messageErreur(err, "Action impossible"));
      signalerChangementMaintenance();
    } finally {
      setEnvoi(false);
    }
  }

  const enMaintenance = phase === "maintenance";
  return (
    <div role="status" className={`no-print fixed inset-x-0 bottom-0 z-[90] px-4 py-2 text-sm text-white shadow-lg ${enMaintenance ? "bg-red-700" : "bg-amber-600"}`}>
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-center gap-x-4 gap-y-2 text-center">
        {enMaintenance ? (
          <span className="font-semibold">🔒 Maintenance en cours — connexions bloquées pour tous les utilisateurs (sauf administrateurs)</span>
        ) : (
          <span className="font-semibold">
            ⏳ Déconnexion générale programmée : {phase === "verrouillage" ? "écrans verrouillés, " : ""}
            déconnexion forcée dans <span className="font-mono">{formatDecompte(secondes)}</span> ({heureLocale(etat.echeance)})
          </span>
        )}
        <Link to="/plateforme/parametres" className="underline">Détails</Link>
        {enMaintenance ? (
          <button type="button" disabled={envoi} className="btn btn-sm bg-white text-red-700 hover:bg-red-50"
            onClick={() => agir("reactiver", "Connexions réactivées : chacun peut se reconnecter.")}>
            {envoi ? "…" : "Réactiver les connexions"}
          </button>
        ) : (
          <button type="button" disabled={envoi} className="btn btn-sm border border-white/60 text-white hover:bg-white/10"
            onClick={() => window.confirm("Annuler la déconnexion programmée ? Personne ne sera déconnecté.")
              && agir("annuler", "Déconnexion annulée.")}>
            {envoi ? "…" : "Annuler la déconnexion"}
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Avis affiché sur la page de connexion et sur « Mot de passe oublié »
// ---------------------------------------------------------------------------
export function AvisMaintenance() {
  const { etat, phase, secondes } = useEtatMaintenance(true);
  if (!etat || phase === "aucune") return null;
  if (phase === "maintenance") {
    return (
      <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
        <p className="font-bold">🔒 Plateforme en maintenance</p>
        <p className="mt-1 whitespace-pre-line">{etat.message}</p>
        <p className="mt-1 text-xs">Les connexions sont suspendues jusqu'à ce que l'administrateur rétablisse l'accès. Réessayez plus tard.</p>
      </div>
    );
  }
  return (
    <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
      <p className="font-bold">⏳ Maintenance prévue dans <span className="font-mono">{formatDecompte(secondes)}</span></p>
      <p className="mt-1 whitespace-pre-line">{etat.message}</p>
    </div>
  );
}
