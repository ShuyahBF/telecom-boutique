import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, montant } from "@/lib/format";
import { MODES_ABONNEMENT, STATUTS_ABONNEMENT } from "@/lib/statuts";
import Chargement from "@/components/Chargement";
import EnTetePage from "@/components/EnTetePage";
import { useToast } from "@/components/Toast";

const fcfa = (v) => `${montant(v || 0)} FCFA`;

// Page « Abonnement » du DG : situation (essai, échéance, retard), paiement en
// ligne par Mobile Money (PawaPay) de la formule choisie, historique.
// Reste accessible quand la boutique est suspendue pour impayé : payer ici
// rend l'accès automatiquement.
export default function Abonnement() {
  const toast = useToast();
  const { boutique, rafraichir } = useAuth();
  const [params, setParams] = useSearchParams();
  const [donnees, setDonnees] = useState(null);
  const [telephone, setTelephone] = useState(boutique?.dg_telephone || boutique?.telephone || "");
  const [paiementEnCours, setPaiementEnCours] = useState(""); // formule dont la page PawaPay se prépare
  const [verification, setVerification] = useState(null); // retour de PawaPay : « en cours », « payé », « échec »
  const [facturesSms, setFacturesSms] = useState([]); // factures du service SMS
  const [utiliserBonus, setUtiliserBonus] = useState(true); // déduire les bonus de parrainage

  const charger = useCallback(() => {
    apiClient.get("/boutique/abonnement").then(({ data }) => setDonnees(data))
      .catch((err) => toast.erreur(messageErreur(err, "Abonnement indisponible")));
    apiClient.get("/boutique/sms/factures").then(({ data }) => setFacturesSms(data)).catch(() => {});
  }, [toast]);
  useEffect(() => { charger(); }, [charger]);

  // Retour de la page PawaPay (?depot=...) : on interroge l'état du paiement
  // jusqu'à sa confirmation (PawaPay met parfois quelques secondes)
  const depot = params.get("depot");
  useEffect(() => {
    if (!depot) return undefined;
    let arret = false;
    let essais = 0;
    setVerification("en_cours");
    const verifier = async () => {
      essais += 1;
      try {
        const { data } = await apiClient.get(`/paiements/${depot}`, { params: { refresh: true } });
        if (arret) return;
        if (data.statut === "paye") {
          setVerification("paye");
          toast.succes(data.type === "facture_sms" ? "Paiement reçu : facture SMS réglée." : "Paiement reçu : votre abonnement est prolongé.");
          charger();
          rafraichir(); // la boutique peut avoir été réactivée
          setParams({}, { replace: true });
          return;
        }
        if (["echec", "montant_incoherent"].includes(data.statut)) {
          setVerification("echec");
          setParams({}, { replace: true });
          return;
        }
      } catch { /* on réessaie */ }
      if (!arret && essais < 20) setTimeout(verifier, 3000);
      else if (!arret) setVerification("attente");
    };
    verifier();
    return () => { arret = true; };
  }, [depot]); // eslint-disable-line react-hooks/exhaustive-deps

  // Paiement en ligne d'une facture SMS (redirection vers PawaPay)
  async function payerFactureSms(f) {
    setPaiementEnCours(f.id);
    try {
      const { data } = await apiClient.post(`/boutique/sms/factures/${f.id}/payer`, { telephone });
      window.location.href = data.url;
    } catch (err) {
      toast.erreur(messageErreur(err, "Paiement impossible pour le moment"));
      setPaiementEnCours("");
    }
  }

  // Paiement en ligne : redirection vers la page sécurisée PawaPay
  async function payer(formule) {
    setPaiementEnCours(formule.code);
    try {
      const { data } = await apiClient.post("/boutique/abonnement/payer", {
        formule: formule.code, telephone, utiliser_bonus: utiliserBonus && (donnees?.bonus?.disponible || 0) > 0 });
      if (data.paye_par_bonus) {
        // Renouvellement entièrement payé par les bonus de parrainage
        toast.succes(`Abonnement renouvelé avec vos bonus : valable jusqu'au ${date(data.paiement.nouvelle_echeance)}`);
        setPaiementEnCours("");
        charger();
        rafraichir();
        return;
      }
      window.location.href = data.url;
    } catch (err) {
      toast.erreur(messageErreur(err, "Paiement impossible pour le moment"));
      setPaiementEnCours("");
    }
  }

  if (!donnees) return <Chargement />;
  const e = donnees.etat;
  // Bonus de parrainage disponibles et montant restant à payer pour une formule
  const bonusDispo = donnees.bonus?.disponible || 0;
  const deduction = (f) => (utiliserBonus ? Math.min(bonusDispo, f.montant) : 0);
  const statut = STATUTS_ABONNEMENT[e.statut] || { libelle: e.statut, classe: "" };

  return (
    <div className="space-y-5">
      <EnTetePage titre="Abonnement adLyn" sousTitre="Votre formule, votre échéance et vos paiements." />

      {/* Retour du paiement en ligne */}
      {verification === "en_cours" && <p className="rounded-xl bg-blue-50 p-3 text-sm text-blue-900">⏳ Vérification de votre paiement auprès de l'opérateur…</p>}
      {verification === "echec" && <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700">❌ Le paiement n'a pas abouti. Vous pouvez réessayer ci-dessous.</p>}
      {verification === "attente" && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Le paiement est toujours en attente de confirmation. Il sera pris en compte automatiquement dès sa validation.</p>}

      {/* Situation actuelle */}
      <div className={`card ${e.statut === "SUSPENDU" || e.statut === "EN_RETARD" ? "border-red-200 bg-red-50/50" : ""}`}>
        <div className="flex flex-wrap items-center gap-3">
          <span className={`badge ${statut.classe}`}>{statut.libelle}</span>
          <p className="text-sm text-gray-600">Formule : <b>{e.formule_libelle}</b></p>
        </div>
        <p className="mt-3 text-2xl font-extrabold">
          {e.statut === "ESSAI" && `Essai gratuit : ${e.jours_restants + 1} jour(s) restant(s)`}
          {["ACTIF", "A_RENOUVELER"].includes(e.statut) && `Abonnement valable jusqu'au ${date(e.echeance)}`}
          {e.statut === "EN_RETARD" && `Échéance dépassée depuis ${e.jours_retard} jour(s)`}
          {e.statut === "SUSPENDU" && "Accès suspendu"}
        </p>
        <p className="text-sm text-gray-600">
          {e.statut === "ESSAI" && `Toutes les fonctions sont ouvertes jusqu'au ${date(e.echeance)} inclus. Abonnez-vous avant cette date pour continuer sans interruption : les jours d'essai restants sont conservés.`}
          {e.statut === "A_RENOUVELER" && `Plus que ${e.jours_restants + 1} jour(s) : renouvelez maintenant pour éviter toute coupure.`}
          {e.statut === "EN_RETARD" && `Montant attendu : ${fcfa(e.montant_attendu)}. Réglez-le rapidement pour éviter la suspension de votre boutique.`}
          {e.statut === "SUSPENDU" && (e.motif_suspension === "IMPAYE"
            ? "Votre back-office et votre vitrine sont fermés faute de paiement. Réglez votre abonnement ci-dessous : l'accès revient dès la confirmation du paiement."
            : "Votre boutique a été suspendue par l'administrateur de la plateforme. Contactez adLyn.")}
        </p>
      </div>

      {/* Formules et paiement en ligne */}
      <div className="card space-y-4">
        <h2 className="font-bold">Payer mon abonnement</h2>
        {/* Sans paiement en ligne, seul un renouvellement entièrement couvert par les bonus reste possible */}
        {!donnees.paiement_en_ligne && bonusDispo <= 0 ? (
          <p className="rounded-xl bg-gray-50 p-3 text-sm text-gray-600">Le paiement en ligne n'est pas encore disponible : contactez l'équipe adLyn pour régler votre abonnement.</p>
        ) : (
          <>
            {!donnees.paiement_en_ligne && (
              <p className="rounded-xl bg-gray-50 p-3 text-sm text-gray-600">Le paiement en ligne n'est pas encore disponible : seules les formules entièrement couvertes par vos bonus peuvent être renouvelées ici.</p>
            )}
            {donnees.paiement_en_ligne && <label className="block max-w-xs">
              <span className="label">Numéro Mobile Money (facultatif)</span>
              <input className="input" type="tel" value={telephone} onChange={(ev) => setTelephone(ev.target.value)} placeholder="+226 70 00 00 00" />
              <span className="mt-1 block text-xs text-gray-500">Vous choisirez l'opérateur (Orange, Moov…) sur la page sécurisée.</span>
            </label>}
            {/* Bonus de parrainage : déduits du prix de la formule choisie */}
            {bonusDispo > 0 && (
              <label className="flex items-start gap-3 rounded-xl border border-green-200 bg-green-50 p-3 text-sm text-green-900">
                <input type="checkbox" className="mt-0.5 h-4 w-4" checked={utiliserBonus} onChange={(ev) => setUtiliserBonus(ev.target.checked)} />
                <span>Utiliser mes bonus de parrainage : <b>{fcfa(bonusDispo)}</b> disponibles.
                  <span className="block text-xs">Ils sont déduits du prix de la formule choisie ; s'ils couvrent tout le prix, l'abonnement est renouvelé sans paiement.</span></span>
              </label>
            )}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {donnees.formules.map((f) => {
                const bonus = deduction(f);
                const reste = f.montant - bonus;
                return (
                  <div key={f.code} className={`rounded-2xl border p-4 ${f.code === e.formule ? "border-primary ring-2 ring-primary/20" : "border-gray-200"}`}>
                    <p className="font-bold">{f.libelle}</p>
                    <p className="text-2xl font-extrabold text-primary">{fcfa(reste)}</p>
                    {bonus > 0 && <p className="text-xs text-green-700"><s className="text-gray-400">{fcfa(f.montant)}</s> − {fcfa(bonus)} de bonus</p>}
                    <p className="text-xs text-gray-500">{f.mois} mois{f.mois > 1 ? ` · soit ${fcfa(Math.round(f.montant / f.mois))} / mois` : ""}</p>
                    <button type="button" className="btn-primary btn-sm mt-3 w-full" disabled={!!paiementEnCours || f.montant <= 0 || (!donnees.paiement_en_ligne && reste > 0)} onClick={() => payer(f)}>
                      {paiementEnCours === f.code ? "Ouverture…" : reste <= 0 ? "Renouveler avec mes bonus" : `Payer ${fcfa(reste)}`}
                    </button>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-gray-500">L'échéance est repoussée de la durée de la formule{e.statut === "SUSPENDU" ? ", à partir du jour du paiement" : ", à partir de l'échéance actuelle (aucun jour perdu)"}.</p>
          </>
        )}
      </div>

      {/* Parrainage : gagner des bonus en invitant d'autres boutiques */}
      <p className="rounded-xl bg-gray-50 p-3 text-sm text-gray-600">
        🤝 Invitez d'autres boutiques sur adLyn : chaque boutique ouverte grâce à vous vous rapporte un bonus déductible de votre abonnement.{" "}
        <Link to="/gestion/parrainage" className="font-semibold text-primary">Mon lien de parrainage →</Link>
      </p>

      {/* Factures du service SMS (volet communication, facturé au SMS envoyé) */}
      {facturesSms.length > 0 && (
        <div className="card overflow-x-auto p-0">
          <h2 className="p-4 pb-1 font-bold">Factures SMS</h2>
          <p className="px-4 pb-2 text-xs text-gray-500">Une facture par mois pour les SMS envoyés à vos clients. En cas de retard, le service SMS peut être suspendu (le reste de la boutique continue de fonctionner).</p>
          <table className="table min-w-[640px]">
            <thead><tr><th>N°</th><th>Période</th><th className="text-right">SMS</th><th className="text-right">Montant</th><th>Échéance</th><th /></tr></thead>
            <tbody>
              {facturesSms.map((f) => (
                <tr key={f.id}>
                  <td className="font-mono text-xs">{f.numero}</td>
                  <td className="whitespace-nowrap">{date(f.debut)} → {date(f.fin)}</td>
                  <td className="text-right">{f.nb_sms}</td>
                  <td className="text-right font-semibold">{fcfa(f.montant)}</td>
                  <td className="whitespace-nowrap">{date(f.echeance)}{f.jours_retard > 0 && <span className="block text-xs font-semibold text-red-600">{f.jours_retard} j de retard</span>}</td>
                  <td className="text-right">
                    {f.statut === "PAYEE" ? <span className="badge bg-green-100 text-green-800">Payée</span>
                      : donnees.paiement_en_ligne
                        ? <button type="button" className="btn-primary btn-sm" disabled={!!paiementEnCours} onClick={() => payerFactureSms(f)}>{paiementEnCours === f.id ? "Ouverture…" : `Payer ${fcfa(f.montant)}`}</button>
                        : <span className="badge bg-amber-100 text-amber-800">À payer</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Historique des paiements */}
      <div className="card overflow-x-auto p-0">
        <h2 className="p-4 pb-2 font-bold">Mes paiements</h2>
        {donnees.paiements.length === 0 ? <p className="px-4 pb-4 text-sm text-gray-500">Aucun paiement pour l'instant.</p> : (
          <table className="table min-w-[560px]">
            <thead><tr><th>Date</th><th>Formule</th><th>Mode</th><th className="text-right">Montant</th><th>Valable jusqu'au</th></tr></thead>
            <tbody>
              {donnees.paiements.map((p) => (
                <tr key={p.id}>
                  <td>{date(p.date)}</td><td>{p.formule_libelle}</td><td>{MODES_ABONNEMENT[p.mode] || p.mode}</td>
                  <td className="text-right font-semibold">{fcfa(p.montant)}{p.bonus_deduit > 0 && <span className="block text-xs font-normal text-green-700">+ {fcfa(p.bonus_deduit)} de bonus</span>}</td><td>{date(p.nouvelle_echeance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
