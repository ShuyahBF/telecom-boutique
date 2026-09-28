import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { aujourdhui, dateHeure, montant, prix } from "@/lib/format";
import EnTetePage from "@/components/EnTetePage";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import ProduitSelect from "@/components/ProduitSelect";
import { useToast } from "@/components/Toast";
import { Champ } from "./_atelier/communs";

// Seuls les produits stockables (pas les services) peuvent être réceptionnés.
// Fonction définie hors du composant : ProduitSelect ne relance pas sa recherche à chaque affichage.
const produitStockable = (p) => p.type_produit !== "SER";

const BON_VIDE = { fournisseur_id: "", date: aujourdhui(), reference_fournisseur: "", commentaire: "", lignes: [] };

// Bon d'entrée (réception fournisseur) sur plusieurs lignes :
// création, modification tant qu'il n'est pas validé, validation (entrée en stock).
export default function BonEntreeForm() {
  const { id } = useParams();
  const creation = !id;
  const navigate = useNavigate();
  const toast = useToast();
  const { boutique } = useAuth();
  const devise = boutique?.devise || "FCFA";

  // --- État ---
  const [bon, setBon] = useState(BON_VIDE);
  const [infos, setInfos] = useState(null); // numéro, validé, dates... (bon existant)
  const [fournisseurs, setFournisseurs] = useState([]);
  const [chargement, setChargement] = useState(!creation);
  const [occupe, setOccupe] = useState(false);
  const [creationFournisseur, setCreationFournisseur] = useState(false);

  // Chargement de la liste des fournisseurs (liste déroulante)
  const chargerFournisseurs = () => apiClient.get("/fournisseurs").then(({ data }) => setFournisseurs(data)).catch(() => {});
  useEffect(() => { chargerFournisseurs(); }, []);

  // Chargement d'un bon existant
  useEffect(() => {
    if (creation) { setBon({ ...BON_VIDE, date: aujourdhui() }); setInfos(null); return; }
    setChargement(true);
    apiClient.get(`/stock/bons/${id}`)
      .then(({ data }) => {
        setInfos(data);
        setBon({ fournisseur_id: data.fournisseur_id, date: data.date, reference_fournisseur: data.reference_fournisseur || "",
          commentaire: data.commentaire || "", lignes: data.lignes.map((l) => ({ ...l })) });
      })
      .catch((err) => toast.erreur(messageErreur(err, "Bon introuvable")))
      .finally(() => setChargement(false));
  }, [id, creation]); // eslint-disable-line react-hooks/exhaustive-deps

  const lectureSeule = !!infos?.valide; // un bon validé ne se modifie plus
  const maj = (champ, valeur) => setBon((b) => ({ ...b, [champ]: valeur }));

  // --- Lignes du bon ---
  // Ajout d'un produit : prix d'achat pré-rempli avec le dernier prix connu ;
  // si le produit est déjà dans le bon, on augmente simplement sa quantité.
  function ajouterProduit(p) {
    setBon((b) => {
      const existe = b.lignes.find((l) => l.produit_id === p.id);
      if (existe) return { ...b, lignes: b.lignes.map((l) => (l.produit_id === p.id ? { ...l, quantite: Number(l.quantite) + 1 } : l)) };
      return { ...b, lignes: [...b.lignes, { produit_id: p.id, produit_nom: p.nom, reference: p.reference, quantite: 1, prix_achat: p.prix_achat || 0 }] };
    });
  }
  const majLigne = (i, champ, valeur) => maj("lignes", bon.lignes.map((l, j) => (j === i ? { ...l, [champ]: valeur } : l)));
  const retirerLigne = (i) => maj("lignes", bon.lignes.filter((_, j) => j !== i));
  const total = bon.lignes.reduce((s, l) => s + (Number(l.quantite) || 0) * (Number(l.prix_achat) || 0), 0);

  // Données envoyées à l'API (format BonSaisie)
  const corps = () => ({
    fournisseur_id: bon.fournisseur_id, date: bon.date, reference_fournisseur: bon.reference_fournisseur,
    commentaire: bon.commentaire,
    lignes: bon.lignes.map((l) => ({ produit_id: l.produit_id, quantite: Number(l.quantite) || 0, prix_achat: Number(l.prix_achat) || 0 })),
  });

  // Contrôles avant envoi (messages clairs plutôt qu'une erreur technique)
  function verifier() {
    if (!bon.fournisseur_id) return "Choisissez le fournisseur";
    if (bon.lignes.length === 0) return "Ajoutez au moins un produit";
    if (bon.lignes.some((l) => !(Number(l.quantite) > 0))) return "Chaque ligne doit avoir une quantité d'au moins 1";
    return "";
  }

  // Enregistrement : POST (nouveau bon) ou PUT (bon existant). Renvoie le bon enregistré.
  async function sauver() {
    const { data } = creation ? await apiClient.post("/stock/bons", corps()) : await apiClient.put(`/stock/bons/${id}`, corps());
    return data;
  }

  async function enregistrer(e) {
    e?.preventDefault();
    const probleme = verifier();
    if (probleme) { toast.erreur(probleme); return; }
    setOccupe(true);
    try {
      const data = await sauver();
      toast.succes(creation ? `Bon ${data.numero} enregistré (non validé)` : "Bon enregistré");
      if (creation) navigate(`/gestion/stock/bons/${data.id}`, { replace: true });
      else setInfos(data);
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible"));
    } finally {
      setOccupe(false);
    }
  }

  // Validation : on enregistre d'abord les dernières modifications, puis
  // POST /stock/bons/{id}/valider fait entrer toutes les lignes en stock.
  async function valider() {
    const probleme = verifier();
    if (probleme) { toast.erreur(probleme); return; }
    const nb = bon.lignes.reduce((s, l) => s + Number(l.quantite || 0), 0);
    if (!window.confirm(`Valider la réception ?\n\nLe stock sera augmenté de ${nb} article(s). Le bon ne pourra plus être modifié.`)) return;
    setOccupe(true);
    try {
      const enregistre = await sauver();
      await apiClient.post(`/stock/bons/${enregistre.id}/valider`);
      toast.succes("Réception validée : le stock a été augmenté");
      if (creation) navigate(`/gestion/stock/bons/${enregistre.id}`, { replace: true });
      else setInfos((await apiClient.get(`/stock/bons/${id}`)).data);
    } catch (err) {
      toast.erreur(messageErreur(err, "Validation impossible"));
    } finally {
      setOccupe(false);
    }
  }

  // Suppression d'un bon non validé
  async function supprimer() {
    if (!window.confirm("Supprimer ce bon non validé ?")) return;
    try {
      await apiClient.delete(`/stock/bons/${id}`);
      toast.succes("Bon supprimé");
      navigate("/gestion/stock/bons");
    } catch (err) {
      toast.erreur(messageErreur(err, "Suppression impossible"));
    }
  }

  if (chargement) return <Chargement />;

  return (
    <>
    <form onSubmit={enregistrer}>
      <EnTetePage titre={creation ? "Nouvelle réception" : `Bon d'entrée ${infos?.numero || ""}`}
        sousTitre={lectureSeule ? `Validé le ${dateHeure(infos.date_validation)} — marchandise entrée en stock` : "Marchandise reçue d'un fournisseur"}>
        <Link to="/gestion/stock/bons" className="btn-outline">← Bons d'entrée</Link>
        {!lectureSeule && !creation && <button type="button" className="btn-outline text-red-600" onClick={supprimer} disabled={occupe}>🗑️ Supprimer</button>}
        {!lectureSeule && <button className="btn-outline" disabled={occupe}>💾 Enregistrer</button>}
        {!lectureSeule && <button type="button" className="btn-primary" onClick={valider} disabled={occupe}>✔ Valider la réception</button>}
      </EnTetePage>

      {/* Bandeau d'état */}
      {lectureSeule
        ? <div className="mb-4 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-900">✔ Ce bon est validé : les quantités ont été ajoutées au stock. Il n'est plus modifiable (pour corriger, faites un mouvement manuel inverse).</div>
        : <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">Tant que le bon n'est pas validé, le stock ne change pas. Cliquez sur « Valider la réception » quand la marchandise est bien arrivée.</div>}

      {/* En-tête du bon : fournisseur, date, références */}
      <fieldset disabled={lectureSeule} className="card mb-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Champ label="Fournisseur *" className="sm:col-span-2">
          <div className="flex gap-2">
            <select className="input" required value={bon.fournisseur_id} onChange={(e) => maj("fournisseur_id", e.target.value)}>
              <option value="">— Choisir le fournisseur —</option>
              {fournisseurs.filter((f) => f.actif !== false || f.id === bon.fournisseur_id).map((f) => <option key={f.id} value={f.id}>{f.nom}</option>)}
            </select>
            {!lectureSeule && <button type="button" className="btn-outline shrink-0" onClick={() => setCreationFournisseur(true)} title="Nouveau fournisseur">+ Nouveau</button>}
          </div>
        </Champ>
        <Champ label="Date de réception"><input className="input" type="date" required value={bon.date} onChange={(e) => maj("date", e.target.value)} /></Champ>
        <Champ label="N° du bon de livraison"><input className="input" maxLength={60} placeholder="Référence fournisseur" value={bon.reference_fournisseur} onChange={(e) => maj("reference_fournisseur", e.target.value)} /></Champ>
        <Champ label="Commentaire" className="sm:col-span-2 lg:col-span-4"><input className="input" maxLength={1000} value={bon.commentaire} onChange={(e) => maj("commentaire", e.target.value)} /></Champ>
      </fieldset>

      {/* Lignes du bon */}
      <div className="card p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 p-4">
          <h2 className="font-bold">Produits reçus</h2>
          {!lectureSeule && <div className="w-full sm:w-96"><ProduitSelect onChoisir={ajouterProduit} filtre={produitStockable} placeholder="+ Ajouter un produit (nom, référence)…" /></div>}
        </div>

        {bon.lignes.length === 0 ? <p className="px-4 pb-6 text-sm text-gray-500">Aucune ligne : recherchez un produit ci-dessus pour l'ajouter.</p> : (
          <>
            {/* Écran large : tableau */}
            <div className="hidden overflow-x-auto sm:block">
              <table className="table">
                <thead><tr><th>Produit</th><th className="w-28 text-right">Quantité</th><th className="w-40 text-right">Prix d'achat unitaire</th><th className="w-36 text-right">Montant</th>{!lectureSeule && <th className="w-12" />}</tr></thead>
                <tbody>
                  {bon.lignes.map((l, i) => (
                    <tr key={l.produit_id}>
                      <td><div className="font-semibold">{l.produit_nom}</div><div className="font-mono text-xs text-gray-500">{l.reference}</div></td>
                      <td className="text-right">{lectureSeule ? l.quantite : <input className="input py-1.5 text-right" type="number" min={1} value={l.quantite} onChange={(e) => majLigne(i, "quantite", e.target.value)} />}</td>
                      <td className="text-right">{lectureSeule ? montant(l.prix_achat) : <input className="input py-1.5 text-right" type="number" min={0} value={l.prix_achat} onChange={(e) => majLigne(i, "prix_achat", e.target.value)} />}</td>
                      <td className="whitespace-nowrap text-right font-semibold">{montant((Number(l.quantite) || 0) * (Number(l.prix_achat) || 0))}</td>
                      {!lectureSeule && <td><button type="button" className="rounded-lg p-1 text-red-600 hover:bg-red-50" onClick={() => retirerLigne(i)} aria-label="Retirer la ligne">✕</button></td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Mobile : une carte par ligne */}
            <div className="space-y-3 px-4 sm:hidden">
              {bon.lignes.map((l, i) => (
                <div key={l.produit_id} className="rounded-xl border border-gray-200 p-3">
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <div><div className="font-semibold">{l.produit_nom}</div><div className="font-mono text-xs text-gray-500">{l.reference}</div></div>
                    {!lectureSeule && <button type="button" className="text-red-600" onClick={() => retirerLigne(i)} aria-label="Retirer la ligne">✕</button>}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Champ label="Quantité"><input className="input py-1.5" type="number" min={1} disabled={lectureSeule} value={l.quantite} onChange={(e) => majLigne(i, "quantite", e.target.value)} /></Champ>
                    <Champ label="Prix d'achat"><input className="input py-1.5" type="number" min={0} disabled={lectureSeule} value={l.prix_achat} onChange={(e) => majLigne(i, "prix_achat", e.target.value)} /></Champ>
                  </div>
                  <p className="mt-2 text-right text-sm font-semibold">{prix((Number(l.quantite) || 0) * (Number(l.prix_achat) || 0), devise)}</p>
                </div>
              ))}
            </div>
          </>
        )}
        {/* Total du bon */}
        <div className="flex items-center justify-end gap-4 border-t border-gray-200 p-4">
          <span className="text-sm text-gray-600">Total de la réception</span>
          <span className="text-xl font-extrabold">{prix(total, devise)}</span>
        </div>
      </div>
    </form>

    {/* Fenêtre de création rapide d'un fournisseur (hors du formulaire du bon) */}
    <ModaleFournisseurRapide ouvert={creationFournisseur} onFermer={() => setCreationFournisseur(false)}
      onCree={(f) => { setCreationFournisseur(false); chargerFournisseurs(); maj("fournisseur_id", f.id); }} />
    </>
  );
}

// Création rapide d'un fournisseur sans quitter le bon (POST /fournisseurs)
function ModaleFournisseurRapide({ ouvert, onFermer, onCree }) {
  const toast = useToast();
  const [f, setF] = useState({ nom: "", telephone: "", contact: "" });

  async function creer(e) {
    e.preventDefault();
    if (!f.nom.trim()) { toast.erreur("Le nom est obligatoire"); return; }
    try {
      const { data } = await apiClient.post("/fournisseurs", { ...f, email: null });
      toast.succes("Fournisseur créé");
      setF({ nom: "", telephone: "", contact: "" });
      onCree(data);
    } catch (err) {
      toast.erreur(messageErreur(err, "Création impossible"));
    }
  }

  return (
    <Modal ouvert={ouvert} titre="Nouveau fournisseur" onFermer={onFermer}>
      <form onSubmit={creer} className="space-y-3">
        <Champ label="Nom *"><input className="input" value={f.nom} onChange={(e) => setF({ ...f, nom: e.target.value })} autoFocus /></Champ>
        <Champ label="Personne à contacter"><input className="input" value={f.contact} onChange={(e) => setF({ ...f, contact: e.target.value })} /></Champ>
        <Champ label="Téléphone"><input className="input" value={f.telephone} onChange={(e) => setF({ ...f, telephone: e.target.value })} /></Champ>
        <p className="text-xs text-gray-500">Vous pourrez compléter sa fiche plus tard dans « Fournisseurs ».</p>
        <button className="btn-primary w-full">Créer le fournisseur</button>
      </form>
    </Modal>
  );
}
