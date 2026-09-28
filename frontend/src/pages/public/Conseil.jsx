import { useState } from "react";
import { Link, useNavigate, useOutletContext, useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";

// DEMANDE DE CONSEIL (/b/:slug/conseil) : le client pose une question à la
// boutique. Une conversation privée est créée, accessible par un lien secret
// (/b/:slug/conseil/<jeton>). ?produit=<id>&nom=<nom> pré-remplit le produit concerné.
export default function Conseil() {
  const { boutique } = useOutletContext();
  const [params] = useSearchParams();
  const navigate = useNavigate();

  // Produit concerné, transmis par la fiche produit (facultatif)
  const produitId = params.get("produit") || "";
  const produitNom = params.get("nom") || "";

  // Champs du formulaire (sujet pré-rempli avec le nom du produit s'il y en a un)
  const [form, setForm] = useState({
    nom: "", telephone: "", email: "",
    sujet: produitNom ? `Question sur ${produitNom}` : "",
    texte: "",
  });
  // Le client peut retirer le produit pré-rempli
  const [avecProduit, setAvecProduit] = useState(Boolean(produitId));
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState("");

  // Met à jour un champ du formulaire
  const champ = (cle) => (e) => setForm({ ...form, [cle]: e.target.value });

  // Envoi de la demande : l'API renvoie le jeton de la conversation
  const envoyer = async (e) => {
    e.preventDefault();
    setErreur("");
    setEnvoi(true);
    try {
      const { data } = await apiClient.post(`/public/b/${boutique.slug}/conseils`, {
        nom: form.nom.trim(),
        telephone: form.telephone.trim(),
        email: form.email.trim() || null,
        sujet: form.sujet.trim(),
        texte: form.texte.trim(),
        produit_id: avecProduit ? produitId : null,
      });
      // On ouvre la page de la conversation (?nouveau=1 affiche un rappel « gardez ce lien »)
      navigate(`/b/${boutique.slug}/conseil/${data.jeton}?nouveau=1`);
    } catch (err) {
      setErreur(messageErreur(err, "Votre demande n'a pas pu être envoyée. Vérifiez les champs."));
      setEnvoi(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-2xl font-extrabold">💬 Demander conseil</h1>
        <p className="text-gray-500">Une question sur un téléphone, un accessoire ou une réparation ? L'équipe de {boutique.nom} vous répond.</p>
      </div>

      {/* Explication : conversation privée + e-mail pour être prévenu */}
      <div className="rounded-2xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-900">
        <p>🔒 Après l'envoi, vous arriverez sur la <b>page privée de votre conversation</b>. Gardez son lien (ajoutez-la à vos favoris) pour lire la réponse et continuer l'échange.</p>
        <p className="mt-1">✉️ Indiquez votre e-mail pour être <b>prévenu dès que la boutique répond</b>.</p>
      </div>

      {erreur && <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">⚠️ {erreur}</p>}

      {/* ---------- Formulaire ---------- */}
      <form onSubmit={envoyer} className="card space-y-3">
        <div>
          <label className="label" htmlFor="nom">Votre nom *</label>
          <input id="nom" className="input" required minLength={2} autoComplete="name" value={form.nom} onChange={champ("nom")} />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="telephone">Téléphone *</label>
            <input id="telephone" className="input" type="tel" inputMode="tel" required minLength={8} autoComplete="tel"
              value={form.telephone} onChange={champ("telephone")} />
          </div>
          <div>
            <label className="label" htmlFor="email">E-mail <span className="font-normal text-gray-400">(facultatif)</span></label>
            <input id="email" className="input" type="email" autoComplete="email" value={form.email} onChange={champ("email")} />
          </div>
        </div>

        {/* Produit concerné (seulement si on vient d'une fiche produit) */}
        {produitId && avecProduit && (
          <div className="flex items-center justify-between gap-2 rounded-xl bg-gray-50 px-3 py-2 text-sm">
            <span>📱 Produit concerné : <b>{produitNom || "produit du catalogue"}</b></span>
            <button type="button" className="text-gray-400 hover:text-red-600" onClick={() => setAvecProduit(false)} aria-label="Retirer le produit">✕</button>
          </div>
        )}

        <div>
          <label className="label" htmlFor="sujet">Sujet *</label>
          <input id="sujet" className="input" required minLength={2} maxLength={200} placeholder="Ex. : quel téléphone pour moins de 100 000 FCFA ?"
            value={form.sujet} onChange={champ("sujet")} />
        </div>
        <div>
          <label className="label" htmlFor="texte">Votre message *</label>
          <textarea id="texte" className="input" rows={5} required minLength={2} maxLength={5000}
            placeholder="Décrivez votre besoin : usage, budget, modèle actuel…" value={form.texte} onChange={champ("texte")} />
        </div>
        <button type="submit" className="btn-boutique w-full py-3" disabled={envoi}>{envoi ? "Envoi…" : "Envoyer ma question"}</button>
        <p className="text-center text-xs text-gray-500">
          Vous préférez appeler ? {boutique.telephone ? <b>{boutique.telephone}</b> : <Link to={`/b/${boutique.slug}`} className="text-boutique">voir nos coordonnées</Link>}
        </p>
      </form>
    </div>
  );
}
