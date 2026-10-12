import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import Chargement from "@/components/Chargement";
import Patientez from "@/components/Patientez";
import { useToast } from "@/components/Toast";

// Pictogramme Facebook usuel (« f » blanc dans un rond bleu), dessiné en SVG (règle 8 : pictogrammes usuels)
function IconeFacebook() {
  return (
    <svg viewBox="0 0 24 24" className="h-10 w-10" aria-hidden="true">
      <circle cx="12" cy="12" r="12" fill="#1877F2" />
      <path fill="#fff" d="M13.4 19.5v-6h2l.3-2.4h-2.3V9.6c0-.7.2-1.2 1.2-1.2h1.2V6.3c-.2 0-1-.1-1.8-.1-1.8 0-3 1.1-3 3.1v1.8H9v2.4h2v6h2.4z" />
    </svg>
  );
}

// Carte « Page Facebook d'adLyn » de l'onglet Réseaux sociaux (DG) :
// accord de la boutique pour que les articles de sa vitrine soient présentés sur la page Facebook d'adLyn
// (publiés par Liluvine depuis SAWALI). DÉSACTIVÉ par défaut ; modifiable à tout moment.
export default function ParamFacebookAdlyn() {
  const toast = useToast();
  const [boutique, setBoutique] = useState(null);
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    apiClient.get("/boutique").then(({ data }) => setBoutique(data))
      .catch((err) => toast.erreur(messageErreur(err, "Réglage indisponible")));
  }, [toast]);

  // Enregistrement immédiat de la case (le serveur garde la date du choix)
  const basculer = async (autorise) => {
    setEnvoi(true);
    try {
      const { data } = await apiClient.patch("/boutique", { publication_facebook_adlyn: autorise });
      setBoutique(data);
      toast.succes(autorise ? "Vos articles pourront être présentés sur la page Facebook d'adLyn"
                            : "Vos articles ne seront plus présentés sur la page Facebook d'adLyn");
    } catch (err) {
      toast.erreur(messageErreur(err));
    } finally {
      setEnvoi(false);
    }
  };

  if (!boutique) return <Chargement />;
  const autorise = boutique.publication_facebook_adlyn === true;
  return (
    <div className="card max-w-2xl space-y-3" data-testid="param-facebook-adlyn">
      <Patientez actif={envoi} />
      <div className="flex items-center gap-3">
        <IconeFacebook />
        <div>
          <h2 className="font-bold">Page Facebook d'adLyn</h2>
          <p className="text-sm text-gray-500">Faites connaître votre boutique sur la page Facebook d'adLyn.</p>
        </div>
      </div>
      <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-gray-200 p-3">
        <input type="checkbox" className="mt-1 h-4 w-4" checked={autorise} disabled={envoi}
               onChange={(e) => basculer(e.target.checked)} />
        <span className="text-sm">
          <b>Autoriser adLyn à publier mes articles sur sa page Facebook</b>
          <span className="block text-gray-500">
            De temps en temps, un article de votre vitrine (photo, nom, prix et nom de la boutique) peut être présenté sur
            la page Facebook d'adLyn, avec le lien vers votre vitrine. Aucune coordonnée (téléphone, e-mail, gérant)
            n'est publiée. Vous pouvez décocher à tout moment.
          </span>
        </span>
      </label>
      {boutique.validee === false && (
        <p className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Votre boutique n'est pas encore validée par l'équipe adLyn : aucun article ne sera présenté avant la validation.
        </p>
      )}
    </div>
  );
}
