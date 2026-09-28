import { useCallback, useEffect, useRef, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { date, dateHeure, prix } from "@/lib/format";
import { STATUTS_SAV } from "@/lib/statuts";
import Badge from "@/components/Badge";
import BarreEtapes from "./_composants/BarreEtapes";

// Étapes affichées dans la barre de progression (dans l'ordre de l'API)
const ETAPES = ["Reçu", "Diagnostic", "Réparation", "Prêt", "Restitué"];

// SUIVI DE RÉPARATION (/b/:slug/suivi-reparation) : le client saisit le n° de
// dossier (bon de dépôt) et son téléphone OU le code de suivi imprimé sur le bon.
// ?numero=&code= dans l'adresse (QR code du bon de dépôt) pré-remplit et lance la recherche.
export default function SuiviReparation() {
  const { boutique } = useOutletContext();
  const [params, setParams] = useSearchParams();

  // Champs du formulaire, pré-remplis depuis l'adresse
  const [numero, setNumero] = useState(params.get("numero") || "");
  const [secret, setSecret] = useState(params.get("code") || params.get("telephone") || "");
  // Résultat : le dossier trouvé, le message d'erreur, la recherche en cours
  const [dossier, setDossier] = useState(null);
  const [erreur, setErreur] = useState("");
  const [recherche, setRecherche] = useState(false);

  // Appel à l'API de suivi
  const chercher = useCallback(async (num, sec) => {
    setErreur("");
    setDossier(null);
    setRecherche(true);
    try {
      const { data } = await apiClient.get(`/public/b/${boutique.slug}/maintenance/suivi`, {
        params: { numero: num.trim(), secret: sec.trim() },
      });
      setDossier(data);
    } catch (err) {
      setErreur(messageErreur(err, "Aucun dossier ne correspond à ces informations"));
    } finally {
      setRecherche(false);
    }
  }, [boutique.slug]);

  // Recherche automatique si le numéro ET le code sont dans l'adresse (une seule fois)
  const dejaLance = useRef(false);
  useEffect(() => {
    if (dejaLance.current) return;
    dejaLance.current = true;
    const n = params.get("numero");
    const s = params.get("code") || params.get("telephone");
    if (n && s) chercher(n, s);
  }, [params, chercher]);

  // Validation du formulaire
  const valider = (e) => {
    e.preventDefault();
    setParams({ numero: numero.trim(), code: secret.trim() }, { replace: true });
    chercher(numero, secret);
  };

  const horsParcours = dossier && dossier.etape === 0; // ex. irréparable

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold">🔧 Suivre ma réparation</h1>
        <p className="text-gray-500">Les informations figurent sur le bon de dépôt remis en boutique.</p>
      </div>

      {/* ---------- Formulaire de recherche ---------- */}
      <form onSubmit={valider} className="card grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <div>
          <label className="label" htmlFor="numero">N° de dossier</label>
          <input id="numero" className="input uppercase" required placeholder="SAV-…" value={numero} onChange={(e) => setNumero(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="secret">Téléphone ou code de suivi</label>
          <input id="secret" className="input" required value={secret} onChange={(e) => setSecret(e.target.value)} />
        </div>
        <button type="submit" className="btn-boutique" disabled={recherche}>{recherche ? "Recherche…" : "Suivre"}</button>
      </form>

      {erreur && <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">⚠️ {erreur}</p>}

      {/* ---------- Résultat ---------- */}
      {dossier && (
        <div className="space-y-4">
          {/* En-tête : appareil, numéro, statut, progression */}
          <div className="card space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-sm text-gray-500">Dossier <span className="font-mono font-semibold">{dossier.numero}</span></p>
                <p className="text-xl font-extrabold">📱 {[dossier.marque, dossier.modele].filter(Boolean).join(" ")}</p>
              </div>
              <Badge table={STATUTS_SAV} statut={dossier.statut} className="text-sm" />
            </div>

            {horsParcours ? (
              <p className="rounded-xl bg-red-50 p-3 text-sm font-semibold text-red-700">
                {dossier.statut_libelle || "Réparation impossible"} : la boutique vous contactera pour la restitution de votre appareil.
              </p>
            ) : (
              <BarreEtapes etapes={ETAPES} etape={dossier.etape} />
            )}

            {/* Dates clés et garantie */}
            <dl className="grid grid-cols-2 gap-3 border-t border-gray-100 pt-4 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-gray-500">Déposé le</dt>
                <dd className="font-semibold">{date(dossier.date_depot)}</dd>
              </div>
              {dossier.date_restitution ? (
                <div>
                  <dt className="text-gray-500">Restitué le</dt>
                  <dd className="font-semibold">{date(dossier.date_restitution)}</dd>
                </div>
              ) : (
                <div>
                  <dt className="text-gray-500">Date prévue</dt>
                  <dd className="font-semibold">{dossier.date_prevue ? date(dossier.date_prevue) : "À préciser"}</dd>
                </div>
              )}
              {dossier.sous_garantie && (
                <div>
                  <dt className="text-gray-500">Garantie</dt>
                  <dd className="font-semibold text-green-700">🛡️ Sous garantie</dd>
                </div>
              )}
            </dl>
          </div>

          {/* Devis : montant et réponse du client */}
          {dossier.devis_montant > 0 && (
            <div className="card flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm text-gray-500">Devis de réparation</p>
                <p className="text-xl font-extrabold text-accent">{prix(dossier.devis_montant, boutique.devise)}</p>
              </div>
              {dossier.devis_accepte === true && <span className="badge bg-green-100 text-green-800">✓ Accepté</span>}
              {dossier.devis_accepte === false && <span className="badge bg-red-100 text-red-700">✕ Refusé</span>}
              {dossier.devis_accepte == null && (
                <span className="badge bg-amber-100 text-amber-800">En attente de votre accord</span>
              )}
              {dossier.devis_accepte == null && (
                <p className="w-full text-xs text-gray-500">Pour accepter ou refuser le devis, contactez la boutique{boutique.telephone ? ` au ${boutique.telephone}` : ""}.</p>
              )}
            </div>
          )}

          {/* Diagnostic du technicien */}
          {dossier.diagnostic && (
            <div className="card">
              <h2 className="mb-1 font-bold">Diagnostic</h2>
              <p className="whitespace-pre-line text-sm text-gray-700">{dossier.diagnostic}</p>
            </div>
          )}

          {/* Historique avec les commentaires de l'atelier (le plus récent en haut) */}
          {dossier.historique?.length > 0 && (
            <div className="card">
              <h2 className="mb-3 font-bold">Historique</h2>
              <ol className="space-y-3 border-l-2 border-gray-200 pl-4">
                {[...dossier.historique].reverse().map((h, i) => (
                  <li key={`${h.date}-${i}`} className="relative">
                    <span className={`absolute -left-[23px] top-1 h-3 w-3 rounded-full ${i === 0 ? "bg-boutique" : "bg-gray-300"}`} />
                    <p className="text-sm font-semibold">{h.statut_libelle || STATUTS_SAV[h.statut]?.libelle || h.statut}</p>
                    <p className="text-xs text-gray-500">{dateHeure(h.date)}</p>
                    {h.commentaire && <p className="mt-1 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-700">{h.commentaire}</p>}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
