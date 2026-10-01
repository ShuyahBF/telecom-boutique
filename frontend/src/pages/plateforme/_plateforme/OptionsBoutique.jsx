// Fenêtre « Barre latérale & Caisse Aizenta » d'une boutique (super-administrateur) :
// 1. options de la barre latérale (menu du back-office) : un interrupteur par option,
//    « Tout activer / Tout désactiver » ; « Tableau de bord » et « Caisse Aizenta »
//    sont obligatoires (cochées et grisées). Chaque changement est journalisé.
// 2. Caisse Aizenta : adresse du webhook, jeton de la boutique (généré ici, affiché
//    UNE SEULE FOIS) et journal des réceptions envoyées par Loois.
import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";

/**
 * boutique : la boutique affichée (null = fenêtre fermée)
 * onMaj()  : appelé après un enregistrement (pour recharger la liste des boutiques)
 */
export default function OptionsBoutique({ boutique, onFermer, onMaj }) {
  const toast = useToast();
  const [etat, setEtat] = useState(null); // réponse du serveur (options + journal)
  const [choix, setChoix] = useState({}); // interrupteurs en cours de modification
  const [caisse, setCaisse] = useState(null); // jeton + journal des réceptions
  const [jetonAffiche, setJetonAffiche] = useState(""); // jeton tout juste généré (montré une fois)
  const [occupe, setOccupe] = useState("");

  const id = boutique?.id;
  const charger = useCallback(async () => {
    if (!id) return;
    try {
      const [o, c] = await Promise.all([
        apiClient.get(`/plateforme/boutiques/${id}/options-sidebar`),
        apiClient.get(`/plateforme/caisse-aizenta/boutiques/${id}`),
      ]);
      setEtat(o.data);
      setChoix(Object.fromEntries(o.data.options.map((x) => [x.cle, x.active])));
      setCaisse(c.data);
    } catch (err) {
      toast.erreur(messageErreur(err, "Chargement impossible"));
    }
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setEtat(null);
    setCaisse(null);
    setJetonAffiche("");
    charger();
  }, [charger]);

  if (!boutique) return null;

  // --- Options de la barre latérale ---
  const modifie = etat && etat.options.some((o) => choix[o.cle] !== o.active);
  function toutCocher(valeur) {
    setChoix(Object.fromEntries(etat.options.map((o) => [o.cle, o.obligatoire ? true : valeur])));
  }

  async function enregistrer() {
    setOccupe("options");
    try {
      // On n'envoie que les options non obligatoires (les obligatoires restent actives)
      const options = Object.fromEntries(etat.options.filter((o) => !o.obligatoire).map((o) => [o.cle, !!choix[o.cle]]));
      const { data } = await apiClient.put(`/plateforme/boutiques/${id}/options-sidebar`, { options });
      setEtat(data);
      setChoix(Object.fromEntries(data.options.map((x) => [x.cle, x.active])));
      toast.succes("Options de la barre latérale enregistrées");
      onMaj?.();
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible"));
    } finally {
      setOccupe("");
    }
  }

  // --- Jeton de la caisse Aizenta ---
  async function genererJeton() {
    if (caisse?.jeton && !window.confirm("Régénérer le jeton ? L'ancien cessera aussitôt de fonctionner : il faudra saisir le nouveau dans Loois.")) return;
    setOccupe("jeton");
    try {
      const { data } = await apiClient.post(`/plateforme/caisse-aizenta/boutiques/${id}/jeton`);
      setJetonAffiche(data.jeton);
      setCaisse((c) => ({ ...c, jeton: { apercu: data.apercu, cree_le: data.cree_le, par: data.par } }));
      toast.succes("Jeton généré : copiez-le maintenant, il ne sera plus affiché");
    } catch (err) {
      toast.erreur(messageErreur(err, "Génération impossible"));
    } finally {
      setOccupe("");
    }
  }

  async function revoquerJeton() {
    if (!window.confirm("Révoquer le jeton ? Loois ne pourra plus envoyer de données (celles déjà reçues sont conservées).")) return;
    try {
      await apiClient.delete(`/plateforme/caisse-aizenta/boutiques/${id}/jeton`);
      setCaisse((c) => ({ ...c, jeton: null }));
      setJetonAffiche("");
      toast.succes("Jeton révoqué");
    } catch (err) {
      toast.erreur(messageErreur(err, "Révocation impossible"));
    }
  }

  function copier(texte) {
    navigator.clipboard?.writeText(texte).then(() => toast.succes("Copié"), () => toast.erreur("Copie impossible : sélectionnez le texte"));
  }

  return (
    <Modal ouvert titre={`Barre latérale & Caisse Aizenta — ${boutique.nom}`} onFermer={onFermer} large>
      {!etat || !caisse ? <Chargement /> : (
        <div className="space-y-6">
          {/* ===== 1. Options de la barre latérale ===== */}
          <section>
            <h3 className="mb-1 text-base font-bold">1. Options de la barre latérale</h3>
            <p className="mb-3 text-xs text-gray-500">
              Une option désactivée disparaît du menu de la boutique et ses écrans sont bloqués (y compris par le serveur).
              Les données ne sont jamais supprimées. Les droits par rôle s'appliquent en plus.
            </p>
            {etat.historique && (
              <p className="mb-3 rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
                Boutique créée avant cette fonction : <b>tout est activé</b> tant que vous n'enregistrez pas un réglage.
              </p>
            )}
            <div className="mb-3 flex flex-wrap gap-2">
              <button type="button" className="btn-outline btn-sm" onClick={() => toutCocher(true)}>Tout activer</button>
              <button type="button" className="btn-outline btn-sm" onClick={() => toutCocher(false)}>Tout désactiver</button>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {etat.options.map((o) => (
                <label key={o.cle} className={`flex items-center justify-between gap-3 rounded-xl border px-3 py-2 text-sm ${o.obligatoire ? "bg-gray-50 text-gray-500" : "cursor-pointer hover:bg-gray-50"}`}>
                  <span>{o.libelle}{o.obligatoire && <span className="ml-1 text-xs">(obligatoire)</span>}</span>
                  <input type="checkbox" className="h-5 w-5" checked={!!choix[o.cle]} disabled={o.obligatoire}
                    onChange={(e) => setChoix((c) => ({ ...c, [o.cle]: e.target.checked }))} />
                </label>
              ))}
            </div>
            <div className="mt-3 text-right">
              <button type="button" className="btn-primary w-full sm:w-auto" disabled={!modifie || occupe === "options"} onClick={enregistrer}>
                {occupe === "options" ? "Enregistrement…" : "Enregistrer les options"}
              </button>
            </div>

            {/* Journal des changements (qui, quand, avant -> après) */}
            {etat.journal.length > 0 && (
              <details className="mt-3 rounded-xl border border-gray-200 p-3 text-sm">
                <summary className="cursor-pointer font-semibold">Journal des changements ({etat.journal.length})</summary>
                <ul className="mt-2 space-y-2">
                  {etat.journal.map((j) => (
                    <li key={j.id} className="border-t border-gray-100 pt-2">
                      <p className="text-xs text-gray-500">{dateHeure(j.date)} — {j.par_nom || j.par}</p>
                      <p>{j.changements.map((c) => `${c.libelle} : ${c.avant ? "activée" : "désactivée"} → ${c.apres ? "activée" : "désactivée"}`).join(" · ")}</p>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>

          {/* ===== 2. Caisse Aizenta (Loois) ===== */}
          <section className="border-t border-gray-200 pt-5">
            <h3 className="mb-1 text-base font-bold">2. Caisse Aizenta (réception depuis Loois)</h3>
            <p className="mb-3 text-xs text-gray-500">À saisir dans Loois : l'adresse du webhook, l'ID boutique et le jeton ci-dessous.</p>
            <dl className="grid gap-2 text-sm sm:grid-cols-[auto_1fr]">
              <dt className="font-semibold">Adresse du webhook</dt>
              <dd className="flex items-center gap-2"><code className="break-all rounded bg-gray-100 px-1">{caisse.webhook_url}</code>
                <button type="button" className="btn-outline btn-sm" onClick={() => copier(caisse.webhook_url)}>Copier</button></dd>
              <dt className="font-semibold">ID boutique</dt>
              <dd className="font-mono">{caisse.code_boutique}</dd>
              <dt className="font-semibold">Jeton</dt>
              <dd>{caisse.jeton ? <>{caisse.jeton.apercu} <span className="text-xs text-gray-500">créé le {dateHeure(caisse.jeton.cree_le)}{caisse.jeton.par ? ` par ${caisse.jeton.par}` : ""}</span></> : <span className="text-amber-700">aucun jeton : la réception est fermée</span>}</dd>
              <dt className="font-semibold">Opérations reçues</dt>
              <dd>{caisse.nb_operations}</dd>
            </dl>

            {jetonAffiche && (
              <div className="mt-3 rounded-xl border border-green-300 bg-green-50 p-3 text-sm">
                <p className="font-semibold text-green-900">Nouveau jeton — copiez-le maintenant, il ne sera plus jamais affiché :</p>
                <div className="mt-2 flex items-center gap-2">
                  <code className="flex-1 break-all rounded bg-white px-2 py-1 font-mono">{jetonAffiche}</code>
                  <button type="button" className="btn-primary btn-sm" onClick={() => copier(jetonAffiche)}>Copier</button>
                </div>
              </div>
            )}

            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="btn-primary btn-sm" disabled={occupe === "jeton"} onClick={genererJeton}>
                {caisse.jeton ? "🔑 Régénérer le jeton" : "🔑 Générer le jeton"}
              </button>
              {caisse.jeton && <button type="button" className="btn-outline btn-sm text-red-600" onClick={revoquerJeton}>Révoquer le jeton</button>}
              <button type="button" className="btn-outline btn-sm" onClick={charger}>↻ Actualiser</button>
            </div>

            {/* Journal des réceptions */}
            <h4 className="mb-2 mt-4 text-sm font-bold">Dernières réceptions</h4>
            {caisse.receptions.length === 0 ? <p className="text-sm text-gray-500">Aucune réception pour l'instant.</p> : (
              <div className="overflow-x-auto rounded-xl border border-gray-200">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 text-left uppercase text-gray-500">
                    <tr><th className="px-3 py-2">Date</th><th className="px-3 py-2">Résultat</th><th className="px-3 py-2">Période</th><th className="px-3 py-2 text-right">Lignes</th><th className="px-3 py-2">Détail</th></tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {caisse.receptions.map((r) => (
                      <tr key={r.id} className={r.resultat === "ACCEPTEE" ? "" : "bg-red-50/50"}>
                        <td className="whitespace-nowrap px-3 py-2">{dateHeure(r.date)}</td>
                        <td className="px-3 py-2">{r.resultat === "ACCEPTEE" ? "✅ Acceptée" : `❌ Refusée (${r.code_http})`}</td>
                        <td className="whitespace-nowrap px-3 py-2">{r.periode ? `${r.periode.du} → ${r.periode.au}` : "—"}</td>
                        <td className="px-3 py-2 text-right">{r.nb_operations ?? "—"}</td>
                        <td className="px-3 py-2 text-gray-600">
                          {r.resultat === "ACCEPTEE"
                            ? `${r.operations_nouvelles} nouvelle(s), ${r.operations_mises_a_jour} mise(s) à jour${r.operations_supprimees ? `, ${r.operations_supprimees} supprimée(s)` : ""}${r.remplacer_periode ? " (période remplacée)" : ""}`
                            : [r.detail, ...(r.erreurs || [])].filter(Boolean).join(" · ")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </Modal>
  );
}
