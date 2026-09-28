// Petits composants partagés par les pages « catalogue, stock, atelier,
// paramètres » (privés à ce dossier : les autres pages ne les utilisent pas).
import { useRef, useState } from "react";

// Champ de formulaire : un libellé au-dessus, le contrôle en dessous,
// et une aide facultative en petit texte gris.
export function Champ({ label, aide, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="label">{label}</span>
      {children}
      {aide && <span className="mt-1 block text-xs text-gray-500">{aide}</span>}
    </label>
  );
}

// Case à cocher avec son libellé (et une explication facultative)
export function Case({ label, aide, checked, onChange, disabled = false }) {
  return (
    <label className={`flex items-start gap-3 rounded-xl border border-gray-200 px-3 py-2.5 ${disabled ? "opacity-60" : "cursor-pointer hover:bg-gray-50"}`}>
      <input type="checkbox" className="mt-1 h-4 w-4 accent-primary" checked={!!checked} disabled={disabled}
        onChange={(e) => onChange(e.target.checked)} />
      <span>
        <span className="block text-sm font-semibold text-gray-800">{label}</span>
        {aide && <span className="block text-xs text-gray-500">{aide}</span>}
      </span>
    </label>
  );
}

// Barre d'onglets horizontale (défile sur mobile si elle est trop large).
// onglets = [{ code, libelle }] ; actif = code de l'onglet affiché
export function Onglets({ onglets, actif, onChange }) {
  return (
    <div className="no-print -mx-1 mb-5 flex gap-1 overflow-x-auto border-b border-gray-200 px-1">
      {onglets.map((o) => (
        <button key={o.code} type="button" onClick={() => onChange(o.code)}
          className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-semibold transition ${
            actif === o.code ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-800"}`}>
          {o.libelle}
        </button>
      ))}
    </div>
  );
}

// Message « liste vide » centré, avec une icône
export function Vide({ icone = "📭", children }) {
  return (
    <div className="py-12 text-center text-gray-500">
      <div className="mb-2 text-4xl">{icone}</div>
      <p>{children}</p>
    </div>
  );
}

// Choix d'une image (photo produit, logo) avec aperçu et envoi immédiat.
// - image : adresse de l'image actuelle (ou null)
// - onEnvoyer(fichier) : fonction asynchrone qui envoie le fichier à l'API
// - desactive : true pour cacher le bouton (lecture seule, produit pas encore créé...)
export function ChoixImage({ image, onEnvoyer, desactive = false, texteDesactive = "", carre = true }) {
  const champ = useRef(null);
  const [envoi, setEnvoi] = useState(false);

  // Quand l'utilisateur a choisi un fichier : on l'envoie tout de suite
  async function surChoix(e) {
    const fichier = e.target.files?.[0];
    e.target.value = ""; // permet de rechoisir le même fichier plus tard
    if (!fichier) return;
    setEnvoi(true);
    try {
      await onEnvoyer(fichier);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <div className={`flex items-center justify-center overflow-hidden rounded-2xl border border-dashed border-gray-300 bg-gray-50 ${carre ? "h-44 w-44" : "h-28 w-56"}`}>
        {image
          ? <img src={image} alt="Aperçu" className="h-full w-full object-contain" />
          : <span className="text-4xl text-gray-300">🖼️</span>}
      </div>
      {desactive ? (
        texteDesactive && <p className="max-w-[14rem] text-center text-xs text-gray-500">{texteDesactive}</p>
      ) : (
        <>
          <input ref={champ} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={surChoix} />
          <button type="button" className="btn-outline btn-sm" disabled={envoi} onClick={() => champ.current?.click()}>
            {envoi ? "Envoi…" : image ? "Changer l'image" : "Choisir une image"}
          </button>
          <p className="text-xs text-gray-500">JPEG, PNG ou WebP · 5 Mo maximum</p>
        </>
      )}
    </div>
  );
}

// Numéro de téléphone -> lien WhatsApp (chiffres uniquement, sans le « + »)
export function lienWhatsApp(telephone, texte = "") {
  const chiffres = String(telephone || "").replace(/\D/g, "");
  return `https://wa.me/${chiffres}${texte ? `?text=${encodeURIComponent(texte)}` : ""}`;
}
