import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { LogoAdlyn } from "@/components/Marque";
import { CONTACT_EMAIL, CONTACT_TELEPHONE, LiensLegaux } from "@/components/PageLegale";
import PoweredBySawali from "@/components/PoweredBySawali";
import VersionApp from "@/components/VersionApp";

// ============================================================================
// PAGE « ACCÈS MOMENTANÉMENT SUSPENDU » (lot 25)
// ============================================================================
// Affichée quand le serveur refuse l'accès parce que le super-administrateur a
// bloqué le compte ou l'adresse IP du visiteur (onglet « Usage » de la plateforme).
// Le site y arrive automatiquement (voir lib/api.js : réponse 403 « acces_suspendu »),
// après avoir effacé la session.
//
// Ton volontairement courtois, SANS détail technique (ni adresse IP, ni motif) :
// on invite simplement à contacter l'Administrateur pour réclamer son accès ou
// contester la décision.
//
// Contact : celui réglé par le super-administrateur dans l'onglet « Usage »
// (e-mail, WhatsApp) ; à défaut, le contact officiel des pages légales.
// ============================================================================
export default function AccesSuspendu() {
  // Contact réglé par l'administrateur ({ email, whatsapp }, vides si non réglés)
  const [contact, setContact] = useState({ email: "", whatsapp: "" });

  useEffect(() => {
    document.title = "adLyn — Accès momentanément suspendu";
    // Route publique : fonctionne sans connexion
    apiClient.get("/acces-suspendu/contact").then(({ data }) => setContact(data)).catch(() => {});
    return () => { document.title = "adLyn"; };
  }, []);

  const email = contact.email || CONTACT_EMAIL;
  // Lien WhatsApp : seulement les chiffres du numéro (format international attendu par wa.me)
  const whatsappChiffres = (contact.whatsapp || "").replace(/\D/g, "");

  return (
    <div className="fond-ondes relative flex min-h-screen items-center justify-center overflow-hidden p-4 pb-24">
      {/* Décor : motif « ondes » de la charte, comme la page de connexion */}

      {/* Carte centrée avec le logo */}
      <div className="carte-acces max-w-md space-y-4 text-center">
        <LogoAdlyn className="mx-auto h-12" />
        <p className="text-4xl" aria-hidden="true">⏸️</p>
        <h1 className="text-xl font-bold">Accès momentanément suspendu</h1>

        {/* Message courtois */}
        <p className="text-sm leading-relaxed text-gray-600">
          Bonjour, l'accès à adLyn est momentanément suspendu pour votre compte ou depuis votre connexion.
        </p>
        <p className="text-sm leading-relaxed text-gray-600">
          Si vous pensez qu'il s'agit d'une erreur, ou pour réclamer votre accès ou contester cette décision,
          nous vous invitons à contacter l'Administrateur : votre demande sera examinée avec attention.
        </p>

        {/* Moyens de contact de la plateforme */}
        <div className="space-y-2 rounded-xl bg-gray-50 p-4 text-sm">
          <p className="font-semibold text-gray-700">Contacter l'Administrateur</p>
          <a href={`mailto:${email}`} className="block font-semibold text-primary hover:underline">✉️ {email}</a>
          {whatsappChiffres ? (
            <a href={`https://wa.me/${whatsappChiffres}`} target="_blank" rel="noreferrer"
              className="block font-semibold text-green-700 hover:underline">
              💬 WhatsApp : {contact.whatsapp}
            </a>
          ) : (
            <a href={`tel:${CONTACT_TELEPHONE.replace(/\s/g, "")}`} className="block font-semibold text-primary hover:underline">
              📞 {CONTACT_TELEPHONE}
            </a>
          )}
        </div>

        <p className="text-sm text-gray-500">Merci de votre compréhension.</p>
        <Link to="/" className="inline-block text-sm font-semibold text-primary">← Retour au portail adLyn</Link>
      </div>

      {/* Liens légaux + mention obligatoire + version/lot (règle permanente) */}
      <div className="absolute bottom-4 left-0 right-0 space-y-1 text-center">
        <LiensLegaux className="justify-center" />
        <PoweredBySawali />
        <VersionApp className="text-gray-400" />
      </div>
    </div>
  );
}
