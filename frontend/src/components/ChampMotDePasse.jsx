import { useState } from "react";

// Champ de saisie SECRÈTE (mot de passe, code reçu) avec un bouton « œil »
// pour afficher ou masquer ce qui est tapé. Chaque champ a son propre œil.
//   - Toutes les propriétés habituelles d'un <input> sont transmises telles
//     quelles (id, value, onChange, autoComplete, required, maxLength...).
//   - visibleParDefaut : true pour un champ affiché en clair au départ
//     (ex. mot de passe provisoire choisi par le DG, à recopier).
//   - classeConteneur : classes du bloc qui entoure le champ (ex. « flex-1 »).
//   - Le bouton est de type « button » : il ne soumet jamais le formulaire, et
//     il est atteignable au clavier (Tab, puis Entrée ou Espace).
export default function ChampMotDePasse({ className = "input", visibleParDefaut = false, classeConteneur = "", ...proprietes }) {
  const [visible, setVisible] = useState(visibleParDefaut);
  return (
    <div className={`relative ${classeConteneur}`}>
      <input {...proprietes} type={visible ? "text" : "password"} className={`${className} pr-11`} />
      <button type="button" onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Masquer le mot de passe" : "Afficher le mot de passe"}
        title={visible ? "Masquer le mot de passe" : "Afficher le mot de passe"}
        className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-lg text-gray-500 hover:text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary">
        {visible ? <OeilBarre /> : <Oeil />}
      </button>
    </div>
  );
}

// Icônes dessinées en SVG (aucune bibliothèque d'icônes dans le projet)
function Oeil() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function OeilBarre() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.6 5.1A10.4 10.4 0 0 1 12 5c6.5 0 10 7 10 7a17.6 17.6 0 0 1-3.1 4.1" />
      <path d="M6.6 6.6C3.9 8.4 2 12 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
      <path d="M2 2l20 20" />
    </svg>
  );
}
