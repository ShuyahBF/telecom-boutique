import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { dureeTexte } from "@/lib/inactivite";

// Réglage de la déconnexion après inactivité (durée en SECONDES, 0 = désactivée).
// mode « plateforme » : super-admin, valeur par défaut de toutes les boutiques ;
// mode « boutique »   : super-admin, valeur propre à une boutique (vide = plateforme) ;
// mode « dg »         : le DG ne peut que RÉDUIRE la durée fixée par l'administrateur.
const ADRESSES = {
  plateforme: () => "/plateforme/parametres/inactivite",
  boutique: (id) => `/plateforme/boutiques/${id}/inactivite`,
  dg: () => "/boutique/inactivite",
};

export default function ReglageInactivite({ mode, boutiqueId }) {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null);
  const [saisie, setSaisie] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const adresse = ADRESSES[mode](boutiqueId);

  // Valeur affichée dans le champ : celle réglée à ce niveau (vide = niveau au-dessus)
  const appliquer = (data) => {
    setDonnees(data);
    const propre = mode === "plateforme" ? data.secondes : mode === "boutique" ? data.boutique : data.dg;
    setSaisie(propre === null || propre === undefined ? "" : String(propre));
  };

  useEffect(() => {
    apiClient.get(adresse).then(({ data }) => appliquer(data))
      .catch((err) => toast.erreur(messageErreur(err, "Réglage d'inactivité indisponible")));
  }, [adresse]); // eslint-disable-line react-hooks/exhaustive-deps

  async function enregistrer(valeur) {
    setEnvoi(true);
    try {
      const { data } = await apiClient.put(adresse, { secondes: valeur });
      appliquer(data);
      toast.succes("Déconnexion après inactivité enregistrée");
    } catch (err) {
      toast.erreur(messageErreur(err, "Durée invalide"));
    } finally {
      setEnvoi(false);
    }
  }

  const valider = (e) => {
    e.preventDefault();
    if (mode === "plateforme" || saisie.trim() !== "") return enregistrer(Number(saisie));
    return enregistrer(null);
  };

  if (!donnees) return null;
  const min = donnees.min ?? 60;
  const max = donnees.max ?? 86400;
  return (
    <form onSubmit={valider} className="space-y-2 text-sm">
      {mode === "plateforme" && (
        <p className="text-gray-600">Valeur par défaut de toutes les boutiques (et de votre propre compte). 0 = désactivée ; sinon entre {min} et {max} secondes. Actuellement : <b>{dureeTexte(donnees.secondes)}</b>.</p>
      )}
      {mode === "boutique" && (
        <p className="text-gray-600">Plateforme : <b>{dureeTexte(donnees.plateforme)}</b>. Laissez vide pour la suivre. Effective pour cette boutique : <b>{dureeTexte(donnees.effective)}</b>{donnees.dg ? ` (réduite par le DG à ${dureeTexte(donnees.dg)})` : ""}.</p>
      )}
      {mode === "dg" && (
        <p className="text-gray-600">Durée fixée par l'administrateur adLyn : <b>{dureeTexte(donnees.plafond)}</b>. Vous pouvez seulement la réduire (laissez vide pour la garder). Effective : <b>{dureeTexte(donnees.effective)}</b>.</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <input className="input w-40" type="number" inputMode="numeric" min={0} max={mode === "dg" && donnees.plafond ? donnees.plafond : max}
          placeholder={mode === "plateforme" ? "0" : "vide = suivre"} required={mode === "plateforme"}
          value={saisie} onChange={(e) => setSaisie(e.target.value.replace(/\D/g, ""))} aria-label="Durée en secondes" />
        <span className="text-gray-500">secondes{saisie ? ` (${dureeTexte(saisie)})` : ""}</span>
        <button className="btn-primary btn-sm" disabled={envoi}>{envoi ? "Enregistrement…" : "Enregistrer"}</button>
      </div>
    </form>
  );
}
