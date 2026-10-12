import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { apiClient, messageErreur } from "@/lib/api";
import Modal from "@/components/Modal";
import Patientez from "@/components/Patientez";
import QrCode from "@/components/QrCode";
import IconePartage from "@/components/IconePartage";
import { useToast } from "@/components/Toast";

// ============================================================================
// Lot E — BOUTON « PARTAGER » (boutique ou produit)
// ============================================================================
// Le DG ou un collaborateur envoie le lien de la vitrine de sa boutique, ou celui
// d'un article. Un clic ouvre une fenêtre qui propose :
//   - le partage natif du téléphone (navigator.share : WhatsApp, SMS, Facebook…
//     au choix de l'utilisateur), quand le navigateur le permet ;
//   - WhatsApp (wa.me avec le message prérempli) ;
//   - Facebook (sharer.php) ;
//   - « Copier le lien » (toast « Lien copié ») ;
//   - le QR code du lien.
// Le message prérempli est MODIFIABLE avant l'envoi.
//
// Le lien et le message viennent du serveur (GET /partage/lien ou
// /partage/lien/produit/{id}) : ils pointent vers une page de partage de l'API
// (aperçu WhatsApp / Facebook avec photo, titre et prix) qui renvoie aussitôt
// le client vers la vitrine. Le serveur dit aussi si le partage est possible
// (boutique validée, produit visible, actif et avec un prix) et sinon pourquoi.
// Le canal utilisé est ajouté au lien (?via=whatsapp|facebook|copie|qr|natif)
// pour compter les ouvertures, sans aucune donnée personnelle.
//
// Usage : <BoutonPartager />                       -> la boutique
//         <BoutonPartager produit={{ id, nom }} /> -> un article
// Props facultatives : libelle, className, titre (infobulle).
// ============================================================================

/** Ajoute le canal (?via=...) à un lien de partage. */
function avecCanal(url, canal) {
  if (!url) return "";
  return `${url}${url.includes("?") ? "&" : "?"}via=${encodeURIComponent(canal)}`;
}

/** Message à envoyer pour un canal : le lien du message reçoit son ?via=, ou est ajouté s'il a été effacé. */
function messagePour(message, url, canal) {
  const lien = avecCanal(url, canal);
  const texte = (message || "").trim();
  if (!url) return texte;
  return texte.includes(url) ? texte.split(url).join(lien) : `${texte}${texte ? " " : ""}${lien}`;
}

