import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { peut, useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure, prix } from "@/lib/format";
import { TYPES_PRODUIT } from "@/lib/statuts";
import EnTetePage from "@/components/EnTetePage";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import { Case, Champ, ChoixImage } from "./_atelier/communs";

// Valeurs d'un produit vierge (création)
const PRODUIT_VIDE = {
  reference: "", nom: "", type_produit: "TEL", categorie_id: "", marque: "", description: "",
  caracteristiques: [""], prix_achat: 0, prix_vente: 0, stock_alerte: 2, garantie_mois: 0,
  visible_portail: true, actif: true, stock_initial: 0,
};

// Fiche produit : création (/gestion/produits/nouveau) ou modification (/gestion/produits/:id).
export default function ProduitForm() {
  const { id } = useParams();
  const creation = !id;
  const navigate = useNavigate();
  const toast = useToast();
  const { user, boutique } = useAuth();
  // Le technicien voit la fiche en lecture seule
  const peutModifier = peut(user, "catalogue.edition");

  // --- État du formulaire ---
  const [produit, setProduit] = useState(PRODUIT_VIDE);
  const [original, setOriginal] = useState(null); // produit tel qu'enregistré (stock, image...)
  const [categories, setCategories] = useState([]);
  const [mouvements, setMouvements] = useState([]);
  const [motifs, setMotifs] = useState({});
  const [chargement, setChargement] = useState(!creation);
  const [enregistrement, setEnregistrement] = useState(false);
  // Création : la photo choisie est gardée ici et envoyée APRÈS la création du produit
  const [photoEnAttente, setPhotoEnAttente] = useState(null);
  const [apercu, setApercu] = useState(null);

  // Chargement des catégories (liste déroulante)
  useEffect(() => {
    apiClient.get("/categories").then(({ data }) => {
      setCategories(data);
      // En création, on présélectionne la première catégorie
      if (creation && data.length) setProduit((p) => (p.categorie_id ? p : { ...p, categorie_id: data[0].id }));
    }).catch(() => {});
  }, [creation]);

  // Chargement du produit existant + historique de ses mouvements de stock
  useEffect(() => {
    if (creation) return;
    setChargement(true);
    apiClient.get(`/produits/${id}`)
      .then(({ data }) => {
        setOriginal(data);
        setProduit({ ...PRODUIT_VIDE, ...data, caracteristiques: data.caracteristiques?.length ? data.caracteristiques : [""] });
      })
      .catch((err) => toast.erreur(messageErreur(err, "Produit introuvable")))
      .finally(() => setChargement(false));
    // Le journal de stock n'est chargé que pour les rôles qui ont accès au stock
    if (peut(user, "stock")) {
      apiClient.get("/stock/mouvements", { params: { produit_id: id } }).then(({ data }) => setMouvements(data)).catch(() => {});
      apiClient.get("/stock/motifs").then(({ data }) => setMotifs(data)).catch(() => {});
    }
  }, [id, creation, peutModifier]); // eslint-disable-line react-hooks/exhaustive-deps

  // Libère l'aperçu local de la photo quand il n'est plus utilisé
  useEffect(() => () => { if (apercu) URL.revokeObjectURL(apercu); }, [apercu]);

  const maj = (champ, valeur) => setProduit((p) => ({ ...p, [champ]: valeur }));

  // --- Caractéristiques : liste éditable ligne par ligne ---
  const majCarac = (i, valeur) => maj("caracteristiques", produit.caracteristiques.map((c, j) => (j === i ? valeur : c)));
  const ajouterCarac = () => maj("caracteristiques", [...produit.caracteristiques, ""]);
  const retirerCarac = (i) => maj("caracteristiques", produit.caracteristiques.filter((_, j) => j !== i));

  // Envoi d'une photo (multipart/form-data, champ « fichier »)
  async function envoyerPhoto(produitId, fichier) {
    const f = new FormData();
    f.append("fichier", fichier);
    const { data } = await apiClient.post(`/produits/${produitId}/image`, f);
    return data;
  }

  // Choix d'une photo : envoi immédiat si le produit existe, sinon mise en attente
  async function surPhoto(fichier) {
    if (creation) {
      setPhotoEnAttente(fichier);
      setApercu(URL.createObjectURL(fichier));
      return;
    }
    try {
      const data = await envoyerPhoto(id, fichier);
      setOriginal(data);
      toast.succes("Photo enregistrée");
    } catch (err) {
      toast.erreur(messageErreur(err, "Image refusée (JPEG, PNG ou WebP, 5 Mo maximum)"));
    }
  }

  // Enregistrement : POST (création) ou PUT (modification) sur /produits
  async function enregistrer(e) {
    e.preventDefault();
    setEnregistrement(true);
    const corps = {
      reference: produit.reference, nom: produit.nom, type_produit: produit.type_produit,
      categorie_id: produit.categorie_id, marque: produit.marque, description: produit.description,
      caracteristiques: produit.caracteristiques.map((c) => c.trim()).filter(Boolean),
      prix_achat: Number(produit.prix_achat) || 0, prix_vente: Number(produit.prix_vente) || 0,
      stock_alerte: Number(produit.stock_alerte) || 0, garantie_mois: Number(produit.garantie_mois) || 0,
      visible_portail: produit.visible_portail, actif: produit.actif,
    };
    try {
      if (creation) {
        const { data } = await apiClient.post("/produits", { ...corps, stock_initial: Number(produit.stock_initial) || 0 });
        // Photo choisie avant la création : on l'envoie maintenant que le produit a un identifiant
        if (photoEnAttente) {
          try {
            await envoyerPhoto(data.id, photoEnAttente);
          } catch (err) {
            toast.erreur(messageErreur(err, "Produit créé, mais la photo a été refusée"));
          }
        }
        toast.succes("Produit créé");
        navigate(`/gestion/produits/${data.id}`, { replace: true });
      } else {
        const { data } = await apiClient.put(`/produits/${id}`, corps);
        setOriginal(data);
        toast.succes("Produit enregistré");
      }
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez les champs obligatoires (référence, nom, catégorie, prix)"));
    } finally {
      setEnregistrement(false);
    }
  }

  if (chargement) return <Chargement />;
  if (!creation && !original) return <p className="p-6 text-gray-500">Produit introuvable. <Link to="/gestion/produits" className="text-primary underline">Retour au catalogue</Link></p>;

  const service = produit.type_produit === "SER";
  const lectureSeule = !peutModifier;
  const devise = boutique?.devise || "FCFA";

  return (
    <form onSubmit={enregistrer}>
      <EnTetePage titre={creation ? "Nouveau produit" : produit.nom}
        sousTitre={creation ? "Ajout d'un article au catalogue" : `Référence ${original.reference}`}>
        <Link to="/gestion/produits" className="btn-outline">← Catalogue</Link>
        {!lectureSeule && <button className="btn-primary" disabled={enregistrement}>{enregistrement ? "Enregistrement…" : "💾 Enregistrer"}</button>}
      </EnTetePage>

      {lectureSeule && <p className="mb-4 rounded-xl bg-blue-50 px-4 py-2 text-sm text-blue-800">Consultation seule : seuls le DG et les commerciaux modifient le catalogue.</p>}

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Colonne principale : identité, description, prix */}
        <fieldset disabled={lectureSeule} className="space-y-5 lg:col-span-2">
          <div className="card grid gap-4 sm:grid-cols-2">
            <h2 className="font-bold sm:col-span-2">Identification</h2>
            <Champ label="Référence *"><input className="input" required maxLength={50} value={produit.reference} onChange={(e) => maj("reference", e.target.value)} placeholder="ex. SAM-A15-128" /></Champ>
            <Champ label="Type"><select className="input" value={produit.type_produit} onChange={(e) => maj("type_produit", e.target.value)}>
              {Object.entries(TYPES_PRODUIT).map(([code, lib]) => <option key={code} value={code}>{lib}</option>)}
            </select></Champ>
            <Champ label="Nom *" className="sm:col-span-2"><input className="input" required maxLength={200} value={produit.nom} onChange={(e) => maj("nom", e.target.value)} placeholder="ex. Samsung Galaxy A15 128 Go" /></Champ>
            <Champ label="Catégorie *" aide={categories.length === 0 ? "Créez d'abord une catégorie depuis le catalogue (bouton « Catégories »)." : ""}>
              <select className="input" required value={produit.categorie_id} onChange={(e) => maj("categorie_id", e.target.value)}>
                <option value="">— Choisir —</option>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.nom}</option>)}
              </select>
            </Champ>
            <Champ label="Marque"><input className="input" maxLength={80} value={produit.marque} onChange={(e) => maj("marque", e.target.value)} placeholder="ex. Samsung" /></Champ>
          </div>

          <div className="card space-y-4">
            <h2 className="font-bold">Description</h2>
            <Champ label="Texte de présentation (affiché sur le portail)">
              <textarea className="input min-h-[110px]" maxLength={5000} value={produit.description} onChange={(e) => maj("description", e.target.value)} />
            </Champ>
            {/* Caractéristiques : une ligne = une caractéristique */}
            <div>
              <label className="label">Caractéristiques</label>
              <p className="mb-2 text-xs text-gray-500">Une caractéristique par ligne, par exemple « Écran : 6,5 pouces ».</p>
              <div className="space-y-2">
                {produit.caracteristiques.map((c, i) => (
                  <div key={i} className="flex gap-2">
                    <input className="input" value={c} onChange={(e) => majCarac(i, e.target.value)} placeholder="Libellé : valeur" />
                    {!lectureSeule && <button type="button" className="btn-outline btn-sm shrink-0" onClick={() => retirerCarac(i)} aria-label="Retirer la ligne">✕</button>}
                  </div>
                ))}
              </div>
              {!lectureSeule && <button type="button" className="btn-outline btn-sm mt-2" onClick={ajouterCarac}>+ Ajouter une ligne</button>}
            </div>
          </div>

          <div className="card grid gap-4 sm:grid-cols-2">
            <h2 className="font-bold sm:col-span-2">Prix et stock</h2>
            <Champ label={`Prix d'achat (${devise})`} aide="Mis à jour automatiquement à chaque réception fournisseur validée.">
              <input className="input" type="number" min={0} value={produit.prix_achat} onChange={(e) => maj("prix_achat", e.target.value)} />
            </Champ>
            <Champ label={`Prix de vente${boutique?.prix_ttc ? " TTC" : " HT"} (${devise}) *`}>
              <input className="input" type="number" min={0} required value={produit.prix_vente} onChange={(e) => maj("prix_vente", e.target.value)} />
            </Champ>
            {!service && (
              <Champ label="Seuil d'alerte de stock" aide="Le produit passe en rouge quand le stock descend à ce niveau.">
                <input className="input" type="number" min={0} value={produit.stock_alerte} onChange={(e) => maj("stock_alerte", e.target.value)} />
              </Champ>
            )}
            <Champ label="Garantie (mois)">
              <input className="input" type="number" min={0} max={120} value={produit.garantie_mois} onChange={(e) => maj("garantie_mois", e.target.value)} />
            </Champ>
            {creation && !service && (
              <Champ label="Stock initial" aide="Quantité déjà en boutique (enregistrée comme un ajustement d'inventaire).">
                <input className="input" type="number" min={0} value={produit.stock_initial} onChange={(e) => maj("stock_initial", e.target.value)} />
              </Champ>
            )}
          </div>
        </fieldset>

        {/* Colonne de droite : photo, publication, stock */}
        <div className="space-y-5">
          <div className="card">
            <h2 className="mb-3 font-bold">Photo</h2>
            <ChoixImage image={creation ? apercu : original?.image_url} onEnvoyer={surPhoto} desactive={lectureSeule} />
            {creation && photoEnAttente && <p className="mt-2 text-center text-xs text-gray-500">La photo sera envoyée à l'enregistrement du produit.</p>}
          </div>

          <fieldset disabled={lectureSeule} className="card space-y-3">
            <h2 className="font-bold">Publication</h2>
            <Case label="Visible sur le portail" aide="Les clients le voient dans votre vitrine en ligne." checked={produit.visible_portail} onChange={(v) => maj("visible_portail", v)} />
            <Case label="Produit actif" aide="Un produit inactif ne peut plus être vendu ni commandé." checked={produit.actif} onChange={(v) => maj("actif", v)} />
          </fieldset>

          {/* Stock actuel : lecture seule, il ne bouge que par des mouvements */}
          {!creation && !service && (
            <div className="card">
              <h2 className="mb-1 font-bold">Stock actuel</h2>
              <p className={`text-4xl font-extrabold ${original.stock <= original.stock_alerte ? "text-red-600" : "text-ink"}`}>{original.stock}</p>
              <p className="mb-3 text-xs text-gray-500">Seuil d'alerte : {original.stock_alerte} · Valeur d'achat : {prix(original.stock * (original.prix_achat || 0), devise)}</p>
              {peutModifier && <Link to={`/gestion/stock?produit=${original.id}`} className="btn-outline btn-sm w-full">Corriger le stock</Link>}
            </div>
          )}
        </div>
      </div>

      {/* Historique des mouvements de stock de ce produit */}
      {!creation && !service && peutModifier && (
        <div className="card mt-5 overflow-x-auto p-0">
          <h2 className="p-4 pb-2 font-bold">Historique du stock</h2>
          {mouvements.length === 0 ? <p className="px-4 pb-4 text-sm text-gray-500">Aucun mouvement pour ce produit.</p> : (
            <table className="table min-w-[600px]">
              <thead><tr><th>Date</th><th>Sens</th><th className="text-right">Qté</th><th>Motif</th><th>Document</th><th>Commentaire</th><th>Par</th></tr></thead>
              <tbody>
                {mouvements.map((m) => (
                  <tr key={m.id}>
                    <td className="whitespace-nowrap">{dateHeure(m.date)}</td>
                    <td>{m.sens === "E" ? <span className="badge bg-green-100 text-green-800">Entrée</span> : <span className="badge bg-red-100 text-red-700">Sortie</span>}</td>
                    <td className={`text-right font-bold ${m.sens === "E" ? "text-green-700" : "text-red-600"}`}>{m.sens === "E" ? "+" : "−"}{m.quantite}</td>
                    <td>{motifs[m.motif] || m.motif}</td>
                    <td className="font-mono text-xs">{m.reference || "—"}</td>
                    <td className="text-gray-600">{m.commentaire || "—"}</td>
                    <td className="whitespace-nowrap text-gray-600">{m.user_nom || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </form>
  );
}
