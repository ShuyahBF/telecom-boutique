import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { DESCRIPTIONS_ROLES, ROLES } from "@/lib/statuts";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { Champ } from "./communs";

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

  // Ajout d'un membre (POST /boutique/equipe)
  async function ajouter(e) {
    e.preventDefault();
    try {
      await apiClient.post("/boutique/equipe", ajout);
      toast.succes(`Compte créé pour ${ajout.nom}`);
      setAjout(null);
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez le nom, l'e-mail et le mot de passe (8 caractères minimum)"));
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
          <button type="button" className="btn-primary" onClick={() => setAjout({ nom: "", email: "", mot_de_passe: "", role: "commercial" })}>+ Ajouter un membre</button>
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
                  <p className="truncate text-sm text-gray-500">{m.email}</p>
                </div>
                <select className="input w-auto py-1.5 text-sm" value={m.role} disabled={moi} aria-label="Rôle"
                  onChange={(e) => modifier(m, { role: e.target.value }, `Rôle : ${ROLES[e.target.value]}`)}>
                  {ROLES_BOUTIQUE.map(([r]) => <option key={r} value={r}>{ROLES[r]}</option>)}
                </select>
                <button type="button" className="btn-outline btn-sm" onClick={() => setMotDePasse({ membre: m, valeur: "" })}>🔑 Mot de passe</button>
                {!moi && (m.actif === false
                  ? <button type="button" className="btn-outline btn-sm text-green-700" onClick={() => modifier(m, { actif: true }, "Compte réactivé")}>Réactiver</button>
                  : <button type="button" className="btn-outline btn-sm text-red-600" onClick={() => window.confirm(`Désactiver le compte de ${m.nom} ? Il ne pourra plus se connecter.`) && modifier(m, { actif: false }, "Compte désactivé")}>Désactiver</button>)}
              </div>
            );
          })}
        </div>
      </div>

      {/* Explication des rôles */}
      <div className="card h-fit text-sm">
        <h2 className="mb-2 font-bold">Les rôles</h2>
        <ul className="space-y-2">
          {ROLES_BOUTIQUE.map(([r, texte]) => <li key={r}><b>{ROLES[r]}</b> : {texte}</li>)}
        </ul>
      </div>

      {/* Fenêtre d'ajout d'un membre */}
      <Modal ouvert={!!ajout} titre="Nouveau membre de l'équipe" onFermer={() => setAjout(null)}>
        {ajout && (
          <form onSubmit={ajouter} className="space-y-3">
            <Champ label="Nom complet"><input className="input" required minLength={2} value={ajout.nom} onChange={(e) => setAjout({ ...ajout, nom: e.target.value })} /></Champ>
            <Champ label="E-mail (identifiant de connexion)"><input className="input" type="email" required value={ajout.email} onChange={(e) => setAjout({ ...ajout, email: e.target.value })} /></Champ>
            <Champ label="Mot de passe" aide="Mot de passe PROVISOIRE (8 caractères minimum) : communiquez-le à la personne avec l'ID boutique ; elle devra le changer à sa première connexion."><input className="input" type="text" required minLength={8} autoComplete="new-password" value={ajout.mot_de_passe} onChange={(e) => setAjout({ ...ajout, mot_de_passe: e.target.value })} /></Champ>
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

      {/* Fenêtre de changement de mot de passe */}
      <Modal ouvert={!!motDePasse} titre={`Nouveau mot de passe — ${motDePasse?.membre.nom || ""}`} onFermer={() => setMotDePasse(null)}>
        {motDePasse && (
          <form onSubmit={changerMotDePasse} className="space-y-3">
            <Champ label="Nouveau mot de passe" aide="Provisoire (8 caractères minimum) : la personne devra le changer à sa prochaine connexion."><input className="input" type="text" required minLength={8} autoComplete="new-password" value={motDePasse.valeur} onChange={(e) => setMotDePasse({ ...motDePasse, valeur: e.target.value })} /></Champ>
            <button className="btn-primary w-full">Enregistrer</button>
          </form>
        )}
      </Modal>
    </div>
  );
}
