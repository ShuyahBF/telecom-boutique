import { useEffect, useState } from "react";
import { apiClient, EN_ARRIERE_PLAN } from "@/lib/api";

// Date de la dernière sauvegarde (backend/sauvegarde_auto.py) :
//  - « Dernière sauvegarde générale » (toute la plateforme, chaque nuit vers R2) ;
//  - « Dernière sauvegarde de votre boutique » (Google Drive, chaque nuit).
// Sans sauvegarde : « Aucune sauvegarde enregistrée » en orange.
// compact = pied de page discret de l'espace de gestion ; sinon carte de « Mon compte ».
export default function DernieresSauvegardes({ compact = false }) {
  const [donnees, setDonnees] = useState(null);

  useEffect(() => {
    apiClient.get("/auth/sauvegardes/dernieres", EN_ARRIERE_PLAN).then(({ data }) => setDonnees(data)).catch(() => setDonnees(null));
  }, []);

  if (!donnees) return null;
  const valeur = (d) => (d
    ? <span className={compact ? "" : "font-semibold"}>{d.texte}</span>
    : <span className="font-semibold text-orange-600">Aucune sauvegarde enregistrée</span>);
  const lignes = [["Dernière sauvegarde générale", donnees.generale]];
  if (donnees.a_une_boutique) lignes.push(["Dernière sauvegarde de votre boutique", donnees.boutique]);

  if (compact) {
    return (
      <p className="no-print mt-8 flex flex-wrap justify-center gap-x-4 gap-y-1 text-center text-xs text-gray-400">
        {lignes.map(([libelle, d]) => <span key={libelle}>{libelle} : {valeur(d)}</span>)}
      </p>
    );
  }
  return (
    <div className="rounded-xl border border-gray-200 p-4 text-sm">
      <p className="mb-1 font-semibold text-gray-600">💾 Sauvegardes</p>
      {lignes.map(([libelle, d]) => <p key={libelle}>{libelle} : {valeur(d)}</p>)}
    </div>
  );
}
