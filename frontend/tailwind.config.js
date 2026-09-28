/** @type {import('tailwindcss').Config} */
import colors from "tailwindcss/colors";

// Charte adLyn alignée sur celle de SAWALI SMART SYSTEMS (sawalismartsystems.com) :
//  - bleu nuit pour les en-têtes, bandeaux et pieds de page ;
//  - bleu vif (#1e90ff) pour les boutons et les liens ;
//  - indigo (#4f46e5) pour les sur-titres et les mots mis en valeur ;
//  - gris « ardoise » (légèrement bleutés) pour les textes secondaires et les bordures ;
//  - titres en Space Grotesk, textes en Geist, codes en Geist Mono ;
//  - angles plus nets (rayon de base 0,5 rem).
// La couleur de chaque boutique (réglable par son gérant) reste appliquée
// dynamiquement via la variable CSS --couleur-boutique.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Tous les « gray-* » de l'application deviennent les gris ardoise de Sawali
        gray: colors.slate,
        primary: "#1e90ff", // bleu des boutons Sawali
        "primary-dark": "#0a66c2", // survol des boutons
        "primary-clair": "#2ba4ff", // chiffres clés sur fond sombre
        accent: "#4f46e5", // indigo : sur-titres, mots en valeur, prix
        ink: "#081226", // bleu nuit (fond des bandeaux)
        // Nuancier bleu nuit (du plus foncé au plus clair)
        nuit: {
          950: "#050b18", // pied de page
          900: "#081226", // bandeau d'accueil
          800: "#0a1730", // sections sombres
          700: "#0e1f3d", // cartes sur fond sombre
          600: "#152232", // bordures sur fond sombre
        },
        boutique: "var(--couleur-boutique, #1e90ff)",
      },
      fontFamily: {
        sans: ["Geist", "Inter", "-apple-system", "BlinkMacSystemFont", "sans-serif"], // textes
        display: ["Space Grotesk", "sans-serif"], // titres
        mono: ["Geist Mono", "ui-monospace", "monospace"], // codes marchands, références
      },
      borderRadius: {
        // Angles plus nets, comme sur Sawali
        xl: "0.5rem",
        "2xl": "0.75rem",
        "3xl": "1rem",
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
