import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { aLeRole, useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, dateHeure, prix } from "@/lib/format";
import { STATUTS_SAV } from "@/lib/statuts";
import EnTetePage from "@/components/EnTetePage";
import Chargement from "@/components/Chargement";
import Badge from "@/components/Badge";
import ClientSelect from "@/components/ClientSelect";
import ProduitSelect from "@/components/ProduitSelect";
import { useToast } from "@/components/Toast";
import { Case, Champ, lienWhatsApp } from "./_atelier/communs";

// Recherche de pièces : uniquement les produits de type « Pièce détachée ».
// Définie hors du composant pour que ProduitSelect ne relance pas sa recherche en boucle.
const pieceDetachee = (p) => p.type_produit === "PIE";

// Champs d'un dossier vierge (mêmes noms que DossierSaisie côté API)
const DOSSIER_VIDE = {
  marque: "", modele: "", imei: "", couleur: "", code_deverrouillage: "", accessoires_deposes: "",
  etat_visuel: "", panne_declaree: "", date_prevue: "", technicien_id: "",
  diagnostic: "", travaux_effectues: "", devis_montant: "", devis_accepte: null, acompte: 0, sous_garantie: false,
};

// Convertit le formulaire en données attendues par l'API (POST et PUT /maintenance).
// Le PUT remplace TOUT le dossier : on renvoie donc toujours tous les champs.
function versApi(saisie, client) {
  return {
    client_id: client?.id,
    marque: saisie.marque, modele: saisie.modele, imei: saisie.imei, couleur: saisie.couleur,
    code_deverrouillage: saisie.code_deverrouillage, accessoires_deposes: saisie.accessoires_deposes,
    etat_visuel: saisie.etat_visuel, panne_declaree: saisie.panne_declaree,
    date_prevue: saisie.date_prevue || null, technicien_id: saisie.technicien_id || null,
    diagnostic: saisie.diagnostic, travaux_effectues: saisie.travaux_effectues,
    devis_montant: saisie.devis_montant === "" || saisie.devis_montant === null ? null : Number(saisie.devis_montant),
    devis_accepte: saisie.devis_accepte, acompte: Number(saisie.acompte) || 0, sous_garantie: !!saisie.sous_garantie,
  };
}

