import { useEffect, useRef, useState } from "react";
import Modal from "@/components/Modal";

// Scanner de QR code avec la caméra du téléphone (bibliothèque html5-qrcode).
// Appelle onResultat(texte) dès qu'un code est lu, puis se ferme.
export default function ScannerQr({ ouvert, onFermer, onResultat }) {
  const zoneId = "zone-scanner-qr";
  const scannerRef = useRef(null);
  const [erreur, setErreur] = useState("");

  useEffect(() => {
    if (!ouvert) return undefined;
    let actif = true;
    setErreur("");
    // Import à la demande : la bibliothèque n'est chargée que si on scanne
    import("html5-qrcode").then(({ Html5Qrcode }) => {
      if (!actif) return;
      const scanner = new Html5Qrcode(zoneId);
      scannerRef.current = scanner;
      scanner
        .start(
          { facingMode: "environment" }, // caméra arrière
          { fps: 10, qrbox: { width: 240, height: 240 } },
          (texte) => {
            scanner.stop().catch(() => {});
            scannerRef.current = null;
            onResultat(texte);
          },
          () => {}, // image sans QR code : on continue
        )
        .catch(() => setErreur("Impossible d'accéder à la caméra. Autorisez-la dans votre navigateur, ou saisissez le code marchand."));
    });
    return () => {
      actif = false;
      scannerRef.current?.stop().catch(() => {});
      scannerRef.current = null;
    };
  }, [ouvert, onResultat]);

  return (
    <Modal ouvert={ouvert} titre="Scanner le QR code de la boutique" onFermer={onFermer}>
      <div id={zoneId} className="overflow-hidden rounded-xl bg-black" />
      {erreur && <p className="mt-3 text-sm text-red-600">{erreur}</p>}
      <p className="mt-3 text-sm text-gray-500">Placez le QR code affiché en boutique dans le cadre.</p>
    </Modal>
  );
}
