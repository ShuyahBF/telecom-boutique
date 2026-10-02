import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { DESCRIPTIONS_ROLES, ROLES } from "@/lib/statuts";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { dateHeure } from "@/lib/format";
import { Champ } from "./communs";
import ChampMotDePasse from "@/components/ChampMotDePasse";

// Canaux d'envoi des accès provisoires (WhatsApp en priorité, puis SMS, puis e-mail)
const CANAUX = { WHATSAPP: "WhatsApp", SMS: "SMS", EMAIL: "e-mail" };
const STATUTS = { ENVOYE: "envoyé", ECHEC: "échec", NON_CONFIGURE: "non configuré" };

// Phrase lisible du résultat réel d'un envoi (renvoyé par le serveur)
function texteEnvoi(envoi) {
  if (!envoi) return "";
  if (envoi.statut === "ENVOYE") return `Accès envoyés par ${CANAUX[envoi.canal]}.`;
  const essais = (envoi.essais || []).map((e) => `${CANAUX[e.canal]} : ${STATUTS[e.statut] || e.statut}`).join(" · ");
  return `Aucun message n'a pu partir${essais ? ` (${essais})` : ""}.`;
}

// Les 5 rôles qu'un DG peut attribuer (DG, commercial, secrétaire, comptable,
// technicien), avec leur description en une ligne (définies dans lib/statuts.js)
const ROLES_BOUTIQUE = Object.entries(DESCRIPTIONS_ROLES);

