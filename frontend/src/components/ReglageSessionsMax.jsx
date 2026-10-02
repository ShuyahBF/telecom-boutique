import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { useToast } from "@/components/Toast";

// Super-administrateur : nombre maximal de sessions ouvertes en même temps par compte
// (1 à 20, 5 par défaut). Au-delà, la session la plus ancienne est fermée à la connexion.
export default function ReglageSessionsMax() {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null);
  const [saisie, setSaisie] = useState("");
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    apiClient.get("/plateforme/parametres/sessions").then(({ data }) => { setDonnees(data); setSaisie(String(data.valeur)); })
      .catch((err) => toast.erreur(messageErreur(err, "Réglage des sessions indisponible")));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function enregistrer(e) {
    e.preventDefault();
    setEnvoi(true);
    try {
      const { data } = await apiClient.put("/plateforme/parametres/sessions", { valeur: Number(saisie) });
      setDonnees(data);
      toast.succes("Nombre maximal de sessions enregistré");
    } catch (err) {
      toast.erreur(messageErreur(err, "Valeur invalide"));
    } finally {
      setEnvoi(false);
    }
  }

  if (!donnees) return null;
  return (
    <form onSubmit={enregistrer} className="space-y-2 text-sm">
      <p className="text-gray-600">Sessions ouvertes en même temps par compte (entre {donnees.min} et {donnees.max}). À la connexion de trop, la session la moins récemment utilisée est fermée. Actuellement : <b>{donnees.valeur}</b>.</p>
      <div className="flex flex-wrap items-center gap-2">
        <input className="input w-28" type="number" min={donnees.min} max={donnees.max} required value={saisie} onChange={(e) => setSaisie(e.target.value)} />
        <button className="btn-primary btn-sm" disabled={envoi}>{envoi ? "…" : "Enregistrer"}</button>
      </div>
    </form>
  );
}
