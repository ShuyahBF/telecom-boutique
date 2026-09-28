import { useCallback, useEffect, useRef, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure, prix } from "@/lib/format";
import { STATUTS_COMMANDE, STATUTS_PAIEMENT_COMMANDE } from "@/lib/statuts";
import Badge from "@/components/Badge";
import BarreEtapes from "./_composants/BarreEtapes";

// Étapes affichées dans la barre de progression (dans l'ordre de l'API)
const ETAPES = ["Reçue", "Confirmée", "Préparation", "Prête", "Livrée"];

// SUIVI DE COMMANDE (/b/:slug/suivi-commande) : le client saisit son n° de
// commande et son téléphone (les deux doivent correspondre) et voit où en est
// sa commande. ?numero=&telephone= dans l'adresse pré-remplit et lance la recherche.
export default function SuiviCommande() {
  const { boutique } = useOutletContext();
  const [params, setParams] = useSearchParams();

  // Champs du formulaire, pré-remplis depuis l'adresse
  const [numero, setNumero] = useState(params.get("numero") || "");
  const [telephone, setTelephone] = useState(params.get("telephone") || "");
  // Résultat : la commande trouvée, le message d'erreur, la recherche en cours
  const [commande, setCommande] = useState(null);
  const [erreur, setErreur] = useState("");
  const [recherche, setRecherche] = useState(false);

  // Appel à l'API de suivi
  const chercher = useCallback(async (num, tel) => {
    setErreur("");
    setCommande(null);
    setRecherche(true);
    try {
      const { data } = await apiClient.get(`/public/b/${boutique.slug}/commandes/suivi`, {
        params: { numero: num.trim(), telephone: tel.trim() },
      });
      setCommande(data);
    } catch (err) {
      setErreur(messageErreur(err, "Aucune commande ne correspond à ce numéro et ce téléphone"));
    } finally {
      setRecherche(false);
    }
  }, [boutique.slug]);

  // Recherche automatique si le numéro ET le téléphone sont dans l'adresse (une seule fois)
  const dejaLance = useRef(false);
  useEffect(() => {
    if (dejaLance.current) return;
    dejaLance.current = true;
    const n = params.get("numero");
    const t = params.get("telephone");
    if (n && t) chercher(n, t);
  }, [params, chercher]);

  // Validation du formulaire : on met aussi à jour l'adresse (pour un éventuel favori)
  const valider = (e) => {
    e.preventDefault();
    setParams({ numero: numero.trim(), telephone: telephone.trim() }, { replace: true });
    chercher(numero, telephone);
  };

  const annulee = commande?.statut === "ANNULEE";

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold">📦 Suivre ma commande</h1>
        <p className="text-gray-500">Saisissez le numéro reçu lors de la commande et le téléphone utilisé.</p>
      </div>

      {/* ---------- Formulaire de recherche ---------- */}
      <form onSubmit={valider} className="card grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <div>
          <label className="label" htmlFor="numero">N° de commande</label>
          <input id="numero" className="input uppercase" required placeholder="CMD-…" value={numero} onChange={(e) => setNumero(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="telephone">Téléphone</label>
          <input id="telephone" className="input" type="tel" inputMode="tel" required value={telephone} onChange={(e) => setTelephone(e.target.value)} />
        </div>
        <button type="submit" className="btn-boutique" disabled={recherche}>{recherche ? "Recherche…" : "Suivre"}</button>
      </form>

      {erreur && <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">⚠️ {erreur}</p>}

      {/* ---------- Résultat ---------- */}
      {commande && (
        <div className="space-y-4">
          {/* En-tête : numéro, date, statut */}
          <div className="card space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-sm text-gray-500">Commande du {dateHeure(commande.date)}</p>
                <p className="font-mono text-xl font-extrabold">{commande.numero}</p>
              </div>
              <Badge table={STATUTS_COMMANDE} statut={commande.statut} className="text-sm" />
            </div>

            {/* Barre de progression (ou bandeau rouge si annulée) */}
            {annulee ? (
              <p className="rounded-xl bg-red-50 p-3 text-sm font-semibold text-red-700">
                Cette commande a été annulée. Pour toute question, contactez la boutique{boutique.telephone ? ` au ${boutique.telephone}` : ""}.
              </p>
            ) : (
              <BarreEtapes etapes={ETAPES} etape={commande.etape} />
            )}

            {/* Réception et paiement */}
            <div className="grid gap-3 border-t border-gray-100 pt-4 text-sm sm:grid-cols-2">
              <div>
                <p className="text-gray-500">Réception</p>
                <p className="font-semibold">{commande.mode_livraison === "LIVRAISON" ? "🛵 Livraison" : "🏪 Retrait en boutique"}</p>
              </div>
              <div>
                <p className="text-gray-500">Paiement</p>
                <Badge table={STATUTS_PAIEMENT_COMMANDE} statut={commande.paiement?.statut} />
              </div>
            </div>
          </div>

          {/* Articles commandés */}
          <div className="card">
            <h2 className="mb-2 font-bold">Articles</h2>
            <ul className="divide-y divide-gray-100 text-sm">
              {commande.lignes.map((l, i) => (
                <li key={`${l.produit_id}-${i}`} className="flex justify-between gap-3 py-2">
                  <span><b>{l.quantite} ×</b> {l.nom}</span>
                  <span className="shrink-0 font-semibold">{prix(l.montant, boutique.devise)}</span>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex items-baseline justify-between border-t border-gray-200 pt-3">
              <span className="font-bold">Total</span>
              <span className="text-xl font-extrabold text-accent">{prix(commande.total, boutique.devise)}</span>
            </div>
          </div>

          {/* Historique daté des changements de statut (le plus récent en haut) */}
          {commande.historique?.length > 0 && (
            <div className="card">
              <h2 className="mb-3 font-bold">Historique</h2>
              <ol className="space-y-3 border-l-2 border-gray-200 pl-4">
                {[...commande.historique].reverse().map((h, i) => (
                  <li key={`${h.date}-${i}`} className="relative">
                    <span className={`absolute -left-[23px] top-1 h-3 w-3 rounded-full ${i === 0 ? "bg-boutique" : "bg-gray-300"}`} />
                    <p className="text-sm font-semibold">{STATUTS_COMMANDE[h.statut]?.libelle || h.statut}</p>
                    <p className="text-xs text-gray-500">{dateHeure(h.date)}</p>
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
