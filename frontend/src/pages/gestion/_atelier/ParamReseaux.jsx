import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";

// Onglet « Réseaux sociaux » des paramètres (DG) : connexion du compte TikTok
// de la boutique. Une fois connecté, les produits peuvent être publiés sur ce
// compte depuis leur fiche (bouton « Publier sur TikTok »).
export default function ParamReseaux() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [etat, setEtat] = useState(null);
  const [attente, setAttente] = useState(false);

  const charger = useCallback(() => {
    apiClient.get("/tiktok/etat").then(({ data }) => setEtat(data))
      .catch((err) => toast.erreur(messageErreur(err, "État TikTok indisponible")));
  }, [toast]);
  useEffect(() => { charger(); }, [charger]);

  // Retour de TikTok (…&tiktok=connecte | refuse | erreur) : message puis nettoyage de l'adresse
  useEffect(() => {
    const resultat = params.get("tiktok");
    if (!resultat) return;
    if (resultat === "connecte") toast.succes("Compte TikTok connecté");
    else if (resultat === "refuse") toast.info("Connexion TikTok annulée");
    else toast.erreur("La connexion TikTok a échoué. Réessayez.");
    setParams({ onglet: "reseaux" }, { replace: true });
  }, [params, setParams, toast]);

  // Connexion : on part sur la page d'autorisation de TikTok
  const connecter = async () => {
    setAttente(true);
    try {
      const { data } = await apiClient.get("/tiktok/connexion");
      window.location.href = data.url;
    } catch (err) {
      toast.erreur(messageErreur(err, "Connexion TikTok impossible"));
      setAttente(false);
    }
  };

  const deconnecter = async () => {
    if (!window.confirm("Déconnecter le compte TikTok de la boutique ?")) return;
    try {
      await apiClient.post("/tiktok/deconnexion");
      toast.succes("Compte TikTok déconnecté");
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err));
    }
  };

  if (!etat) return <Chargement />;
  return (
    <div className="card max-w-2xl space-y-4">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-black text-lg text-white" aria-hidden="true">♪</span>
        <div>
          <h2 className="font-bold">TikTok</h2>
          <p className="text-sm text-gray-500">Publiez les photos de vos produits sur le compte TikTok de votre boutique.</p>
        </div>
      </div>

      {!etat.configure && (
        <p className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
          La publication sur TikTok n'est pas encore activée sur adLyn. Elle sera disponible dès que l'application TikTok d'adLyn sera validée.
        </p>
      )}

      {etat.configure && !etat.connecte && (
        <>
          <p className="text-sm text-gray-600">
            Vous serez redirigé vers TikTok pour autoriser adLyn à lire le nom et la photo de votre compte et à y publier
            les contenus que <b>vous</b> choisissez. Rien n'est publié sans votre action.
          </p>
          <button type="button" className="btn-primary" onClick={connecter} disabled={attente}>
            {attente ? "Redirection…" : "Connecter mon compte TikTok"}
          </button>
        </>
      )}

      {etat.connecte && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 p-3">
          {etat.compte.avatar_url && <img src={etat.compte.avatar_url} alt="" className="h-12 w-12 rounded-full object-cover" />}
          <div className="flex-1">
            <p className="font-semibold">{etat.compte.display_name}</p>
            <p className="text-xs text-gray-500">Connecté le {dateHeure(etat.compte.connecte_le)}</p>
          </div>
          <button type="button" className="btn-outline btn-sm" onClick={deconnecter}>Déconnecter</button>
        </div>
      )}
      {etat.connecte && (
        <p className="text-xs text-gray-500">Vous pouvez aussi retirer l'accès depuis TikTok : Paramètres et confidentialité › Sécurité › Applications autorisées.</p>
      )}
    </div>
  );
}
