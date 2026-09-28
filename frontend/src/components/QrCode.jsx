import { useEffect, useState } from "react";
import QRCode from "qrcode";

// Affiche un QR code pour un texte ou une adresse web (ex. lien de la boutique).
export default function QrCode({ valeur, taille = 220, className = "" }) {
  const [image, setImage] = useState("");

  useEffect(() => {
    // Génère l'image du QR code (format PNG encodé en texte)
    QRCode.toDataURL(valeur, { width: taille, margin: 1, errorCorrectionLevel: "M" })
      .then(setImage)
      .catch(() => setImage(""));
  }, [valeur, taille]);

  if (!image) return <div style={{ width: taille, height: taille }} className="animate-pulse rounded-xl bg-gray-100" />;
  return <img src={image} width={taille} height={taille} alt={`QR code : ${valeur}`} className={className} />;
}
