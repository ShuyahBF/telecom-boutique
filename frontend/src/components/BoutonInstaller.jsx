import { useEffect, useState } from "react";
import Modal from "@/components/Modal";

// Bouton « Installer l'application » (application Android installable, PWABuilder / TWA).
// Chrome propose l'installation par l'événement « beforeinstallprompt » (gardé de côté dans main.jsx) :
// on l'offre sur ce bouton. Si le navigateur ne le propose pas (iPhone, Firefox, déjà installée…),
// le bouton ouvre une petite fenêtre qui explique les gestes à faire.
// Rien n'est affiché quand le site tourne déjà comme application installée.
export default function BoutonInstaller({ className = "" }) {
  const [invite, setInvite] = useState(window.__adlynInvite || null);
  const [aide, setAide] = useState(false);
  // Déjà installée : le site est ouvert en plein écran (mode « standalone »)
  const [installee, setInstallee] = useState(
    window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone === true,
  );

  useEffect(() => {
    const surInvite = (e) => { e.preventDefault(); window.__adlynInvite = e; setInvite(e); };
    const surInstallation = () => { window.__adlynInvite = null; setInvite(null); setInstallee(true); };
    window.addEventListener("beforeinstallprompt", surInvite);
    window.addEventListener("appinstalled", surInstallation);
    return () => {
      window.removeEventListener("beforeinstallprompt", surInvite);
      window.removeEventListener("appinstalled", surInstallation);
    };
  }, []);

  if (installee) return null;

  // Clic : installation directe si Chrome l'a proposée, sinon explication des gestes
  const installer = async () => {
    if (!invite) { setAide(true); return; }
    invite.prompt();
    try { await invite.userChoice; } catch { /* choix ignoré */ }
    window.__adlynInvite = null; setInvite(null);
  };

  const estIphone = /iphone|ipad|ipod/i.test(navigator.userAgent);
  return (
    <>
      <button type="button" className={`btn-outline w-full ${className}`} onClick={installer}>
        📲 Installer l'application
      </button>
      <Modal ouvert={aide} titre="Installer l'application adLyn" onFermer={() => setAide(false)}>
        {estIphone ? (
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            <li>Ouvrez ce site dans <b>Safari</b>.</li>
            <li>Touchez le bouton <b>Partager</b> (carré avec une flèche vers le haut).</li>
            <li>Choisissez <b>Sur l'écran d'accueil</b>.</li>
          </ol>
        ) : (
          <>
            <p className="mb-2 text-sm">Sur Android, avec <b>Chrome</b> :</p>
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              <li>Touchez le menu <b>⋮</b> en haut à droite.</li>
              <li>Choisissez <b>Installer l'application</b> (ou <b>Ajouter à l'écran d'accueil</b>).</li>
              <li>Confirmez : l'icône adLyn apparaît sur votre écran d'accueil.</li>
            </ol>
            <p className="mt-3 text-xs text-gray-500">Le bouton d'installation direct n'apparaît que dans Chrome, quand le site est ouvert depuis une adresse sécurisée.</p>
          </>
        )}
        <button type="button" className="btn-primary mt-4 w-full" onClick={() => setAide(false)}>Compris</button>
      </Modal>
    </>
  );
}
