import { useEffect, useRef, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { date } from "@/lib/format";
import { useToast } from "@/components/Toast";

// Section « Documents privés » de la fiche produit (back-office).
// La boutique joint à un produit ses propres fichiers : brochure, fiche
// technique, manuel, conseils, photo... Ils lui appartiennent et ne sont
// JAMAIS partagés avec les autres boutiques. Chaque document peut être
// montré ou non aux clients sur la vitrine en ligne.
//
// Props :
// - produit : le produit tel qu'enregistré (avec sa liste « documents »)
// - onMaj(produit) : appelé avec le produit renvoyé par l'API après chaque changement
// - lectureSeule : true pour le technicien (consultation sans modification)
//
// Attention : cette section est affichée À L'INTÉRIEUR du formulaire du produit.
// On n'utilise donc pas de <form> ici (formulaires imbriqués interdits en HTML) :
// les boutons sont de type « button » et la touche Entrée est neutralisée.

// Formats et taille acceptés par le serveur (voir backend/storage.py)
const FORMATS = ["application/pdf", "image/jpeg", "image/png", "image/webp"];
const TAILLE_MAX = 15 * 1024 * 1024; // 15 Mo

// Icône affichée devant chaque document selon son type
const ICONES = { BROCHURE: "📰", FICHE_TECHNIQUE: "📋", MANUEL: "📘", CONSEILS: "💡", PHOTO: "🖼️", AUTRE: "📄" };

// Valeurs du petit formulaire d'ajout (vierge)
const AJOUT_VIDE = { titre: "", type_document: "BROCHURE", visible_clients: false };

export default function DocumentsPrives({ produit, onMaj, lectureSeule }) {
  const toast = useToast();
  const champFichier = useRef(null);
  // Types de documents proposés par l'API : { BROCHURE: "Brochure", ... }
  const [types, setTypes] = useState({});
  const [ajout, setAjout] = useState(AJOUT_VIDE);
  const [fichier, setFichier] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const documents = produit.documents || [];

  // Chargement de la liste des types (une seule fois)
  useEffect(() => {
    apiClient.get("/produits-types-documents").then(({ data }) => setTypes(data)).catch(() => {});
  }, []);

  // Choix du fichier : contrôle du format et de la taille AVANT l'envoi
  function surFichier(e) {
    const f = e.target.files?.[0] || null;
    if (f && !FORMATS.includes(f.type)) {
      toast.erreur("Format non accepté : PDF, JPEG, PNG ou WebP uniquement.");
      e.target.value = "";
      setFichier(null);
      return;
    }
    if (f && f.size > TAILLE_MAX) {
      toast.erreur("Fichier trop lourd : 15 Mo maximum.");
      e.target.value = "";
      setFichier(null);
      return;
    }
    setFichier(f);
    // Titre pré-rempli avec le nom du fichier (sans l'extension) s'il est vide
    if (f && !ajout.titre.trim()) setAjout((a) => ({ ...a, titre: f.name.replace(/\.[^.]+$/, "") }));
  }

  // Envoi du document (multipart/form-data : fichier, titre, type_document, visible_clients)
  async function ajouter() {
    if (!fichier) { toast.erreur("Choisissez d'abord un fichier."); return; }
    if (!ajout.titre.trim()) { toast.erreur("Donnez un titre au document."); return; }
    const f = new FormData();
    f.append("fichier", fichier);
    f.append("titre", ajout.titre.trim());
    f.append("type_document", ajout.type_document);
    f.append("visible_clients", ajout.visible_clients ? "true" : "false");
    setEnvoi(true);
    try {
      const { data } = await apiClient.post(`/produits/${produit.id}/documents`, f);
      onMaj(data);
      // Remise à zéro du petit formulaire
      setAjout(AJOUT_VIDE);
      setFichier(null);
      if (champFichier.current) champFichier.current.value = "";
      toast.succes("Document ajouté");
    } catch (err) {
      toast.erreur(messageErreur(err, "Document refusé (PDF, JPEG, PNG ou WebP, 15 Mo maximum)"));
    } finally {
      setEnvoi(false);
    }
  }

  // Bascule « visible par les clients sur ma vitrine » (PATCH)
  async function basculer(doc) {
    try {
      const { data } = await apiClient.patch(`/produits/${produit.id}/documents/${doc.id}`, { visible_clients: !doc.visible_clients });
      onMaj(data);
      toast.succes(doc.visible_clients ? "Document masqué aux clients" : "Document visible sur votre vitrine");
    } catch (err) {
      toast.erreur(messageErreur(err, "Modification impossible"));
    }
  }

  // Suppression définitive (après confirmation)
  async function supprimer(doc) {
    if (!window.confirm(`Supprimer le document « ${doc.titre} » ?`)) return;
    try {
      const { data } = await apiClient.delete(`/produits/${produit.id}/documents/${doc.id}`);
      onMaj(data);
      toast.succes("Document supprimé");
    } catch (err) {
      toast.erreur(messageErreur(err, "Suppression impossible"));
    }
  }

  // La touche Entrée dans un champ ne doit pas enregistrer tout le produit
  const bloquerEntree = (e) => { if (e.key === "Enter") e.preventDefault(); };

  return (
    <div className="card mt-5">
      <h2 className="font-bold">📎 Documents privés</h2>
      <p className="mb-3 text-xs text-gray-500">
        🔒 Ces documents appartiennent à votre boutique et ne sont jamais partagés avec les autres boutiques.
        Cochez « visible par les clients » pour les proposer au téléchargement sur votre vitrine.
      </p>

      {/* ---------- Liste des documents déjà joints ---------- */}
      {documents.length === 0 ? (
        <p className="mb-4 rounded-xl bg-gray-50 px-4 py-3 text-sm text-gray-500">Aucun document pour ce produit.</p>
      ) : (
        <ul className="mb-4 divide-y divide-gray-100 rounded-xl border border-gray-200">
          {documents.map((d) => (
            <li key={d.id} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center">
              {/* Icône + titre (lien qui ouvre le fichier) + type et date */}
              <a href={d.url} target="_blank" rel="noopener noreferrer" className="flex min-w-0 flex-1 items-center gap-3 hover:underline">
                <span className="text-2xl" aria-hidden="true">{ICONES[d.type] || ICONES.AUTRE}</span>
                <span className="min-w-0">
                  <span className="block truncate font-semibold text-primary">{d.titre}</span>
                  <span className="block text-xs text-gray-500">
                    {types[d.type] || d.type} · {d.format === "application/pdf" ? "PDF" : "Image"} · ajouté le {date(d.created_at)}
                  </span>
                </span>
              </a>
              {/* Visibilité sur la vitrine + suppression */}
              <div className="flex items-center gap-2">
                {lectureSeule ? (
                  <span className={`badge ${d.visible_clients ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"}`}>
                    {d.visible_clients ? "Visible par les clients" : "Privé"}
                  </span>
                ) : (
                  <>
                    <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs font-semibold">
                      <input type="checkbox" className="h-4 w-4 accent-primary" checked={!!d.visible_clients} onChange={() => basculer(d)} />
                      Visible par les clients sur ma vitrine
                    </label>
                    <button type="button" className="btn-sm rounded-lg text-red-600 hover:bg-red-50" onClick={() => supprimer(d)}
                      aria-label={`Supprimer ${d.titre}`} title="Supprimer">🗑️</button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* ---------- Ajout d'un document (DG et commerciaux seulement) ---------- */}
      {!lectureSeule && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-3">
          <p className="mb-2 text-sm font-semibold">Ajouter un document</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <input className="input" placeholder="Titre (ex. Brochure 2026)" maxLength={150} value={ajout.titre}
              onKeyDown={bloquerEntree} onChange={(e) => setAjout({ ...ajout, titre: e.target.value })} aria-label="Titre du document" />
            <select className="input" value={ajout.type_document} onChange={(e) => setAjout({ ...ajout, type_document: e.target.value })} aria-label="Type de document">
              {Object.entries(types).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
            </select>
            {/* Champ fichier caché, déclenché par un bouton en français (le bouton natif du navigateur peut être en anglais) */}
            <input ref={champFichier} type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={surFichier}
              className="hidden" aria-label="Fichier" />
            <button type="button" className="btn-outline min-w-0 justify-start overflow-hidden" onClick={() => champFichier.current?.click()}
              title={fichier?.name || ""}>
              <span aria-hidden="true">📂</span>
              <span className="truncate text-sm">{fichier ? fichier.name : "Choisir un fichier…"}</span>
            </button>
            <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm font-semibold">
              <input type="checkbox" className="h-4 w-4 accent-primary" checked={ajout.visible_clients}
                onChange={(e) => setAjout({ ...ajout, visible_clients: e.target.checked })} />
              Visible par les clients
            </label>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button type="button" className="btn-primary btn-sm" disabled={envoi} onClick={ajouter}>{envoi ? "Envoi…" : "⬆ Ajouter le document"}</button>
            <span className="text-xs text-gray-500">PDF, JPEG, PNG ou WebP · 15 Mo maximum</span>
          </div>
        </div>
      )}
    </div>
  );
}