export default function BoutonPartager({ produit = null, libelle, className = "btn-outline btn-sm", titre }) {
  const toast = useToast();
  const [ouvert, setOuvert] = useState(false);
  const [chargement, setChargement] = useState(false);
  const [infos, setInfos] = useState(null); // réponse du serveur (lien, message, partageable, raison…)
  const [message, setMessage] = useState(""); // message prérempli, modifiable
  const [qrVisible, setQrVisible] = useState(false);
  // Partage natif disponible ? (téléphones, certains navigateurs d'ordinateur)
  const natif = typeof navigator !== "undefined" && typeof navigator.share === "function";

  // Ouverture de la fenêtre : lecture du lien et du message auprès du serveur
  // (toast « Patientez… » + jauge circulaire pendant l'attente, règle du propriétaire)
  useEffect(() => {
    if (!ouvert) return;
    setChargement(true);
    setInfos(null);
    setQrVisible(false);
    const adresse = produit ? `/partage/lien/produit/${produit.id}` : "/partage/lien";
    apiClient.get(adresse)
      .then(({ data }) => { setInfos(data); setMessage(data.message || ""); })
      .catch((err) => { toast.erreur(messageErreur(err, "Lien de partage indisponible")); setOuvert(false); })
      .finally(() => setChargement(false));
  }, [ouvert, produit?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Partage natif du téléphone (l'utilisateur choisit l'application)
  async function partagerNatif() {
    try {
      await navigator.share({ title: infos.titre, text: messagePour(message, infos.url, "natif") });
    } catch (err) {
      // Annulation par l'utilisateur : rien à signaler
      if (err?.name !== "AbortError") toast.erreur("Partage impossible depuis ce navigateur");
    }
  }

  // Copie dans le presse-papiers (lien seul, ou message complet)
  async function copier(texte, confirmation) {
    try {
      await navigator.clipboard.writeText(texte);
      toast.succes(confirmation);
    } catch {
      toast.erreur("Copie impossible : sélectionnez le texte à la main");
    }
  }

  // Liens WhatsApp (message prérempli) et Facebook (adresse seule : Facebook n'accepte pas de texte)
  const lienWhatsApp = infos?.url ? `https://wa.me/?text=${encodeURIComponent(messagePour(message, infos.url, "whatsapp"))}` : "";
  const lienFacebook = infos?.url ? `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(avecCanal(infos.url, "facebook"))}` : "";
  // Texte du bouton (sans pictogramme : l'icône « Partager » usuelle est ajoutée devant).
  // libelle = "" → bouton réduit à l'icône (barre du haut sur téléphone, lignes du tableau).
  const intitule = libelle ?? (produit ? "Partager" : "Partager ma boutique");

  return (
    // Les clics dans la fenêtre ne remontent pas à la ligne du tableau (qui ouvrirait la fiche)
    <span className={`no-print ${className.includes("w-full") ? "flex w-full" : "inline-flex"}`} onClick={(e) => e.stopPropagation()}>
      <button type="button" className={className} title={titre || (produit ? `Partager « ${produit.nom} »` : "Partager le lien de ma vitrine")}
        onClick={(e) => { e.preventDefault(); setOuvert(true); }}>
        <span className="inline-flex items-center gap-1.5">
          <IconePartage />
          {intitule && <span>{intitule}</span>}
        </span>
      </button>
      {/* « Patientez… » pendant la lecture du lien (rendu à la racine de la page, lui aussi) */}
      {chargement && createPortal(<Patientez actif />, document.body)}
      {/* Fenêtre rendue à la racine de la page : jamais gênée par la ligne de tableau qui la contient */}
      {ouvert && infos && createPortal(
        <div onClick={(e) => e.stopPropagation()}>
          <Modal ouvert titre={produit ? "Partager cet article" : "Partager ma boutique"} onFermer={() => setOuvert(false)}>
            {!infos.partageable ? (
              // Partage impossible : raison explicite (boutique non validée, article masqué…)
              <div className="rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="alert">
                <p className="font-semibold">🔒 Partage indisponible</p>
                <p className="mt-1">{infos.raison}</p>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="font-semibold">{infos.titre}</p>
                {/* Message prérempli, modifiable avant l'envoi */}
                <div>
                  <label className="label" htmlFor="message-partage">Message (modifiable)</label>
                  <textarea id="message-partage" className="input min-h-[96px]" maxLength={1000} value={message}
                    onChange={(e) => setMessage(e.target.value)} />
                  <button type="button" className="mt-1 text-xs font-semibold text-primary" onClick={() => setMessage(infos.message)}>
                    ↺ Revenir au message proposé
                  </button>
                </div>

                {/* Canaux de partage */}
                <div className="grid gap-2 sm:grid-cols-2">
                  {natif && (
                    <button type="button" className="btn-primary sm:col-span-2" onClick={partagerNatif}>
                      <span className="inline-flex items-center justify-center gap-2"><IconePartage /> Partager… (WhatsApp, SMS, Facebook…)</span>
                    </button>
                  )}
                  <a className="btn-outline justify-center" href={lienWhatsApp} target="_blank" rel="noopener noreferrer">🟢 WhatsApp</a>
                  <a className="btn-outline justify-center" href={lienFacebook} target="_blank" rel="noopener noreferrer">🔵 Facebook</a>
                  <button type="button" className="btn-outline" onClick={() => copier(avecCanal(infos.url, "copie"), "Lien copié")}>📋 Copier le lien</button>
                  <button type="button" className="btn-outline" onClick={() => copier(messagePour(message, infos.url, "copie"), "Message copié")}>📝 Copier le message</button>
                  <button type="button" className="btn-outline sm:col-span-2" onClick={() => setQrVisible((v) => !v)}>
                    {qrVisible ? "Masquer le QR code" : "▦ Afficher le QR code"}
                  </button>
                </div>

                {/* QR code du lien (à faire scanner ou à capturer) */}
                {qrVisible && (
                  <div className="flex flex-col items-center gap-2 rounded-2xl bg-gray-50 p-4 text-center">
                    <QrCode valeur={avecCanal(infos.url, "qr")} taille={240} className="h-auto w-full max-w-[240px]" />
                    <p className="text-xs text-gray-500">Le client scanne ce QR code avec l'appareil photo de son téléphone.</p>
                  </div>
                )}

                {/* Lien affiché (sélection manuelle possible) + statistiques */}
                <div>
                  <p className="label">Lien partagé</p>
                  <input className="input font-mono text-xs" readOnly value={infos.url} onFocus={(e) => e.target.select()} />
                  <p className="mt-1 text-xs text-gray-500">
                    Ce lien affiche un aperçu (photo, nom{produit ? ", prix" : ""}) dans WhatsApp et Facebook, puis ouvre la vitrine.
                    {" "}Ouvert {infos.ouvertures || 0} fois via un lien partagé.
                  </p>
                  {infos.url_vitrine && (
                    <a href={infos.url_vitrine} target="_blank" rel="noreferrer" className="mt-1 inline-block text-sm font-semibold text-primary">Voir la page sur la vitrine ↗</a>
                  )}
                </div>
              </div>
            )}
          </Modal>
        </div>,
        document.body,
      )}
    </span>
  );
}
