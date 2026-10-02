// Fenêtre « Comptes & sessions » (super-administrateur) : comptes du personnel
// d'une boutique, fermeture des sessions d'un compte ou de toute la boutique
// (sans changer les mots de passe ni désactiver les comptes), et historique.
import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import { ROLES } from "@/lib/statuts";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import ReglageInactivite from "@/components/ReglageInactivite";

// Actions de fermeture des sessions notées dans le journal des identifiants
const ACTIONS_SESSIONS = ["SESSIONS_FERMEES", "SESSIONS_BOUTIQUE_FERMEES", "SESSIONS_AUTRES_FERMEES"];

/** boutique : boutique affichée (null = fenêtre fermée) */
export default function SessionsBoutique({ boutique, onFermer }) {
  const toast = useToast();
  const [comptes, setComptes] = useState(null);
  const [journal, setJournal] = useState([]);
  const [occupe, setOccupe] = useState(""); // id du compte en cours, ou "tous"

  const id = boutique?.id;
  const charger = useCallback(() => {
    if (!id) return;
    apiClient.get(`/plateforme/boutiques/${id}/comptes`)
      .then(({ data }) => setComptes(data))
      .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger les comptes")));
    apiClient.get("/plateforme/journal-identifiants", { params: { boutique_id: id } })
      .then(({ data }) => setJournal(data.filter((l) => ACTIONS_SESSIONS.includes(l.action)).slice(0, 20)))
      .catch(() => setJournal([]));
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setComptes(null); charger(); }, [charger]);

  if (!boutique) return null;

  async function fermer(chemin, question, cle) {
    if (!window.confirm(question)) return;
    setOccupe(cle);
    try {
      const { data } = await apiClient.post(chemin);
      toast.succes(data.message || "Sessions fermées");
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Impossible de fermer les sessions"));
    } finally {
      setOccupe("");
    }
  }

  const base = `/plateforme/boutiques/${boutique.id}`;
  return (
    <Modal ouvert titre={`Comptes & sessions — ${boutique.nom}`} onFermer={onFermer} large>
      <div className="space-y-5 text-sm">
        <p className="text-gray-600">
          Déconnecte un compte de tous ses appareils (téléphone perdu, poste partagé…) <b>sans changer son mot de passe</b> ni
          le désactiver. La personne voit « Votre session a été fermée par un administrateur » et se reconnecte normalement.
        </p>
        <button type="button" className="btn-danger w-full sm:w-auto" disabled={!!occupe || !comptes?.length}
          onClick={() => fermer(`${base}/fermer-sessions`, `Fermer les sessions de TOUS les comptes de « ${boutique.nom} » ? Chacun devra se reconnecter.`, "tous")}>
          {occupe === "tous" ? "Fermeture…" : "🚪 Fermer toutes les sessions de la boutique"}
        </button>

        {comptes === null ? <p className="text-gray-500">Chargement…</p> : (
          <ul className="divide-y divide-gray-100 rounded-xl border border-gray-200">
            {comptes.map((c) => (
              <li key={c.id} className={`flex flex-wrap items-center gap-3 p-3 ${c.actif === false ? "opacity-60" : ""}`}>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{c.nom} <span className="text-xs font-normal text-gray-500">· {ROLES[c.role] || c.role}{c.actif === false ? " · désactivé" : ""}</span></p>
                  <p className="truncate text-xs text-gray-500">{[c.telephone, c.email].filter(Boolean).join(" · ")}</p>
                </div>
                <button type="button" className="btn-outline btn-sm" disabled={!!occupe}
                  onClick={() => fermer(`${base}/comptes/${c.id}/fermer-sessions`, `Fermer les sessions de ${c.nom} sur tous ses appareils ?`, c.id)}>
                  {occupe === c.id ? "Fermeture…" : "🚪 Fermer ses sessions"}
                </button>
              </li>
            ))}
            {!comptes.length && <li className="p-3 text-gray-500">Aucun compte.</li>}
          </ul>
        )}

        {/* Déconnexion après inactivité propre à cette boutique */}
        <section>
          <h3 className="mb-2 font-bold">⏳ Déconnexion après inactivité</h3>
          <ReglageInactivite mode="boutique" boutiqueId={boutique.id} />
        </section>

        {/* Historique des fermetures de sessions (journal des identifiants) */}
        <section>
          <h3 className="mb-2 font-bold">Historique des fermetures</h3>
          {journal.length === 0 ? <p className="text-gray-500">Aucune fermeture enregistrée.</p> : (
            <ul className="divide-y">
              {journal.map((l) => (
                <li key={l.id} className="py-2">
                  <span className="text-gray-500">{dateHeure(l.date)}</span> · <b>{l.libelle}</b>
                  {l.user_nom && <> · {l.user_nom}</>}
                  {l.details?.nb_comptes !== undefined && <> · {l.details.nb_comptes} compte(s)</>}
                  {l.par_nom && <span className="text-gray-500"> · par {l.par_nom}</span>}
                  {l.ip && <span className="text-gray-500"> · IP {l.ip}</span>}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Modal>
  );
}
