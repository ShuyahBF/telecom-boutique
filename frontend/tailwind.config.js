/** @type {import('tailwindcss').Config} */
import colors from "tailwindcss/colors";

// =============================================================================
// CHARTE adLyn « Ondes & comptoir » (refonte de l'interface, lot de refonte)
// =============================================================================
// Direction : une plateforme pour les boutiques de téléphonie du Burkina Faso.
//  - « encre »   : le bleu nuit du logo adLyn (bandeaux, barre latérale, textes) ;
//  - « signal »  : le bleu du logo, un ton plus profond pour rester lisible
//                  (texte blanc sur bouton : contraste suffisant) ;
//  - « ciel »    : le bleu clair de l'anneau du logo (chiffres et liens sur fond sombre) ;
//  - « monnaie » : un vert profond, celui du mobile money, pour les prix, les
//                  compteurs et les mises en valeur (remplace l'ancien indigo) ;
//  - gris « ardoise » (légèrement bleutés) pour les textes secondaires et les bordures.
// Typographie : titres en Bricolage Grotesque (lettrage d'enseigne peinte,
// caractère affirmé), textes en Instrument Sans (net et compact, idéal pour
// les tableaux), codes (ID boutique, code marchand) en Geist Mono.
// Les NOMS des couleurs (primary, accent, ink, nuit…) sont conservés : toutes
// les pages prennent la nouvelle charte sans être réécrites.
// La couleur de chaque boutique (réglable par son gérant) reste appliquée
// dynamiquement via la variable CSS --couleur-boutique.
// =============================================================================
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Tous les « gray-* » de l'application deviennent les gris ardoise de Sawali
        gray: colors.slate,
        primary: "#1668e3", // « signal » : boutons et liens (bleu du logo, approfondi)
        "primary-dark": "#0f52b8", // survol des boutons
        "primary-clair": "#5cb0ff", // « ciel » : chiffres et liens sur fond sombre
        accent: "#0b7a5d", // « monnaie » : prix, compteurs, mises en valeur
        ink: "#121a2c", // « encre » : bleu nuit du logo (textes, bandeaux)
        // Nuancier « encre » (du plus foncé au plus clair), dérivé du logo
        nuit: {
          950: "#0a0f1c", // pied de page
          900: "#121a2c", // barre latérale, bandeau d'accueil
          800: "#18223a", // sections sombres
          700: "#1f2b47", // cartes sur fond sombre
          600: "#2a3757", // bordures sur fond sombre
        },
        // Fond général des écrans (gris bleuté très pâle, posé sur <body>)
        papier: "#eef1f6",
        boutique: "var(--couleur-boutique, #1e90ff)",
      },
      fontFamily: {
        sans: ["Instrument Sans", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"], // textes
        display: ["Bricolage Grotesque", "Instrument Sans", "sans-serif"], // titres
        mono: ["Geist Mono", "ui-monospace", "monospace"], // codes marchands, références
      },
      borderRadius: {
        // Hiérarchie des arrondis : champs et boutons (lg/xl) < cartes (2xl) < fenêtres (3xl)
        xl: "0.625rem",
        "2xl": "0.875rem",
        "3xl": "1.25rem",
      },
      keyframes: {
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        "slide-up": { "0%": { transform: "translateY(12px)", opacity: "0" }, "100%": { transform: "translateY(0)", opacity: "1" } },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out",
        "slide-up": "slide-up 0.25s ease-out",
      },
    },
  },
  plugins: [],
};
