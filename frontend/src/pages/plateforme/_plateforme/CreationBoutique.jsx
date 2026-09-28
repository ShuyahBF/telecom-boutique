// Fenêtre « Créer une boutique » (super-administrateur) : la boutique, son
// identification (pays, ville, GPS, IFU, CNSS, RCCM) et le compte de son DG.
// À la création, le serveur copie aussi tout le catalogue public (sans prix).
import { useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { Champ, ChampsIdentification, erreurCoordonnees, identificationVersApi, TitreSection } from "./composants";
import { PAYS_DEFAUT } from "./outils";

// Formulaire vierge
const CREATION_VIDE = {
  nom: "", telephone: "", email: "", code_marchand: "",
  pays: PAYS_DEFAUT, ville: "", adresse: "", latitude: "", longitude: "", ifu: "", cnss: "", rccm: "",
  dg_nom: "", dg_telephone: "", dg_email: "", dg_mot_de_passe: "",
};

// Mot de passe provisoire lisible (sans 0/O ni 1/l) proposé au DG
function motDePasseAleatoire() {
  const lettres = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789";
  const tirage = crypto.getRandomValues(new Uint32Array(10));
  return Array.from(tirage, (n) => lettres[n % lettres.length]).join("");
}

export default function CreationBoutique({ ouvert, onFermer, onCreee }) {
  const toast = useToast();
  const [f, setF] = useState(CREATION_VIDE);
  const [envoi, setEnvoi] = useState(false);
  const maj = (champ, valeur) => setF((v) => ({ ...v, [champ]: valeur }));

  // Envoi au serveur (POST /plateforme/boutiques)
  async function creer(e) {
    e.preventDefault();
    const erreur = erreurCoordonnees(f);
    if (erreur) return toast.erreur(erreur);
    setEnvoi(true);
    try {
      const { data } = await apiClient.post("/plateforme/boutiques", {
        nom: f.nom.trim(), telephone: f.telephone.trim(), email: f.email.trim() || null,
        code_marchand: f.code_marchand.trim() || null,
        ...identificationVersApi(f),
        dg_email: f.dg_email.trim(), dg_mot_de_passe: f.dg_mot_de_passe,
      });
      // Message de succès : code marchand + nombre de modèles du catalogue copiés
      toast.succes(`Boutique « ${data.boutique.nom} » créée (ID boutique ${data.boutique.code_marchand}) — ${data.produits_copies} modèle(s) du catalogue public copié(s).`);
      setF(CREATION_VIDE);
      onCreee?.(data);
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez les champs (e-mails valides, mot de passe de 8 caractères minimum)"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Modal ouvert={ouvert} titre="Créer une boutique" onFermer={onFermer} large>
      <form onSubmit={creer} className="grid gap-3 sm:grid-cols-2">
        {/* ----- Section 1 : la boutique ----- */}
        <TitreSection premier>🏪 La boutique</TitreSection>
        <Champ label="Nom de la boutique *" className="sm:col-span-2">
          <input className="input" required minLength={2} maxLength={120} value={f.nom} onChange={(e) => maj("nom", e.target.value)} />
        </Champ>
        <Champ label="Téléphone"><input className="input" type="tel" value={f.telephone} onChange={(e) => maj("telephone", e.target.value)} placeholder="70 00 00 00" /></Champ>
        <Champ label="E-mail de la boutique"><input className="input" type="email" value={f.email} onChange={(e) => maj("email", e.target.value)} /></Champ>
        <Champ label="ID boutique (code marchand)" className="sm:col-span-2" aide="Facultatif : laissé vide, un ID unique de 6 caractères est créé automatiquement. C'est cet ID que le personnel tape pour se connecter.">
          <input className="input font-mono uppercase" minLength={6} maxLength={6} pattern="[A-Za-z0-9]{6}" title="6 lettres ou chiffres" value={f.code_marchand}
            onChange={(e) => maj("code_marchand", e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))} />
        </Champ>

        {/* ----- Section 2 : identification & localisation ----- */}
        <TitreSection>📍 Identification & localisation</TitreSection>
        <ChampsIdentification valeurs={f} maj={maj} />

        {/* ----- Section 3 : compte du Directeur Général ----- */}
        <TitreSection>👤 Compte du DG (Directeur Général)</TitreSection>
        <p className="-mt-2 text-xs text-gray-500 sm:col-span-2">Premier compte de la boutique : le DG a tous les droits et crée ensuite les comptes de son équipe.</p>
        <Champ label="Nom du DG *" aide="C'est aussi le nom affiché sur son compte.">
          <input className="input" required minLength={2} maxLength={120} value={f.dg_nom} onChange={(e) => maj("dg_nom", e.target.value)} />
        </Champ>
        <Champ label="Téléphone du DG">
          <input className="input" type="tel" maxLength={30} value={f.dg_telephone} onChange={(e) => maj("dg_telephone", e.target.value)} placeholder="+226 70 00 00 00" />
        </Champ>
        <Champ label="E-mail de connexion du DG *">
          <input className="input" type="email" required autoComplete="off" value={f.dg_email} onChange={(e) => maj("dg_email", e.target.value)} />
        </Champ>
        <Champ label="Mot de passe provisoire *" aide="8 caractères minimum ; à transmettre au DG, qui pourra le changer.">
          <div className="flex gap-2">
            <input className="input font-mono" type="text" required minLength={8} autoComplete="new-password" value={f.dg_mot_de_passe} onChange={(e) => maj("dg_mot_de_passe", e.target.value)} />
            <button type="button" className="btn-outline btn-sm shrink-0" title="Proposer un mot de passe" onClick={() => maj("dg_mot_de_passe", motDePasseAleatoire())}>🎲</button>
          </div>
        </Champ>

        <div className="mt-2 flex flex-col-reverse gap-2 sm:col-span-2 sm:flex-row sm:justify-end">
          <button type="button" className="btn-outline" onClick={onFermer}>Annuler</button>
          <button className="btn-primary" disabled={envoi}>{envoi ? "Création…" : "Créer la boutique"}</button>
        </div>
      </form>
    </Modal>
  );
}
