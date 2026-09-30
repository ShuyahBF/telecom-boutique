import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure, montant } from "@/lib/format";
import Chargement from "@/components/Chargement";
import EnTetePage from "@/components/EnTetePage";
import QrCode from "@/components/QrCode";
import { useToast } from "@/components/Toast";

const fcfa = (v) => `${montant(v || 0)} FCFA`;
const STATUTS = {
  EN_ATTENTE: ["En attente d'ouverture", "bg-amber-100 text-amber-800"],
  VALIDE: ["Ouverte — bonus gagné", "bg-green-100 text-green-800"],
  ANNULE: ["Sans bonus", "bg-gray-100 text-gray-600"],
};

// Page « Parrainage » (DG) : lien d'invitation à partager, boutiques invitées et
// bonus gagnés. Chaque boutique ouverte grâce au lien rapporte un bonus,
// déductible de l'abonnement adLyn (page « Abonnement adLyn »).
export default function Parrainage() {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null);

  useEffect(() => {
    apiClient.get("/boutique/parrainage").then(({ data }) => setDonnees(data))
      .catch((err) => toast.erreur(messageErreur(err, "Parrainage indisponible")));
  }, [toast]);

  if (!donnees) return <Chargement />;
  const s = donnees.solde;
  const message = `Ouvrez votre boutique de téléphonie sur adLyn : vitrine en ligne, commandes, stock et réparations. Je vous invite : ${donnees.lien}`;

  const copier = async () => {
    try {
      await navigator.clipboard.writeText(donnees.lien);
      toast.succes("Lien copié");
    } catch {
      toast.erreur("Copie impossible : sélectionnez le lien à la main");
    }
  };

  return (
    <div className="space-y-5">
      <EnTetePage titre="Parrainage" sousTitre={`Invitez d'autres boutiques : ${fcfa(donnees.bonus_unitaire)} de bonus pour chaque boutique ouverte grâce à vous.`} />

      {/* Solde des bonus */}
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="card"><p className="text-sm text-gray-500">Bonus disponibles</p><p className="text-3xl font-extrabold text-green-700">{fcfa(s.disponible)}</p>
          <p className="text-xs text-gray-500">Déductibles de votre abonnement adLyn.</p></div>
        <div className="card"><p className="text-sm text-gray-500">Bonus gagnés</p><p className="text-2xl font-bold">{fcfa(s.gagnes)}</p></div>
        <div className="card"><p className="text-sm text-gray-500">Bonus utilisés</p><p className="text-2xl font-bold">{fcfa(s.utilises)}</p>
          {s.reserves > 0 && <p className="text-xs text-amber-700">{fcfa(s.reserves)} réservés pour un paiement en cours</p>}</div>
      </div>

      {/* Lien d'invitation */}
      <div className="card grid gap-5 md:grid-cols-[auto_1fr] md:items-center">
        <div className="mx-auto rounded-xl border border-gray-200 bg-white p-2"><QrCode valeur={donnees.lien} taille={180} /></div>
        <div className="min-w-0 space-y-3">
          <h2 className="font-bold">Mon lien d'invitation</h2>
          {!donnees.lien_actif && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Votre lien sera actif dès que votre boutique sera ouverte au public.</p>}
          <p className="break-all rounded-lg bg-gray-50 px-3 py-2 font-mono text-sm">{donnees.lien}</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-primary" onClick={copier}>Copier le lien</button>
            <a className="btn-outline" href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noopener noreferrer">Partager sur WhatsApp</a>
          </div>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-gray-600">
            <li>La boutique invitée ouvre votre lien et <b>accepte votre invitation</b>.</li>
            <li>Elle remplit sa demande d'ouverture ; l'équipe adLyn vérifie puis <b>ouvre sa boutique</b>.</li>
            <li>Vous recevez alors <b>{fcfa(donnees.bonus_unitaire)}</b> de bonus, déductibles de votre abonnement.</li>
          </ol>
        </div>
      </div>

      {/* Boutiques invitées */}
      <div className="card overflow-x-auto p-0">
        <h2 className="p-4 pb-2 font-bold">Boutiques invitées</h2>
        {donnees.filleuls.length === 0 ? <p className="px-4 pb-4 text-sm text-gray-500">Aucune boutique invitée pour le moment : partagez votre lien.</p> : (
          <table className="table min-w-[560px]">
            <thead><tr><th>Boutique</th><th>Invitation acceptée</th><th>Statut</th><th className="text-right">Bonus</th></tr></thead>
            <tbody>
              {donnees.filleuls.map((f) => {
                const [libelle, classe] = STATUTS[f.statut] || [f.statut, ""];
                return (
                  <tr key={f.id}>
                    <td>{f.filleul_nom} <span className="text-xs text-gray-500">{f.filleul_ville}</span></td>
                    <td className="whitespace-nowrap">{dateHeure(f.invitation_acceptee_le)}</td>
                    <td><span className={`badge ${classe}`}>{libelle}</span></td>
                    <td className="text-right font-semibold">{f.statut === "VALIDE" ? fcfa(f.bonus) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Historique des bonus */}
      {donnees.mouvements.length > 0 && (
        <div className="card overflow-x-auto p-0">
          <h2 className="p-4 pb-2 font-bold">Historique des bonus</h2>
          <table className="table min-w-[480px]">
            <thead><tr><th>Date</th><th>Opération</th><th className="text-right">Montant</th></tr></thead>
            <tbody>
              {donnees.mouvements.map((m) => (
                <tr key={m.id}>
                  <td className="whitespace-nowrap">{dateHeure(m.created_at)}</td>
                  <td>{m.libelle}{m.statut === "EN_ATTENTE" && <span className="ml-2 badge bg-amber-100 text-amber-800">en cours</span>}</td>
                  <td className={`text-right font-semibold ${m.type === "GAIN" ? "text-green-700" : ""}`}>{m.type === "GAIN" ? "+" : "−"} {fcfa(m.montant)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
