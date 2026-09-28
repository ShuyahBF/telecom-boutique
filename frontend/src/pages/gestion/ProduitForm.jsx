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
import DocumentsPrives from "./_catalogue/DocumentsPrives";

// Valeurs d'un produit vierge (création)
const PRODUIT_VIDE = {
  reference: "", nom: "", type_produit: "TEL", categorie_id: "", marque: "", description: "",
  caracteristiques: [""], prix_achat: 0, prix_vente: 0, stock_alerte: 2, garantie_mois: 0,
  visible_portail: true, actif: true, stock_initial: 0, conseils_utilisation: "",
};

// Message affiché quand on veut montrer sur le portail un produit sans prix
// (même règle que le serveur : un service peut rester à 0)
const MESSAGE_SANS_PRIX = "Fixez d'abord un prix de vente : un produit sans prix ne peut pas être visible sur le portail.";

// Fiche produit : création (/gestion/produits/nouveau) ou modification (/gestion/produits/:id).
// Deux sortes de produits :
// - produit créé par la boutique : tout est modifiable ;
// - produit copié du CATALOGUE PUBLIC (champ catalogue_id rempli) : le nom, la
//   marque, le type, la description, les caractéristiques et la référence sont
//   tenus à jour chaque soir par la plateforme -> affichés en LECTURE SEULE.
//   La boutique règle seulement son prix, son stock, son rayon, sa visibilité,
//   ses conseils, ses documents privés et, si elle veut, sa propre photo.
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
  // Devient vrai quand l'utilisateur coche « visible sur le portail » ou tente
  // d'enregistrer : on peut alors afficher l'avertissement « prix manquant »
  const [alerteVisibilite, setAlerteVisibilite] = useState(false);

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
        // (les valeurs absentes ou nulles sont remplacées par "" pour garder des champs contrôlés)
        setProduit({ ...PRODUIT_VIDE, ...data, marque: data.marque || "", description: data.description || "",
          conseils_utilisation: data.conseils_utilisation || "",
          caracteristiques: data.caracteristiques?.length ? data.caracteristiques : [""] });
        // Nouveauté du catalogue public : l'ouvrir retire le badge « Nouveau »
        if (data.nouveau) apiClient.post(`/produits/${id}/vu`).catch(() => {});
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
    // Contrôle avant l'envoi : pas de produit visible sur le portail sans prix
    if (sansPrixVisible) {
      setAlerteVisibilite(true);
      toast.erreur(MESSAGE_SANS_PRIX);
      document.getElementById("prix-vente")?.focus();
      return;
    }
    setEnregistrement(true);
    const corps = {
      reference: produit.reference, nom: produit.nom, type_produit: produit.type_produit,
      categorie_id: produit.categorie_id, marque: produit.marque, description: produit.description,
      caracteristiques: produit.caracteristiques.map((c) => c.trim()).filter(Boolean),
      prix_achat: Number(produit.prix_achat) || 0, prix_vente: Number(produit.prix_vente) || 0,
      stock_alerte: Number(produit.stock_alerte) || 0, garantie_mois: Number(produit.garantie_mois) || 0,
      visible_portail: produit.visible_portail, actif: produit.actif,
      conseils_utilisation: produit.conseils_utilisation || "",
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
  // Produit issu du catalogue public : ses informations partagées sont verrouillées
  const duCatalogue = !creation && !!original?.catalogue_id;
  const verrou = lectureSeule || duCatalogue;
  // Visible sur le portail mais sans prix (hors service) : enregistrement refusé
  const sansPrixVisible = produit.visible_portail && !service && !(Number(produit.prix_vente) > 0);

  return (
    <form onSubmit={enregistrer}>
      <EnTetePage titre={creation ? "Nouveau produit" : produit.nom}
        sousTitre={creation ? "Ajout d'un article au catalogue" : `Référence ${original.reference}`}>
        <Link to="/gestion/produits" className="btn-outline">← Catalogue</Link>
        {!lectureSeule && <button className="btn-primary" disabled={enregistrement}>{enregistrement ? "Enregistrement…" : "💾 Enregistrer"}</button>}
      </EnTetePage>

      {lectureSeule && <p className="mb-4 rounded-xl bg-blue-50 px-4 py-2 text-sm text-blue-800">Consultation seule : seuls le DG et les commerciaux modifient le catalogue.</p>}

      {/* Bandeau des produits copiés du catalogue public */}
      {duCatalogue && (
        <div className="mb-4 flex flex-col gap-2 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900 sm:flex-row sm:items-center">
          <span className="text-2xl" aria-hidden="true">🌍</span>
          <p className="flex-1">
            <b>Fiche du catalogue public, mise à jour chaque soir</b> : vous réglez ici votre prix, votre stock,
            votre visibilité et vos documents. Le nom, la marque, la description et les caractéristiques sont communs à toutes les boutiques.
          </p>
          <Link to="/gestion/catalogue-public" className="btn-outline btn-sm shrink-0">Consulter le catalogue public →</Link>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Colonne principale : identité, description, prix */}
        <fieldset disabled={lectureSeule} className="space-y-5 lg:col-span-2">
          <div className="card grid gap-4 sm:grid-cols-2">
            <h2 className="font-bold sm:col-span-2">Identification {duCatalogue && <span className="ml-1 text-xs font-normal text-gray-500">🔒 informations communes (lecture seule)</span>}</h2>
            {/* Champs partagés : désactivés (disabled) pour un produit du catalogue public */}
            <Champ label="Référence *"><input className="input disabled:bg-gray-100 disabled:text-gray-600" required maxLength={50} disabled={verrou} value={produit.reference} onChange={(e) => maj("reference", e.target.value)} placeholder="ex. SAM-A15-128" /></Champ>
            <Champ label="Type"><select className="input disabled:bg-gray-100 disabled:text-gray-600" disabled={verrou} value={produit.type_produit} onChange={(e) => maj("type_produit", e.target.value)}>
              {Object.entries(TYPES_PRODUIT).map(([code, lib]) => <option key={code} value={code}>{lib}</option>)}
            </select></Champ>
            <Champ label="Nom *" className="sm:col-span-2"><input className="input disabled:bg-gray-100 disabled:text-gray-600" required maxLength={200} disabled={verrou} value={produit.nom} onChange={(e) => maj("nom", e.target.value)} placeholder="ex. Samsung Galaxy A15 128 Go" /></Champ>
            <Champ label="Catégorie *" aide={categories.length === 0 ? "Créez d'abord une catégorie depuis le catalogue (bouton « Catégories »)." : ""}>
              <select className="input" required value={produit.categorie_id} onChange={(e) => maj("categorie_id", e.target.value)}>
                <option value="">— Choisir —</option>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.nom}</option>)}
              </select>
            </Champ>
            <Champ label="Marque"><input className="input disabled:bg-gray-100 disabled:text-gray-600" maxLength={80} disabled={verrou} value={produit.marque} onChange={(e) => maj("marque", e.target.value)} placeholder="ex. Samsung" /></Champ>
          </div>

          {/* Description et caractéristiques : verrouillées pour un produit du catalogue public */}
          <fieldset disabled={verrou} className="card space-y-4">
            <h2 className="font-bold">Description {duCatalogue && <span className="ml-1 text-xs font-normal text-gray-500">🔒 lecture seule</span>}</h2>
            <Champ label="Texte de présentation (affiché sur le portail)">
              <textarea className="input min-h-[110px] disabled:bg-gray-100 disabled:text-gray-600" maxLength={5000} value={produit.description} onChange={(e) => maj("description", e.target.value)} />
            </Champ>
            {/* Caractéristiques : une ligne = une caractéristique */}
            <div>
              <label className="label">Caractéristiques</label>
              <p className="mb-2 text-xs text-gray-500">Une caractéristique par ligne, par exemple « Écran : 6,5 pouces ».</p>
              <div className="space-y-2">
                {produit.caracteristiques.map((c, i) => (
                  <div key={i} className="flex gap-2">
                    <input className="input disabled:bg-gray-100 disabled:text-gray-600" value={c} onChange={(e) => majCarac(i, e.target.value)} placeholder="Libellé : valeur" />
                    {!verrou && <button type="button" className="btn-outline btn-sm shrink-0" onClick={() => retirerCarac(i)} aria-label="Retirer la ligne">✕</button>}
                  </div>
                ))}
              </div>
              {!verrou && <button type="button" className="btn-outline btn-sm mt-2" onClick={ajouterCarac}>+ Ajouter une ligne</button>}
            </div>

            {/* « Compatible avec » : téléphones auxquels cette pièce / cet accessoire convient */}
            {original?.modeles_compatibles?.length > 0 && (
              <div>
                <p className="label">Compatible avec</p>
                <div className="flex flex-wrap gap-2">
                  {original.modeles_compatibles.map((m) => (
                    <span key={m.catalogue_id || m.nom} className="badge bg-gray-100 px-3 py-1 text-sm text-gray-700">📱 {m.nom}</span>
                  ))}
                </div>
              </div>
            )}
          </fieldset>

          <div className="card grid gap-4 sm:grid-cols-2">
            <h2 className="font-bold sm:col-span-2">Prix et stock</h2>
            <Champ label={`Prix d'achat (${devise})`} aide="Mis à jour automatiquement à chaque réception fournisseur validée.">
              <input className="input" type="number" min={0} value={produit.prix_achat} onChange={(e) => maj("prix_achat", e.target.value)} />
            </Champ>
            <Champ label={`Prix de vente${boutique?.prix_ttc ? " TTC" : " HT"} (${devise}) *`}>
              <input id="prix-vente" className={`input ${sansPrixVisible && alerteVisibilite ? "border-accent ring-2 ring-accent/20" : ""}`} type="number" min={0} required
                value={produit.prix_vente} onChange={(e) => maj("prix_vente", e.target.value)} />
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
          {/* Conseils d'utilisation : texte propre à la boutique, affiché sur sa vitrine */}
          <div className="card">
            <h2 className="mb-2 font-bold">💡 Conseils d'utilisation</h2>
            <Champ label="Vos conseils aux clients (affichés sur votre vitrine)" aide="Par exemple : charger complètement avant la première utilisation, utiliser le chargeur d'origine…">
              <textarea className="input min-h-[90px]" maxLength={5000} value={produit.conseils_utilisation}
                onChange={(e) => maj("conseils_utilisation", e.target.value)} />
            </Champ>
          </div>

        </fieldset>

        {/* Colonne de droite : photo, publication, stock */}
        <div className="space-y-5">
          <div className="card">
            <h2 className="mb-3 font-bold">Photo</h2>
            <ChoixImage image={creation ? apercu : original?.image_url} onEnvoyer={surPhoto} desactive={lectureSeule} />
            {/* Produit du catalogue : la photo envoyée ne remplace celle du catalogue que pour cette boutique */}
            {duCatalogue && (
              <p className="mt-2 text-center text-xs text-gray-500">
                {original.image_source === "boutique" ? "📷 Photo de votre boutique." : "🌍 Photo du catalogue public."}
                {!lectureSeule && " Votre photo remplace celle du catalogue pour votre boutique seulement."}
              </p>
            )}
            {creation && photoEnAttente && <p className="mt-2 text-center text-xs text-gray-500">La photo sera envoyée à l'enregistrement du produit.</p>}
          </div>

          <fieldset disabled={lectureSeule} className="card space-y-3">
            <h2 className="font-bold">Publication</h2>
            <Case label="Visible sur le portail" aide="Les clients le voient dans votre vitrine en ligne." checked={produit.visible_portail}
              onChange={(v) => { maj("visible_portail", v); if (v) setAlerteVisibilite(true); }} />
            {/* Avertissement : visible sur le portail mais pas encore de prix */}
            {sansPrixVisible && alerteVisibilite && (
              <p role="alert" className="rounded-xl bg-orange-50 px-3 py-2 text-sm font-semibold text-orange-800">⚠️ {MESSAGE_SANS_PRIX}</p>
            )}
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

      {/* Documents privés (brochure, manuel...) : seulement pour un produit déjà enregistré */}
      {!creation && <DocumentsPrives produit={original} onMaj={setOriginal} lectureSeule={lectureSeule} />}

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
