import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import { Champ } from "./communs";
import ReglageInactivite from "@/components/ReglageInactivite";

// Libellés et couleurs des résultats de connexion
const RESULTATS = {
  SUCCES: ["Réussie", "bg-green-100 text-green-800"],
  ECHEC: ["Identifiants incorrects", "bg-amber-100 text-amber-800"],
  BLOQUE: ["Refusée (règle)", "bg-red-100 text-red-700"],
};

// Onglet « Sécurité » des paramètres (DG) :
//  1. règles d'accès au back-office : adresses IP (avec « * », ex. 196.28.*) ou
//     appareils, à AUTORISER (liste blanche) ou à INTERDIRE ;
//  2. journal des connexions : chaque tentative, avec un bouton pour autoriser
//     ou interdire son adresse IP ou son appareil à l'avenir.
export default function ParamSecurite() {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null);
  const [journal, setJournal] = useState(null);
  const [filtre, setFiltre] = useState({ resultat: "", q: "" });
  const [nouvelle, setNouvelle] = useState({ type: "IP", valeur: "", action: "INTERDIRE", libelle: "" });

  const chargerRegles = useCallback(() => {
    apiClient.get("/boutique/acces").then(({ data }) => setDonnees(data))
      .catch((err) => toast.erreur(messageErreur(err, "Règles indisponibles")));
  }, [toast]);
  useEffect(() => { chargerRegles(); }, [chargerRegles]);

  // Journal (petit délai pendant la saisie de la recherche)
  useEffect(() => {
    const t = setTimeout(() => {
      apiClient.get("/boutique/acces/journal", { params: filtre }).then(({ data }) => setJournal(data.lignes)).catch(() => setJournal([]));
    }, 250);
    return () => clearTimeout(t);
  }, [filtre, donnees]);

  async function ajouter(e) {
    e.preventDefault();
    try {
      await apiClient.post("/boutique/acces/regles", { ...nouvelle, valeur: nouvelle.valeur.trim() });
      toast.succes("Règle ajoutée");
      setNouvelle({ ...nouvelle, valeur: "", libelle: "" });
      chargerRegles();
    } catch (err) {
      toast.erreur(messageErreur(err, "Règle refusée"));
    }
  }

  async function supprimer(r) {
    if (!window.confirm(`Supprimer la règle « ${r.valeur} » ?`)) return;
    try {
      await apiClient.delete(`/boutique/acces/regles/${r.id}`);
      chargerRegles();
    } catch (err) {
      toast.erreur(messageErreur(err, "Suppression impossible"));
    }
  }

  // Règle créée depuis une ligne du journal (adresse IP ou appareil de cette connexion)
  async function depuisJournal(ligne, type, action) {
    const quoi = type === "IP" ? `l'adresse ${ligne.ip}` : `l'appareil ${ligne.appareil} (${ligne.appareil_id})`;
    if (!window.confirm(`${action === "AUTORISER" ? "Autoriser" : "Interdire"} ${quoi} pour les prochaines connexions ?`)) return;
    try {
      await apiClient.post(`/boutique/acces/journal/${ligne.id}/regle`, { type, action });
      toast.succes(action === "AUTORISER" ? "Ajouté à la liste des accès autorisés" : "Accès interdit");
      chargerRegles();
    } catch (err) {
      toast.erreur(messageErreur(err, "Règle refusée"));
    }
  }

  if (!donnees) return <Chargement />;
  const blanche = donnees.regles.filter((r) => r.action === "AUTORISER");
  const noire = donnees.regles.filter((r) => r.action === "INTERDIRE");
  const moi = donnees.ma_connexion;

  const listeRegles = (liste, vide) => (
    liste.length === 0 ? <p className="text-sm text-gray-500">{vide}</p> : (
      <ul className="divide-y divide-gray-100 rounded-xl border border-gray-200">
        {liste.map((r) => (
          <li key={r.id} className="flex items-center gap-3 px-3 py-2 text-sm">
            <span className="badge bg-gray-100 text-gray-700">{r.type === "IP" ? "IP" : "Appareil"}</span>
            <span className="font-mono font-semibold">{r.valeur}</span>
            <span className="min-w-0 flex-1 truncate text-gray-500">{r.libelle}</span>
            <button type="button" className="text-red-600" onClick={() => supprimer(r)} aria-label="Supprimer la règle">✕</button>
          </li>
        ))}
      </ul>
    ));

  return (
    <div className="space-y-5">
      {/* Déconnexion après inactivité : le DG peut seulement réduire la durée de l'administrateur */}
      <div className="card">
        <h2 className="mb-2 font-bold">⏳ Déconnexion après inactivité</h2>
        <ReglageInactivite mode="dg" />
      </div>
      {/* Connexion actuelle : utile pour autoriser sa propre adresse avant une liste blanche */}
      <div className="rounded-2xl bg-blue-50 p-4 text-sm text-blue-900">
        Votre connexion actuelle : adresse IP <b className="font-mono">{moi.ip}</b> · appareil <b>{moi.appareil}</b>
        {moi.appareil_id && <> (<span className="font-mono">{moi.appareil_id}</span>)</>}.
        <span className="block text-xs text-blue-800">
          Les interdictions l'emportent toujours. Dès qu'une règle « autoriser » existe, seules les adresses et les appareils
          de cette liste blanche peuvent se connecter ; « * » dans la liste blanche autorise tout le monde.
        </span>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="card space-y-3">
          <h2 className="font-bold">✅ Liste blanche (accès autorisés)</h2>
          {listeRegles(blanche, "Vide : toutes les adresses et tous les appareils sont acceptés (sauf ceux interdits).")}
        </div>
        <div className="card space-y-3">
          <h2 className="font-bold">⛔ Accès interdits</h2>
          {listeRegles(noire, "Aucune interdiction.")}
        </div>
      </div>

      {/* Ajout d'une règle */}
      <form onSubmit={ajouter} className="card grid gap-3 sm:grid-cols-5 sm:items-end">
        <Champ label="Action">
          <select className="input" value={nouvelle.action} onChange={(e) => setNouvelle({ ...nouvelle, action: e.target.value })}>
            <option value="INTERDIRE">Interdire</option><option value="AUTORISER">Autoriser</option>
          </select>
        </Champ>
        <Champ label="Type">
          <select className="input" value={nouvelle.type} onChange={(e) => setNouvelle({ ...nouvelle, type: e.target.value })}>
            <option value="IP">Adresse IP</option><option value="APPAREIL">Appareil</option>
          </select>
        </Champ>
        <Champ label={nouvelle.type === "IP" ? "Adresse ou motif" : "Identifiant d'appareil"}>
          <input className="input font-mono" required maxLength={45} value={nouvelle.valeur} onChange={(e) => setNouvelle({ ...nouvelle, valeur: e.target.value })}
            placeholder={nouvelle.type === "IP" ? "ex. 196.28.* ou *" : "voir le journal, ou *"} />
        </Champ>
        <Champ label="Libellé"><input className="input" maxLength={80} value={nouvelle.libelle} onChange={(e) => setNouvelle({ ...nouvelle, libelle: e.target.value })} placeholder="ex. Wifi de la boutique" /></Champ>
        <button className="btn-primary">+ Ajouter</button>
      </form>

      {/* Journal des connexions */}
      <div className="card space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-bold">📜 Journal des connexions</h2>
          <div className="flex flex-wrap gap-2">
            <input className="input max-w-[14rem]" placeholder="IP, nom, e-mail, appareil…" value={filtre.q} onChange={(e) => setFiltre({ ...filtre, q: e.target.value })} />
            <select className="input max-w-[12rem]" value={filtre.resultat} onChange={(e) => setFiltre({ ...filtre, resultat: e.target.value })} aria-label="Filtrer par résultat">
              <option value="">Toutes</option>{Object.entries(RESULTATS).map(([c, [l]]) => <option key={c} value={c}>{l}</option>)}
            </select>
          </div>
        </div>
        {!journal ? <Chargement /> : journal.length === 0 ? <p className="text-sm text-gray-500">Aucune connexion enregistrée.</p> : (
          <div className="overflow-x-auto">
            <table className="table min-w-[860px]">
              <thead><tr><th>Date</th><th>Compte</th><th>Résultat</th><th>Adresse IP</th><th>Appareil</th><th>Pour l'avenir</th></tr></thead>
              <tbody>
                {journal.map((l) => {
                  const [libelle, couleur] = RESULTATS[l.resultat] || [l.resultat, "bg-gray-100"];
                  return (
                    <tr key={l.id}>
                      <td className="whitespace-nowrap">{dateHeure(l.date)}</td>
                      <td>{l.nom || "—"}<span className="block text-xs text-gray-500">{l.email}</span></td>
                      <td><span className={`badge ${couleur}`}>{libelle}</span>{l.raison && l.resultat === "BLOQUE" && <span className="block text-xs text-gray-500">{l.raison}</span>}</td>
                      <td className="font-mono text-xs">{l.ip}</td>
                      <td className="text-xs">{l.appareil}<span className="block font-mono text-gray-500">{l.appareil_id || "—"}</span></td>
                      <td className="whitespace-nowrap text-xs">
                        <span className="mr-1 text-gray-500">IP :</span>
                        <button type="button" className="mr-1 text-green-700 underline" onClick={() => depuisJournal(l, "IP", "AUTORISER")}>autoriser</button>
                        <button type="button" className="text-red-600 underline" onClick={() => depuisJournal(l, "IP", "INTERDIRE")}>interdire</button>
                        {l.appareil_id && (
                          <span className="block">
                            <span className="mr-1 text-gray-500">Appareil :</span>
                            <button type="button" className="mr-1 text-green-700 underline" onClick={() => depuisJournal(l, "APPAREIL", "AUTORISER")}>autoriser</button>
                            <button type="button" className="text-red-600 underline" onClick={() => depuisJournal(l, "APPAREIL", "INTERDIRE")}>interdire</button>
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
