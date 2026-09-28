/** @type {import('tailwindcss').Config} */
// Charte adLyn : bleu « télécom » + orange pour les prix et les
// appels à l'action. La couleur de chaque boutique (réglable par son gérant)
// est appliquée dynamiquement via la variable CSS --couleur-boutique.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#0b5ed7",
        "primary-dark": "#083f91",
        accent: "#ff7a00",
        ink: "#111827",
        boutique: "var(--couleur-boutique, #0b5ed7)",
      },
      fontFamily: {
        display: ["Plus Jakarta Sans", "system-ui", "sans-serif"],
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
