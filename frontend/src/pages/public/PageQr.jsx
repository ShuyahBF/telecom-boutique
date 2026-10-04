import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiEspace, memoriserQr } from "@/lib/espaceClient";
import { messageErreur } from "@/lib/api";
import { date } from "@/lib/format";
import Patientez from "@/components/Patientez";
import { LogoAdlyn } from "@/components/Marque";
import VersionApp from "@/components/VersionApp";

// Page ouverte par le QR code d'une facture / proforma : /q/<jeton>
// Le jeton (chiffré par le serveur) désigne la boutique ; il ne contient jamais le
// numéro du client en clair.
//  - Vitrine publique ouverte : on va sur la page publique de la boutique, qui
//    propose « Mon espace » (le jeton est retenu le temps de l'onglet).
//  - Vitrine fermée (boutique non publiée) : page MINIMALE de la boutique ici même
//    (logo, nom, contact) avec le bouton « Mon espace ».
export default function PageQr() {
  const { jeton } = useParams();
  const navigate = useNavigate();
  const [infos, setInfos] = useState(null);
  const [erreur, setErreur] = useState("");

  useEffect(() => {
    apiEspace.get(`/espace-client/qr/${jeton}`)
      .then(({ data }) => {
        if (data.boutique.page_publique && data.boutique.slug) {
          memoriserQr(data.boutique.slug, jeton);
          navigate(`/b/${data.boutique.slug}?espace=1`, { replace: true });
        } else {
          setInfos(data);
          document.title = data.boutique.nom || "adLyn";
        }
      })
      .catch((err) => setErreur(messageErreur(err, "QR code non reconnu")));
  }, [jeton, navigate]);

  if (erreur) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-gray-50 p-6 text-center">
        <LogoAdlyn className="h-10" />
        <h1 className="text-xl font-bold">QR code non reconnu</h1>
        <p className="max-w-sm text-gray-600">{erreur}. Vérifiez le document ou contactez la boutique.</p>
        <Link to="/" className="btn-primary">Voir les boutiques</Link>
      </div>
    );
  }
  if (!infos) return <Patientez actif />;

  const b = infos.boutique;
  return (
    <div style={{ "--couleur-boutique": b.couleur || "#1e90ff" }} className="flex min-h-screen flex-col items-center justify-center bg-gray-50 p-4">
      {/* Carte centrée : logo, nom et coordonnées de la boutique */}
      <div className="w-full max-w-md rounded-2xl bg-white p-6 text-center shadow-xl">
        <img src={b.logo_url || "/marque/logo-adlyn.png"} alt="" className="mx-auto h-20 w-20 object-contain" draggable="false" />
        <h1 className="mt-3 font-display text-2xl font-bold">{b.nom}</h1>
        {b.slogan && <p className="italic text-gray-500">{b.slogan}</p>}
        <div className="mt-4 space-y-1 text-sm text-gray-700">
          {b.adresse && <p>{b.adresse}{b.ville ? `, ${b.ville}` : ""}</p>}
          {b.telephone && <p>📞 <a className="font-semibold text-primary" href={`tel:${b.telephone}`}>{b.telephone}</a></p>}
          {b.email && <p>✉️ <a className="font-semibold text-primary" href={`mailto:${b.email}`}>{b.email}</a></p>}
        </div>
        {infos.document?.numero && (
          <p className="mt-4 rounded-xl bg-gray-50 p-2 text-xs text-gray-600">
            Document {infos.document.numero}{infos.document.date ? ` du ${date(infos.document.date)}` : ""}
          </p>
        )}
        <Link to={`/q/${jeton}/mon-espace`} className="btn-primary mt-6 w-full">👤 Mon espace</Link>
        <p className="mt-2 text-xs text-gray-500">Vos factures, devis, règlements et réparations, avec votre numéro de téléphone.</p>
      </div>
      <div className="mt-6 flex flex-col items-center gap-1 text-gray-400">
        <LogoAdlyn className="h-6" />
        <VersionApp />
      </div>
    </div>
  );
}
