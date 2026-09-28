import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import { Case, Champ } from "./communs";

// Variables utilisables dans les textes (remplacées au moment de l'envoi)
const VARIABLES = [
  ["{{ client.nom }}", "Nom du client"],
  ["{{ commande.numero }}", "N° de commande"],
  ["{{ commande.total }}", "Montant de la commande"],
  ["{{ commande.statut_libelle }}", "Statut de la commande"],
  ["{{ dossier.numero }}", "N° de dossier SAV"],
  ["{{ dossier.code_suivi }}", "Code de suivi SAV"],
  ["{{ dossier.statut_libelle }}", "Statut de la réparation"],
  ["{{ dossier.marque }}", "Marque de l'appareil"],
  ["{{ dossier.modele }}", "Modèle de l'appareil"],
  ["{{ conversation.sujet }}", "Sujet de la demande de conseil"],
  ["{{ message.texte }}", "Texte du message"],
  ["{{ boutique.nom }}", "Nom de la boutique"],
  ["{{ boutique.devise }}", "Devise (FCFA…)"],
  ["{{ lien }}", "Lien de suivi / de réponse"],
];

// Onglet « Modèles de messages » : textes des e-mails automatiques.
export default function ParamModeles() {
  const toast = useToast();
  const [modeles, setModeles] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [ouvert, setOuvert] = useState(""); // code du modèle en cours d'édition
  const [edition, setEdition] = useState(null);

  // Chargement de la liste (GET /boutique/messagerie/modeles)
  useEffect(() => {
    apiClient.get("/boutique/messagerie/modeles")
      .then(({ data }) => setModeles(data))
      .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger les modèles")))
      .finally(() => setChargement(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Ouvre / ferme un modèle (une seule fiche ouverte à la fois)
  function basculer(m) {
    if (ouvert === m.code) { setOuvert(""); setEdition(null); return; }
    setOuvert(m.code);
    setEdition({ sujet: m.sujet, corps: m.corps, actif: m.actif });
  }

  // Remplace le modèle modifié dans la liste
  const remplacer = (m) => setModeles((liste) => liste.map((x) => (x.code === m.code ? m : x)));

  // Enregistrement (PUT /boutique/messagerie/modeles/{code})
  async function enregistrer(code) {
    try {
      const { data } = await apiClient.put(`/boutique/messagerie/modeles/${code}`, edition);
      remplacer(data);
      toast.succes("Modèle enregistré");
    } catch (err) {
      toast.erreur(messageErreur(err, "Le sujet et le texte sont obligatoires"));
    }
  }

  // Retour au texte proposé à l'origine
  async function reinitialiser(code) {
    if (!window.confirm("Remettre le texte d'origine ? Vos modifications seront perdues.")) return;
    try {
      const { data } = await apiClient.post(`/boutique/messagerie/modeles/${code}/reinitialiser`);
      remplacer(data);
      setEdition({ sujet: data.sujet, corps: data.corps, actif: data.actif });
      toast.succes("Texte d'origine rétabli");
    } catch (err) {
      toast.erreur(messageErreur(err, "Réinitialisation impossible"));
    }
  }

  if (chargement) return <Chargement />;

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      {/* Liste des modèles en accordéon */}
      <div className="space-y-3 lg:col-span-2">
        {modeles.map((m) => (
          <div key={m.code} className="card p-0">
            <button type="button" className="flex w-full items-center justify-between gap-3 p-4 text-left" onClick={() => basculer(m)}>
              <span className="min-w-0">
                <span className="block font-semibold">{m.libelle}</span>
                <span className="block truncate text-sm text-gray-500">{m.sujet}</span>
              </span>
              <span className="flex shrink-0 items-center gap-2">
                {m.actif ? <span className="badge bg-green-100 text-green-800">Actif</span> : <span className="badge bg-gray-100 text-gray-600">Désactivé</span>}
                <span className="text-gray-400">{ouvert === m.code ? "▲" : "▼"}</span>
              </span>
            </button>
            {ouvert === m.code && edition && (
              <div className="space-y-3 border-t border-gray-100 p-4">
                <Champ label="Sujet"><input className="input" maxLength={200} value={edition.sujet} onChange={(e) => setEdition({ ...edition, sujet: e.target.value })} /></Champ>
                <Champ label="Texte"><textarea className="input min-h-[180px] font-mono text-sm" maxLength={5000} value={edition.corps} onChange={(e) => setEdition({ ...edition, corps: e.target.value })} /></Champ>
                <Case label="Envoyer ce message" aide="Décochez pour ne plus envoyer cet e-mail automatique." checked={edition.actif} onChange={(v) => setEdition({ ...edition, actif: v })} />
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="btn-primary" onClick={() => enregistrer(m.code)}>💾 Enregistrer</button>
                  <button type="button" className="btn-outline" onClick={() => reinitialiser(m.code)}>↺ Rétablir le texte d'origine</button>
                </div>
                <p className="font-mono text-xs text-gray-400">Code : {m.code}</p>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Aide : variables disponibles */}
      <div className="card h-fit text-sm">
        <h2 className="mb-2 font-bold">Variables disponibles</h2>
        <p className="mb-3 text-gray-600">Copiez-les telles quelles (avec les accolades) : elles seront remplacées par les vraies valeurs à l'envoi. Certaines n'ont de sens que dans certains messages (ex. « dossier » pour les réparations).</p>
        <ul className="space-y-1.5">
          {VARIABLES.map(([code, sens]) => (
            <li key={code} className="flex flex-wrap items-baseline justify-between gap-x-2">
              <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">{code}</code>
              <span className="text-xs text-gray-500">{sens}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
