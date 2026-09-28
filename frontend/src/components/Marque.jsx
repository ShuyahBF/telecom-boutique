// Logo et icône officiels d'adLyn (fichiers dans public/marque/).
// - LogoAdlyn : pictogramme + « adLyn » (en-têtes, connexion, pieds de page)
// - IconeAdlyn : pictogramme seul, carré (petits emplacements)
// clair = true : version où le bleu nuit devient blanc, pour les fonds sombres.
// La hauteur se règle avec className (ex. « h-9 ») ; la largeur suit automatiquement.

export function LogoAdlyn({ clair = false, className = "h-9" }) {
  return (
    <img
      src={clair ? "/marque/logo-adlyn-clair.png" : "/marque/logo-adlyn.png"}
      alt="adLyn"
      className={`w-auto select-none ${className}`}
      draggable="false"
    />
  );
}

export function IconeAdlyn({ clair = false, className = "h-9 w-9" }) {
  return (
    <img
      src={clair ? "/marque/icone-adlyn-clair.png" : "/marque/icone-adlyn.png"}
      alt="adLyn"
      className={`select-none object-contain ${className}`}
      draggable="false"
    />
  );
}
