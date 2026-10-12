import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import { useToast } from "@/components/Toast";

// ============================================================================
// Lot C — super-administrateur : réglages de la vérification des pièces d'identité
// par Liluvine (IA) — GET/PUT /plateforme/parametres/kyc-ia
//   - validation automatique de la boutique quand le nom concorde (activée par défaut) ;
//   - seuil de confiance minimal de la lecture (0,80 par défaut) ;
//   - nombre maximal de vérifications IA par boutique sur 24 heures (5 par défaut).
// Lot D — photo du DG tenant sa pièce (selfie) :
//   - « Exiger le selfie » (activé par défaut) : sans selfie, le dossier part en revue humaine ;
//   - seuil visage : confiance minimale « même personne » pour valider sans humain (85 % par défaut).
// La clé ANTHROPIC_API_KEY n'est jamais affichée : seulement « configurée » ou non.
// ============================================================================
export default function ReglageKycIa() {
  const toast = useToast();
  const [etat, setEtat] = useState(null); // réglages lus sur le serveur
  const [saisie, setSaisie] = useState(null); // formulaire en cours de modification
  const [envoi, setEnvoi] = useState(false);

  // Chargement des réglages au premier affichage
  useEffect(() => {
    apiClient.get("/plateforme/parametres/kyc-ia")
      .then(({ data }) => { setEtat(data); setSaisie(versFormulaire(data)); })
      .catch((err) => toast.erreur(messageErreur(err, "Réglages de Liluvine indisponibles")));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Valeurs du serveur -> champs du formulaire (seuil affiché en pourcentage)
  function versFormulaire(d) {
    return {
      auto_validation: d.auto_validation, seuil: String(Math.round(d.seuil_confiance * 100)), max_par_jour: String(d.max_par_jour),
      exiger_selfie: d.exiger_selfie !== false, seuil_visage: String(Math.round((d.seuil_visage ?? 0.85) * 100)),
    };
  }

  async function enregistrer(e) {
    e.preventDefault();
    setEnvoi(true);
    try {
      const { data } = await apiClient.put("/plateforme/parametres/kyc-ia", {
        auto_validation: saisie.auto_validation, seuil_confiance: Number(saisie.seuil) / 100, max_par_jour: Number(saisie.max_par_jour),
        exiger_selfie: saisie.exiger_selfie, seuil_visage: Number(saisie.seuil_visage) / 100,
      });
      setEtat(data);
      setSaisie(versFormulaire(data));
      toast.succes("Réglages de Liluvine enregistrés");
    } catch (err) {
      toast.erreur(messageErreur(err, "Valeurs invalides (seuils entre 50 et 100 %, 1 à 20 vérifications par jour)"));
    } finally {
      setEnvoi(false);
    }
  }

  if (!etat || !saisie) return null;
  const maj = (champ, valeur) => setSaisie((s) => ({ ...s, [champ]: valeur }));
  return (
    <form onSubmit={enregistrer} className="space-y-3 text-sm">
      <p className="text-gray-600">
        Quand un commerçant envoie sa pièce d'identité, Liluvine la lit et compare le nom au propriétaire déclaré.
        S'il concorde (pièce lisible, non expirée, confiance suffisante), la boutique peut être validée tout de suite.
      </p>
      {/* État de l'IA : clé présente ou non (jamais sa valeur) et modèle utilisé */}
      <p>
        <span className={`badge ${etat.ia_configuree ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"}`}>
          {etat.ia_configuree ? "IA configurée" : "Clé ANTHROPIC_API_KEY absente : vérification manuelle"}
        </span>
        <span className="ml-2 text-gray-500">Modèle : {etat.modele}</span>
      </p>
      <label className="flex items-center gap-2 font-semibold">
        <input type="checkbox" checked={saisie.auto_validation} onChange={(e) => maj("auto_validation", e.target.checked)} />
        Valider automatiquement la boutique quand le nom concorde
      </label>
      {/* Lot D — selfie exigé : sans lui, jamais de validation automatique */}
      <label className="flex items-center gap-2 font-semibold">
        <input type="checkbox" checked={saisie.exiger_selfie} onChange={(e) => maj("exiger_selfie", e.target.checked)} />
        🤳 Exiger le selfie (photo du commerçant tenant sa pièce à côté du visage)
      </label>
      <p className="text-xs text-gray-500">
        Liluvine compare le visage du selfie à la photo de la pièce. Elle ne valide seule que si tout est sûr ; au moindre
        doute, le dossier entre dans la file « 🔍 KYC à vérifier » et l'équipe est prévenue par e-mail.
      </p>
      <div className="flex flex-wrap items-end gap-4">
        <label className="block">
          <span className="text-xs text-gray-500">Seuil de confiance (%)</span>
          <input className="input w-28" type="number" min={50} max={100} required value={saisie.seuil} onChange={(e) => maj("seuil", e.target.value)} />
        </label>
        <label className="block">
          <span className="text-xs text-gray-500">Vérifications IA par boutique / 24 h</span>
          <input className="input w-28" type="number" min={1} max={20} required value={saisie.max_par_jour} onChange={(e) => maj("max_par_jour", e.target.value)} />
        </label>
        <label className="block">
          <span className="text-xs text-gray-500">Seuil visage « même personne » (%)</span>
          <input className="input w-28" type="number" min={50} max={100} required value={saisie.seuil_visage} onChange={(e) => maj("seuil_visage", e.target.value)} />
        </label>
        <button className="btn-primary btn-sm" disabled={envoi}>{envoi ? "Patientez…" : "Enregistrer"}</button>
      </div>
      {etat.modifie_le && <p className="text-xs text-gray-500">Modifié le {dateHeure(etat.modifie_le)}{etat.modifie_par ? ` par ${etat.modifie_par}` : ""}</p>}
    </form>
  );
}