// Fiche d'un dossier de réparation : formulaire de dépôt (nouveau) ou suivi complet (existant).
export default function DossierFiche() {
  const { id } = useParams();
  const creation = !id;
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { user, boutique } = useAuth();
  const peutFacturer = aLeRole(user, "gerant", "vendeur"); // le technicien ne facture pas
  const devise = boutique?.devise || "FCFA";

  // --- État ---
  const [dossier, setDossier] = useState(null); // dossier tel qu'enregistré (fiche existante)
  const [saisie, setSaisie] = useState(DOSSIER_VIDE); // valeurs du formulaire
  const [client, setClient] = useState(null);
  const [equipe, setEquipe] = useState([]);
  const [statuts, setStatuts] = useState({});
  const [chargement, setChargement] = useState(!creation);
  const [occupe, setOccupe] = useState(false);

  // Liste des techniciens possibles (techniciens et gérants actifs) + libellés des statuts
  useEffect(() => {
    apiClient.get("/boutique/equipe")
      .then(({ data }) => setEquipe(data.filter((m) => ["technicien", "gerant"].includes(m.role) && m.actif !== false)))
      .catch(() => {});
    apiClient.get("/maintenance/statuts").then(({ data }) => setStatuts(data)).catch(() => {});
  }, []);

  // Nouveau dépôt depuis une fiche client (?client=<id>) : client pré-rempli
  const clientDemande = params.get("client");
  useEffect(() => {
    if (!creation || !clientDemande) return;
    apiClient.get(`/clients/${clientDemande}`).then(({ data }) => setClient(data)).catch(() => {});
  }, [creation, clientDemande]);

  // Remplit le formulaire à partir d'un dossier renvoyé par l'API
  function afficher(d) {
    setDossier(d);
    setClient({ id: d.client_id, ...d.client });
    const valeurs = {};
    for (const k of Object.keys(DOSSIER_VIDE)) valeurs[k] = d[k] ?? DOSSIER_VIDE[k];
    setSaisie(valeurs);
  }

  // Chargement du dossier existant
  useEffect(() => {
    if (creation) { setDossier(null); setSaisie(DOSSIER_VIDE); return; }
    setChargement(true);
    apiClient.get(`/maintenance/${id}`)
      .then(({ data }) => afficher(data))
      .catch((err) => toast.erreur(messageErreur(err, "Dossier introuvable")))
      .finally(() => setChargement(false));
  }, [id, creation]); // eslint-disable-line react-hooks/exhaustive-deps

  const maj = (champ, valeur) => setSaisie((s) => ({ ...s, [champ]: valeur }));

  // Enregistrement : POST (dépôt) puis ouverture de la fiche, ou PUT (mise à jour)
  async function enregistrer(e) {
    e.preventDefault();
    if (!client) { toast.erreur("Choisissez ou créez le client"); return; }
    setOccupe(true);
    try {
      if (creation) {
        const { data } = await apiClient.post("/maintenance", versApi(saisie, client));
        toast.succes(`Dossier ${data.numero} créé`);
        navigate(`/gestion/maintenance/${data.id}`, { replace: true });
      } else {
        const { data } = await apiClient.put(`/maintenance/${id}`, versApi(saisie, client));
        afficher(data);
        toast.succes("Dossier enregistré");
      }
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez la marque, le modèle et la panne déclarée"));
    } finally {
      setOccupe(false);
    }
  }

  // Génération de la facture de réparation (brouillon) puis ouverture dans l'éditeur
  async function genererFacture() {
    if (!window.confirm("Générer la facture de ce dossier (main d'œuvre + pièces utilisées) ?")) return;
    setOccupe(true);
    try {
      const { data } = await apiClient.post(`/maintenance/${id}/facture`);
      toast.succes(`Facture ${data.numero || ""} créée (brouillon)`);
      navigate(`/gestion/documents/${data.id}`);
    } catch (err) {
      toast.erreur(messageErreur(err, "Génération de la facture impossible"));
    } finally {
      setOccupe(false);
    }
  }

  if (chargement) return <Chargement />;
  if (!creation && !dossier) return <p className="p-6 text-gray-500">Dossier introuvable. <Link to="/gestion/maintenance" className="text-primary underline">Retour</Link></p>;

  // ----- Choix du client -----
  // Placé HORS du <form> : la fenêtre « Nouveau client » de ClientSelect contient
  // son propre formulaire, et un formulaire ne peut pas être imbriqué dans un autre.
  const carteClient = (
    <div className="card">
      <p className="label">Client *</p>
      <ClientSelect value={client} onChange={setClient} />
    </div>
  );

  // ----- Formulaire commun (dépôt) -----
  const formulaireDepot = (
    <div className="card grid gap-4 sm:grid-cols-2">
      <h2 className="font-bold sm:col-span-2">📱 Appareil déposé</h2>
      <Champ label="Marque *"><input className="input" required maxLength={60} value={saisie.marque} onChange={(e) => maj("marque", e.target.value)} placeholder="ex. Tecno" /></Champ>
      <Champ label="Modèle *"><input className="input" required maxLength={100} value={saisie.modele} onChange={(e) => maj("modele", e.target.value)} placeholder="ex. Spark 20" /></Champ>
      <Champ label="IMEI"><input className="input font-mono" maxLength={40} value={saisie.imei} onChange={(e) => maj("imei", e.target.value)} placeholder="*#06# pour l'afficher" /></Champ>
      <Champ label="Couleur"><input className="input" maxLength={40} value={saisie.couleur} onChange={(e) => maj("couleur", e.target.value)} /></Champ>
      <Champ label="Code de déverrouillage 🔒" aide="Confidentiel : jamais imprimé sur le bon ni visible par le client.">
        <input className="input" maxLength={40} autoComplete="off" value={saisie.code_deverrouillage} onChange={(e) => maj("code_deverrouillage", e.target.value)} />
      </Champ>
      <Champ label="Accessoires déposés"><input className="input" maxLength={255} value={saisie.accessoires_deposes} onChange={(e) => maj("accessoires_deposes", e.target.value)} placeholder="ex. coque, chargeur, carte SIM" /></Champ>
      <Champ label="État visuel" className="sm:col-span-2"><textarea className="input" rows={2} maxLength={1000} value={saisie.etat_visuel} onChange={(e) => maj("etat_visuel", e.target.value)} placeholder="Rayures, écran fissuré, traces de choc…" /></Champ>
      <Champ label="Panne déclarée par le client *" className="sm:col-span-2"><textarea className="input" rows={3} required maxLength={2000} value={saisie.panne_declaree} onChange={(e) => maj("panne_declaree", e.target.value)} /></Champ>
      <Champ label="Date de retrait prévue"><input className="input" type="date" value={saisie.date_prevue || ""} onChange={(e) => maj("date_prevue", e.target.value)} /></Champ>
      <Champ label="Technicien">
        <select className="input" value={saisie.technicien_id || ""} onChange={(e) => maj("technicien_id", e.target.value)}>
          <option value="">— Non attribué —</option>
          {equipe.map((m) => <option key={m.id} value={m.id}>{m.nom} ({m.role === "gerant" ? "gérant" : "technicien"})</option>)}
        </select>
      </Champ>
      <Champ label={`Acompte versé (${devise})`}><input className="input" type="number" min={0} value={saisie.acompte} onChange={(e) => maj("acompte", e.target.value)} /></Champ>
    </div>
  );

  // ----- Nouveau dépôt : formulaire seul -----
  if (creation) {
    return (
      <div>
        {/* Le bouton du haut soumet le formulaire grâce à l'attribut form="form-depot" */}
        <EnTetePage titre="Nouveau dépôt" sousTitre="Enregistrement d'un appareil confié à l'atelier">
          <Link to="/gestion/maintenance" className="btn-outline">← Dossiers</Link>
          <button form="form-depot" className="btn-primary" disabled={occupe}>{occupe ? "Enregistrement…" : "✔ Enregistrer le dépôt"}</button>
        </EnTetePage>
        <div className="mx-auto max-w-3xl space-y-5">
          {carteClient}
          <form id="form-depot" onSubmit={enregistrer}>
            {formulaireDepot}
            <p className="mt-3 text-sm text-gray-500">Après l'enregistrement, vous pourrez imprimer le bon de dépôt (avec le code de suivi et le QR code) à remettre au client.</p>
            <button className="btn-primary mt-4 w-full" disabled={occupe}>✔ Enregistrer le dépôt</button>
          </form>
        </div>
      </div>
    );
  }

  // ----- Fiche existante -----
  const telephone = dossier.client?.telephone;
  return (
    <div>
      <EnTetePage titre={`${dossier.marque} ${dossier.modele}`} sousTitre={`Déposé le ${dateHeure(dossier.date_depot)}${dossier.date_restitution ? ` · restitué le ${date(dossier.date_restitution)}` : ""}`}>
        <Link to="/gestion/maintenance" className="btn-outline">← Dossiers</Link>
        <a href={`/gestion/maintenance/${dossier.id}/bon-de-depot`} target="_blank" rel="noreferrer" className="btn-outline">🖨️ Bon de dépôt</a>
        {peutFacturer && (dossier.facture_id
          ? <Link to={`/gestion/documents/${dossier.facture_id}`} className="btn-outline">🧾 Voir la facture</Link>
          : <button type="button" className="btn-accent" onClick={genererFacture} disabled={occupe}>🧾 Générer la facture</button>)}
      </EnTetePage>

      {/* Bandeau : numéro de dossier, code de suivi, statut */}
      <div className="card mb-5 flex flex-wrap items-center gap-x-8 gap-y-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">N° de dossier</p>
          <p className="font-mono text-2xl font-extrabold">{dossier.numero}</p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Code de suivi client</p>
          <p className="rounded-lg bg-primary/10 px-3 font-mono text-2xl font-extrabold tracking-[0.25em] text-primary">{dossier.code_suivi}</p>
        </div>
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">Statut</p>
          <Badge table={STATUTS_SAV} statut={dossier.statut} className="text-sm" />
        </div>
        {dossier.sous_garantie && <span className="badge bg-teal-100 text-teal-800">🛡️ Sous garantie</span>}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Colonne principale : dépôt + atelier (un seul bouton Enregistrer) */}
        <div className="space-y-5 lg:col-span-2">
        {carteClient}
        <form onSubmit={enregistrer} className="space-y-5">
          {formulaireDepot}

          <div className="card grid gap-4 sm:grid-cols-2">
            <h2 className="font-bold sm:col-span-2">🔧 Atelier</h2>
            <Champ label="Diagnostic" className="sm:col-span-2"><textarea className="input" rows={3} maxLength={3000} value={saisie.diagnostic} onChange={(e) => maj("diagnostic", e.target.value)} /></Champ>
            <Champ label="Travaux effectués" className="sm:col-span-2"><textarea className="input" rows={3} maxLength={3000} value={saisie.travaux_effectues} onChange={(e) => maj("travaux_effectues", e.target.value)} /></Champ>
            <Champ label={`Montant du devis — main d'œuvre (${devise})`} aide="Facturé comme main d'œuvre ; les pièces s'ajoutent en plus.">
              <input className="input" type="number" min={0} value={saisie.devis_montant ?? ""} onChange={(e) => maj("devis_montant", e.target.value)} />
            </Champ>
            <Champ label="Devis accepté par le client ?">
              <select className="input" value={saisie.devis_accepte === null ? "" : saisie.devis_accepte ? "oui" : "non"}
                onChange={(e) => maj("devis_accepte", e.target.value === "" ? null : e.target.value === "oui")}>
                <option value="">En attente de réponse</option>
                <option value="oui">Oui, accepté</option>
                <option value="non">Non, refusé</option>
              </select>
            </Champ>
            <div className="sm:col-span-2"><Case label="Réparation sous garantie" aide="Appareil vendu par la boutique et encore couvert." checked={saisie.sous_garantie} onChange={(v) => maj("sous_garantie", v)} /></div>
          </div>

          <div className="sticky bottom-3 z-10 flex justify-end">
            <button className="btn-primary shadow-lg" disabled={occupe}>{occupe ? "Enregistrement…" : "💾 Enregistrer les modifications"}</button>
          </div>
        </form>
        </div>

        {/* Colonne de droite : statut, client, pièces, historique */}
        <div className="space-y-5">
          <ChangementStatut dossier={dossier} statuts={statuts} onChange={afficher} />

          {/* Contacter le client */}
          <div className="card">
            <h2 className="mb-2 font-bold">👤 Client</h2>
            <p className="font-semibold">{dossier.client?.nom}</p>
            <p className="mb-3 text-sm text-gray-500">{telephone}{dossier.client?.email && ` · ${dossier.client.email}`}</p>
            {telephone && (
              <div className="grid grid-cols-2 gap-2">
                <a href={`tel:${telephone}`} className="btn-outline btn-sm">📞 Appeler</a>
                <a href={lienWhatsApp(telephone, `Bonjour ${dossier.client?.nom}, au sujet de votre ${dossier.marque} ${dossier.modele} (dossier ${dossier.numero}) : `)}
                  target="_blank" rel="noreferrer" className="btn btn-sm bg-green-600 text-white hover:bg-green-700">💬 WhatsApp</a>
              </div>
            )}
            <Link to={`/gestion/clients/${dossier.client_id}`} className="mt-3 block text-sm font-semibold text-primary">Voir la fiche client →</Link>
          </div>

          <PiecesUtilisees dossier={dossier} devise={devise} onChange={afficher} />
          <Historique historique={dossier.historique} />
        </div>
      </div>
    </div>
  );
}