// Onglet « Équipe » : comptes du personnel de la boutique.
export default function ParamEquipe() {
  const { user } = useAuth();
  const toast = useToast();
  const [membres, setMembres] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [ajout, setAjout] = useState(null); // formulaire d'ajout (null = fenêtre fermée)
  const [motDePasse, setMotDePasse] = useState(null); // { membre, valeur } : nouveau mot de passe
  const [identifiants, setIdentifiants] = useState(null); // { membre, email, telephone } : identifiants de connexion
  const [resultat, setResultat] = useState(null); // { nom, envoi } : résultat d'un envoi d'accès provisoires
  const [journal, setJournal] = useState(null); // historique des actions sur les identifiants (null = masqué)

  // Chargement des membres (GET /boutique/equipe)
  const charger = useCallback(() => {
    apiClient.get("/boutique/equipe")
      .then(({ data }) => setMembres(data))
      .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger l'équipe")))
      .finally(() => setChargement(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  // Modification d'un membre (PATCH /boutique/equipe/{id}) : rôle, activation, mot de passe
  async function modifier(membre, changements, message) {
    try {
      const { data } = await apiClient.patch(`/boutique/equipe/${membre.id}`, changements);
      setMembres((liste) => liste.map((m) => (m.id === data.id ? data : m)));
      toast.succes(message);
      return true;
    } catch (err) {
      toast.erreur(messageErreur(err, "Modification impossible"));
      return false;
    }
  }

  // Ajout d'un membre (POST /boutique/equipe) : e-mail et/ou téléphone ; ses accès
  // provisoires lui sont envoyés (WhatsApp, sinon SMS, sinon e-mail)
  async function ajouter(e) {
    e.preventDefault();
    if (!ajout.email.trim() && !ajout.telephone.trim()) return toast.erreur("Indiquez l'e-mail ou le téléphone de la personne (au moins l'un des deux).");
    try {
      const { data } = await apiClient.post("/boutique/equipe", ajout);
      toast.succes(`Compte créé pour ${ajout.nom}`);
      setResultat({ nom: ajout.nom, envoi: data.envoi });
      setAjout(null);
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez le nom, l'e-mail ou le téléphone, et le mot de passe (8 caractères minimum)"));
    }
  }

  // Modification de l'e-mail / du téléphone d'un membre (il en est prévenu sur l'ancien et le nouveau contact)
  async function enregistrerIdentifiants(e) {
    e.preventDefault();
    const { membre, email, telephone } = identifiants;
    const changements = {};
    if (email.trim() !== (membre.email || "")) changements.email = email.trim();
    if (telephone.trim() !== (membre.telephone || "")) changements.telephone = telephone.trim();
    if (!Object.keys(changements).length) return setIdentifiants(null);
    if (await modifier(membre, changements, "Identifiants modifiés : la personne en a été prévenue")) setIdentifiants(null);
  }

  // Nouveau mot de passe provisoire tiré au hasard et envoyé au membre
  async function envoyerNouveauMotDePasse(m) {
    if (!window.confirm(`Envoyer un NOUVEAU mot de passe provisoire à ${m.nom} (WhatsApp, sinon SMS ou e-mail) ? L'actuel ne fonctionnera plus.`)) return;
    try {
      const { data } = await apiClient.post(`/boutique/equipe/${m.id}/nouveau-mot-de-passe`);
      setResultat({ nom: m.nom, envoi: data.envoi });
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi impossible"));
    }
  }

  // Historique des actions sur les identifiants (affiché à la demande)
  async function basculerJournal() {
    if (journal) return setJournal(null);
    try {
      setJournal((await apiClient.get("/boutique/equipe/journal-identifiants")).data);
    } catch (err) {
      toast.erreur(messageErreur(err, "Impossible de charger l'historique"));
    }
  }

  // Changement de mot de passe d'un membre
  async function changerMotDePasse(e) {
    e.preventDefault();
    if (await modifier(motDePasse.membre, { mot_de_passe: motDePasse.valeur }, "Mot de passe modifié")) setMotDePasse(null);
  }

  if (chargement) return <Chargement />;

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="font-bold">{membres.length} membre(s)</h2>
          <button type="button" className="btn-primary" onClick={() => setAjout({ nom: "", email: "", telephone: "", mot_de_passe: "", role: "commercial" })}>+ Ajouter un membre</button>
        </div>

        {/* Une carte par membre (lisible aussi sur téléphone) */}
        <div className="space-y-3">
          {membres.map((m) => {
            const moi = m.id === user.id;
            return (
              <div key={m.id} className={`card flex flex-wrap items-center gap-3 p-4 ${m.actif === false ? "opacity-60" : ""}`}>
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 font-bold text-primary">{m.nom.slice(0, 1).toUpperCase()}</span>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{m.nom}{moi && <span className="ml-2 text-xs text-gray-500">(vous)</span>}</p>
                  <p className="truncate text-sm text-gray-500">{[m.telephone && `📱 ${m.telephone}`, m.email && `✉️ ${m.email}`].filter(Boolean).join(" · ")}</p>
                </div>
                <select className="input w-auto py-1.5 text-sm" value={m.role} disabled={moi} aria-label="Rôle"
                  onChange={(e) => modifier(m, { role: e.target.value }, `Rôle : ${ROLES[e.target.value]}`)}>
                  {ROLES_BOUTIQUE.map(([r]) => <option key={r} value={r}>{ROLES[r]}</option>)}
                </select>
                {!moi && <button type="button" className="btn-outline btn-sm" onClick={() => setIdentifiants({ membre: m, email: m.email || "", telephone: m.telephone || "" })}>✏️ Identifiants</button>}
                {!moi && <button type="button" className="btn-outline btn-sm" onClick={() => envoyerNouveauMotDePasse(m)}>📲 Nouveau mot de passe</button>}
                <button type="button" className="btn-outline btn-sm" onClick={() => setMotDePasse({ membre: m, valeur: "" })}>🔑 Saisir un mot de passe</button>
                {!moi && (m.actif === false
                  ? <button type="button" className="btn-outline btn-sm text-green-700" onClick={() => modifier(m, { actif: true }, "Compte réactivé")}>Réactiver</button>
                  : <button type="button" className="btn-outline btn-sm text-red-600" onClick={() => window.confirm(`Désactiver le compte de ${m.nom} ? Il ne pourra plus se connecter.`) && modifier(m, { actif: false }, "Compte désactivé")}>Désactiver</button>)}
              </div>
            );
          })}
        </div>
      </div>

      {/* Explication des rôles et des identifiants */}
      <div className="space-y-5">
        <div className="card h-fit text-sm">
          <h2 className="mb-2 font-bold">Les rôles</h2>
          <ul className="space-y-2">
            {ROLES_BOUTIQUE.map(([r, texte]) => <li key={r}><b>{ROLES[r]}</b> : {texte}</li>)}
          </ul>
        </div>
        <div className="card h-fit text-sm">
          <h2 className="mb-2 font-bold">Connexion de l'équipe</h2>
          <p className="text-gray-600">Chacun se connecte avec l'<b>ID boutique</b> + son <b>e-mail ou son téléphone</b>. Mot de passe oublié : lien « Mot de passe oublié ? » de la page de connexion (code par WhatsApp), ou bouton 📲 ici.</p>
          <button type="button" className="btn-outline btn-sm mt-3" onClick={basculerJournal}>{journal ? "Masquer l'historique" : "📜 Historique des identifiants"}</button>
        </div>
      </div>

      {/* Historique des actions sur les identifiants (sans aucun code ni mot de passe) */}
      {journal && (
        <div className="card text-sm lg:col-span-3">
          <h2 className="mb-2 font-bold">Historique des identifiants</h2>
          {journal.length === 0 ? <p className="text-gray-500">Aucune action enregistrée.</p> : (
            <ul className="divide-y">
              {journal.map((l) => (
                <li key={l.id} className="py-2">
                  <span className="text-gray-500">{dateHeure(l.date)}</span> · <b>{l.libelle}</b>
                  {l.user_nom && <> · {l.user_nom}</>}{l.identifiant && <> ({l.identifiant})</>}
                  {l.details?.type && <> · {l.details.type === "email" ? "e-mail" : "téléphone"}{l.details.nouveau ? ` → ${l.details.nouveau}` : ""}</>}
                  {l.canal && <> · {CANAUX[l.canal] || l.canal}</>}{l.statut && <> · {STATUTS[l.statut] || l.statut}</>}
                  {l.par_nom && <span className="text-gray-500"> · par {l.par_nom}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Fenêtre d'ajout d'un membre */}
      <Modal ouvert={!!ajout} titre="Nouveau membre de l'équipe" onFermer={() => setAjout(null)}>
        {ajout && (
          <form onSubmit={ajouter} className="space-y-3">
            <Champ label="Nom complet"><input className="input" required minLength={2} value={ajout.nom} onChange={(e) => setAjout({ ...ajout, nom: e.target.value })} /></Champ>
            <Champ label="Téléphone (WhatsApp)" aide="Sert d'identifiant de connexion ; les accès y sont envoyés par WhatsApp (sinon par SMS)."><input className="input" type="tel" placeholder="70 12 34 56" value={ajout.telephone} onChange={(e) => setAjout({ ...ajout, telephone: e.target.value })} /></Champ>
            <Champ label="E-mail (facultatif si un téléphone est indiqué)"><input className="input" type="email" value={ajout.email} onChange={(e) => setAjout({ ...ajout, email: e.target.value })} /></Champ>
            <Champ label="Mot de passe provisoire (facultatif)" aide="Laissez vide : un mot de passe provisoire est créé et envoyé à la personne avec l'ID boutique. Elle devra le changer à sa première connexion."><ChampMotDePasse visibleParDefaut minLength={8} autoComplete="new-password" value={ajout.mot_de_passe} onChange={(e) => setAjout({ ...ajout, mot_de_passe: e.target.value })} /></Champ>
            <Champ label="Rôle">
              <select className="input" value={ajout.role} onChange={(e) => setAjout({ ...ajout, role: e.target.value })}>
                {ROLES_BOUTIQUE.map(([r]) => <option key={r} value={r}>{ROLES[r]}</option>)}
              </select>
            </Champ>
            <p className="text-xs text-gray-500">{ROLES_BOUTIQUE.find(([r]) => r === ajout.role)?.[1]}</p>
            <button className="btn-primary w-full">Créer le compte</button>
          </form>
        )}
      </Modal>

      {/* Fenêtre de modification des identifiants d'un membre */}
      <Modal ouvert={!!identifiants} titre={`Identifiants de connexion — ${identifiants?.membre.nom || ""}`} onFermer={() => setIdentifiants(null)}>
        {identifiants && (
          <form onSubmit={enregistrerIdentifiants} className="space-y-3">
            <Champ label="Téléphone (WhatsApp)" aide="Vide = retirer. Il doit rester au moins un identifiant."><input className="input" type="tel" value={identifiants.telephone} onChange={(e) => setIdentifiants({ ...identifiants, telephone: e.target.value })} /></Champ>
            <Champ label="E-mail" aide="Vide = retirer."><input className="input" type="email" value={identifiants.email} onChange={(e) => setIdentifiants({ ...identifiants, email: e.target.value })} /></Champ>
            <p className="text-xs text-gray-500">Vous en êtes responsable : aucun code n'est demandé, mais la personne est prévenue sur son ancien et son nouveau contact.</p>
            <button className="btn-primary w-full">Enregistrer</button>
          </form>
        )}
      </Modal>

      {/* Résultat réel de l'envoi des accès provisoires */}
      <Modal ouvert={!!resultat} titre={`Accès de ${resultat?.nom || ""}`} onFermer={() => setResultat(null)}>
        {resultat && (
          <div className="space-y-3 text-sm">
            <p className={`rounded-lg p-2 ${resultat.envoi?.statut === "ENVOYE" ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-800"}`}>{texteEnvoi(resultat.envoi)}</p>
            {resultat.envoi?.mot_de_passe_provisoire && (
              <div className="rounded-lg border border-amber-300 p-3">
                <p>Remettez-lui ce mot de passe provisoire en main propre, avec l'ID boutique :</p>
                <p className="mt-2 text-center font-mono text-xl font-bold tracking-wider">{resultat.envoi.mot_de_passe_provisoire}</p>
                <p className="mt-2 text-xs text-gray-500">Il ne sera plus affiché après la fermeture de cette fenêtre.</p>
              </div>
            )}
            <button type="button" className="btn-primary w-full" onClick={() => setResultat(null)}>Fermer</button>
          </div>
        )}
      </Modal>

      {/* Fenêtre de changement de mot de passe */}
      <Modal ouvert={!!motDePasse} titre={`Nouveau mot de passe — ${motDePasse?.membre.nom || ""}`} onFermer={() => setMotDePasse(null)}>
        {motDePasse && (
          <form onSubmit={changerMotDePasse} className="space-y-3">
            <Champ label="Nouveau mot de passe" aide="Provisoire (8 caractères minimum) : la personne devra le changer à sa prochaine connexion."><ChampMotDePasse visibleParDefaut required minLength={8} autoComplete="new-password" value={motDePasse.valeur} onChange={(e) => setMotDePasse({ ...motDePasse, valeur: e.target.value })} /></Champ>
            <button className="btn-primary w-full">Enregistrer</button>
          </form>
        )}
      </Modal>
    </div>
  );
}
