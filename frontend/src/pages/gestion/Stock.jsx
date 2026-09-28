import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import EnTetePage from "@/components/EnTetePage";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import ProduitSelect from "@/components/ProduitSelect";
import { useToast } from "@/components/Toast";
import { Champ, Vide } from "./_atelier/communs";
import OngletsStock from "./_atelier/OngletsStock";

// Filtre de la recherche de produit : les services ne se stockent pas.
// (Défini hors du composant pour ne pas relancer la recherche à chaque affichage.)
const produitStockable = (p) => p.type_produit !== "SER";

// Motifs autorisés pour un mouvement saisi à la main
const MOTIFS_MANUELS = ["CASSE", "INVENT", "RETOUR", "AUTRE"];

// Page « Stock » : journal de tous les mouvements (entrées / sorties)
// et saisie d'un mouvement manuel (casse, inventaire...).
export default function Stock() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();

  // --- État de la page ---
  const [mouvements, setMouvements] = useState([]);
  const [motifs, setMotifs] = useState({});
  const [chargement, setChargement] = useState(true);
  const [recherche, setRecherche] = useState("");
  const [modale, setModale] = useState(false);

  // Chargement du journal (500 derniers mouvements) et des libellés de motifs
  const charger = useCallback(() => {
    apiClient.get("/stock/mouvements")
      .then(({ data }) => setMouvements(data))
      .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger le journal de stock")))
      .finally(() => setChargement(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    charger();
    apiClient.get("/stock/motifs").then(({ data }) => setMotifs(data)).catch(() => {});
  }, [charger]);

  // Arrivée depuis une fiche produit (« Corriger le stock ») : on ouvre la saisie directement
  const produitDemande = params.get("produit");
  useEffect(() => { if (produitDemande) setModale(true); }, [produitDemande]);

  function fermerModale() {
    setModale(false);
    if (produitDemande) setParams({}, { replace: true });
  }

  // Filtrage local du journal (produit, référence, document, commentaire)
  const q = recherche.trim().toLowerCase();
  const affiches = q
    ? mouvements.filter((m) => [m.produit_nom, m.produit_reference, m.reference, m.commentaire, m.user_nom]
      .some((v) => (v || "").toLowerCase().includes(q)))
    : mouvements;

  return (
    <div>
      <EnTetePage titre="Stock" sousTitre="Journal de toutes les entrées et sorties de marchandises">
        <Link to="/gestion/stock/bons/nouveau" className="btn-outline">📥 Nouvelle réception</Link>
        <button type="button" className="btn-primary" onClick={() => setModale(true)}>± Mouvement manuel</button>
      </EnTetePage>

      {/* Onglets : journal / bons d'entrée */}
      <OngletsStock />

      {/* Rappel de la règle d'or du stock */}
      <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        💡 Le stock ne se modifie jamais à la main : pour corriger une erreur, saisissez un <b>mouvement inverse</b>.
        Chaque vente, réception ou pièce utilisée en atelier crée automatiquement son mouvement.
      </div>

      <div className="mb-4">
        <input className="input sm:max-w-sm" placeholder="🔍 Filtrer par produit, document, commentaire…" value={recherche} onChange={(e) => setRecherche(e.target.value)} />
      </div>

      {/* Tableau du journal */}
      <div className="card overflow-x-auto p-0">
        {chargement ? <Chargement /> : affiches.length === 0 ? <Vide icone="🏷️">Aucun mouvement de stock.</Vide> : (
          <>
          {/* Téléphone : une ligne compacte par mouvement */}
          <ul className="divide-y divide-gray-100 sm:hidden">
            {affiches.map((m) => (
              <li key={m.id} className="flex items-start gap-3 p-3">
                <span className={`w-12 shrink-0 text-right text-lg font-extrabold ${m.sens === "E" ? "text-green-700" : "text-red-600"}`}>{m.sens === "E" ? "+" : "−"}{m.quantite}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">{m.produit_nom}</span>
                  <span className="block text-xs text-gray-600">{motifs[m.motif] || m.motif}{m.reference && ` · ${m.reference}`}</span>
                  {m.commentaire && <span className="block text-xs text-gray-500">{m.commentaire}</span>}
                  <span className="block text-xs text-gray-400">{dateHeure(m.date)} · {m.user_nom}</span>
                </span>
              </li>
            ))}
          </ul>
          <table className="table hidden min-w-[860px] sm:table">
            <thead>
              <tr><th>Date</th><th>Produit</th><th>Sens</th><th className="text-right">Quantité</th><th>Motif</th><th>Document</th><th>Commentaire</th><th>Utilisateur</th></tr>
            </thead>
            <tbody>
              {affiches.map((m) => (
                <tr key={m.id}>
                  <td className="whitespace-nowrap">{dateHeure(m.date)}</td>
                  <td>
                    <Link to={`/gestion/produits/${m.produit_id}`} className="font-semibold hover:text-primary">{m.produit_nom}</Link>
                    <div className="font-mono text-xs text-gray-500">{m.produit_reference}</div>
                  </td>
                  <td className="whitespace-nowrap">{m.sens === "E"
                    ? <span className="badge bg-green-100 text-green-800">▲ Entrée</span>
                    : <span className="badge bg-red-100 text-red-700">▼ Sortie</span>}</td>
                  <td className={`text-right text-base font-bold ${m.sens === "E" ? "text-green-700" : "text-red-600"}`}>{m.sens === "E" ? "+" : "−"}{m.quantite}</td>
                  <td>{motifs[m.motif] || m.motif}</td>
                  <td className="font-mono text-xs">{m.reference || "—"}</td>
                  <td className="max-w-[16rem] text-gray-600">{m.commentaire || "—"}</td>
                  <td className="whitespace-nowrap text-gray-600">{m.user_nom || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </>
        )}
      </div>

      <ModaleMouvement ouvert={modale} onFermer={fermerModale} motifs={motifs} produitId={produitDemande}
        onEnregistre={() => { fermerModale(); charger(); }} />
    </div>
  );
}

// Fenêtre de saisie d'un mouvement manuel (POST /stock/mouvements)
function ModaleMouvement({ ouvert, onFermer, motifs, produitId, onEnregistre }) {
  const toast = useToast();
  const [produit, setProduit] = useState(null);
  const [saisie, setSaisie] = useState({ sens: "S", quantite: 1, motif: "CASSE", commentaire: "" });
  const [envoi, setEnvoi] = useState(false);

  // Remise à zéro à chaque ouverture ; produit pré-rempli si on vient d'une fiche produit
  useEffect(() => {
    if (!ouvert) return;
    setSaisie({ sens: "S", quantite: 1, motif: "CASSE", commentaire: "" });
    setProduit(null);
    if (produitId) apiClient.get(`/produits/${produitId}`).then(({ data }) => setProduit(data)).catch(() => {});
  }, [ouvert, produitId]);

  const maj = (champ, valeur) => setSaisie((s) => ({ ...s, [champ]: valeur }));

  async function valider(e) {
    e.preventDefault();
    if (!produit) { toast.erreur("Choisissez un produit"); return; }
    setEnvoi(true);
    try {
      await apiClient.post("/stock/mouvements", { ...saisie, produit_id: produit.id, quantite: Number(saisie.quantite) });
      toast.succes(`Mouvement enregistré : ${saisie.sens === "E" ? "+" : "−"}${saisie.quantite} ${produit.nom}`);
      onEnregistre();
    } catch (err) {
      toast.erreur(messageErreur(err, "Mouvement refusé"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Modal ouvert={ouvert} titre="Mouvement manuel de stock" onFermer={onFermer}>
      <form onSubmit={valider} className="space-y-4">
        {/* Choix du produit (hors services) */}
        <div>
          <p className="label">Produit</p>
          {produit ? (
            <div className="flex items-center justify-between gap-2 rounded-xl border border-gray-300 px-3 py-2.5">
              <div>
                <div className="font-semibold">{produit.nom}</div>
                <div className="text-xs text-gray-500">{produit.reference} · stock actuel <b>{produit.stock}</b></div>
              </div>
              <button type="button" className="text-sm font-semibold text-primary" onClick={() => setProduit(null)}>Changer</button>
            </div>
          ) : <ProduitSelect onChoisir={setProduit} filtre={produitStockable} placeholder="Rechercher le produit (nom, référence)…" />}
        </div>

        {/* Sens : deux gros boutons Entrée / Sortie */}
        <div className="grid grid-cols-2 gap-2">
          <button type="button" onClick={() => maj("sens", "E")}
            className={`btn border-2 ${saisie.sens === "E" ? "border-green-600 bg-green-50 text-green-800" : "border-gray-200 bg-white text-gray-600"}`}>▲ Entrée (+)</button>
          <button type="button" onClick={() => maj("sens", "S")}
            className={`btn border-2 ${saisie.sens === "S" ? "border-red-600 bg-red-50 text-red-700" : "border-gray-200 bg-white text-gray-600"}`}>▼ Sortie (−)</button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Champ label="Quantité"><input className="input" type="number" min={1} required value={saisie.quantite} onChange={(e) => maj("quantite", e.target.value)} /></Champ>
          <Champ label="Motif">
            <select className="input" value={saisie.motif} onChange={(e) => maj("motif", e.target.value)}>
              {MOTIFS_MANUELS.map((m) => <option key={m} value={m}>{motifs[m] || m}</option>)}
            </select>
          </Champ>
        </div>
        <Champ label="Commentaire" aide="Expliquez la raison (ex. « écran cassé au déballage », « inventaire du 30/09 »).">
          <input className="input" maxLength={255} value={saisie.commentaire} onChange={(e) => maj("commentaire", e.target.value)} />
        </Champ>
        <button className="btn-primary w-full" disabled={envoi}>{envoi ? "Enregistrement…" : "Enregistrer le mouvement"}</button>
      </form>
    </Modal>
  );
}