// Changement de statut avec un commentaire visible par le client sur le portail
function ChangementStatut({ dossier, statuts, onChange }) {
  const toast = useToast();
  const [statut, setStatut] = useState(dossier.statut);
  const [commentaire, setCommentaire] = useState("");
  const [envoi, setEnvoi] = useState(false);

  // Si le dossier change (rechargement), on repart de son statut actuel
  useEffect(() => { setStatut(dossier.statut); }, [dossier.statut]);

  async function valider(e) {
    e.preventDefault();
    setEnvoi(true);
    try {
      const { data } = await apiClient.post(`/maintenance/${dossier.id}/statut`, { statut, commentaire });
      onChange(data);
      setCommentaire("");
      toast.succes(`Statut : ${data.statut_libelle}`);
    } catch (err) {
      toast.erreur(messageErreur(err, "Changement de statut impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  const liste = Object.keys(statuts).length ? statuts : Object.fromEntries(Object.entries(STATUTS_SAV).map(([k, v]) => [k, v.libelle]));
  return (
    <form onSubmit={valider} className="card space-y-3">
      <h2 className="font-bold">🚦 Changer le statut</h2>
      <select className="input" value={statut} onChange={(e) => setStatut(e.target.value)}>
        {Object.entries(liste).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
      </select>
      <Champ label="Message pour le client (facultatif)" aide="Visible sur la page de suivi du client ; envoyé par e-mail s'il en a un.">
        <input className="input" maxLength={255} value={commentaire} onChange={(e) => setCommentaire(e.target.value)} placeholder="ex. Écran commandé, arrivée jeudi" />
      </Champ>
      <button className="btn-primary w-full" disabled={envoi}>{envoi ? "Envoi…" : "Mettre à jour le statut"}</button>
    </form>
  );
}

// Pièces détachées utilisées : chaque ajout SORT du stock, chaque retrait y REVIENT.
function PiecesUtilisees({ dossier, devise, onChange }) {
  const toast = useToast();
  const [piece, setPiece] = useState(null); // pièce choisie, en attente de la quantité
  const [quantite, setQuantite] = useState(1);

  async function ajouter() {
    try {
      const { data } = await apiClient.post(`/maintenance/${dossier.id}/pieces`, { produit_id: piece.id, quantite: Number(quantite) || 1 });
      onChange(data);
      toast.succes(`${piece.nom} ajoutée (sortie du stock)`);
      setPiece(null);
      setQuantite(1);
    } catch (err) {
      toast.erreur(messageErreur(err, "Ajout de la pièce impossible"));
    }
  }

  async function retirer(p) {
    if (!window.confirm(`Retirer « ${p.nom} » du dossier ? La pièce sera remise en stock.`)) return;
    try {
      const { data } = await apiClient.delete(`/maintenance/${dossier.id}/pieces/${p.id}`);
      onChange(data);
      toast.succes("Pièce retirée et remise en stock");
    } catch (err) {
      toast.erreur(messageErreur(err, "Retrait impossible"));
    }
  }

  const pieces = dossier.pieces || [];
  const total = pieces.reduce((s, p) => s + p.quantite * p.prix_vente, 0);
  return (
    <div className="card">
      <h2 className="mb-1 font-bold">🔩 Pièces utilisées</h2>
      <p className="mb-3 text-xs text-gray-500">Une pièce ajoutée sort immédiatement du stock ; la retirer la remet en stock.</p>

      {/* Ajout : recherche de la pièce puis quantité */}
      {piece ? (
        <div className="mb-3 space-y-2 rounded-xl border border-primary/30 bg-primary/5 p-3">
          <p className="text-sm font-semibold">{piece.nom} <span className="text-xs font-normal text-gray-500">(stock {piece.stock})</span></p>
          <div className="flex gap-2">
            <input className="input w-20 py-1.5" type="number" min={1} value={quantite} onChange={(e) => setQuantite(e.target.value)} aria-label="Quantité" />
            <button type="button" className="btn-primary btn-sm flex-1" onClick={ajouter}>Ajouter</button>
            <button type="button" className="btn-outline btn-sm" onClick={() => setPiece(null)}>Annuler</button>
          </div>
        </div>
      ) : (
        <div className="mb-3"><ProduitSelect onChoisir={setPiece} filtre={pieceDetachee} placeholder="+ Ajouter une pièce détachée…" /></div>
      )}

      {pieces.length === 0 ? <p className="text-sm text-gray-500">Aucune pièce pour l'instant.</p> : (
        <ul className="divide-y divide-gray-100">
          {pieces.map((p) => (
            <li key={p.id} className="flex items-center gap-2 py-2 text-sm">
              <span className="flex-1"><b>{p.quantite} ×</b> {p.nom}<span className="block text-xs text-gray-500">{p.reference} · {prix(p.prix_vente, devise)} l'unité</span></span>
              <button type="button" className="rounded-lg p-1 text-red-600 hover:bg-red-50" onClick={() => retirer(p)} aria-label="Retirer la pièce">✕</button>
            </li>
          ))}
          <li className="flex justify-between pt-2 text-sm font-bold"><span>Total pièces</span><span>{prix(total, devise)}</span></li>
        </ul>
      )}
    </div>
  );
}

// Historique chronologique des statuts (du dépôt jusqu'à aujourd'hui)
function Historique({ historique = [] }) {
  return (
    <div className="card">
      <h2 className="mb-3 font-bold">🕓 Historique</h2>
      <ol className="relative ml-2 border-l-2 border-gray-200">
        {historique.map((h, i) => (
          <li key={i} className="mb-4 ml-4 last:mb-0">
            <span className={`absolute -left-[7px] mt-1.5 h-3 w-3 rounded-full ${i === historique.length - 1 ? "bg-primary" : "bg-gray-300"}`} />
            <p className="text-xs text-gray-500">{dateHeure(h.date)}{h.par && ` · ${h.par}`}</p>
            <p className="text-sm font-semibold">{h.statut_libelle || h.statut}</p>
            {h.commentaire && <p className="text-sm text-gray-600">« {h.commentaire} »</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}
