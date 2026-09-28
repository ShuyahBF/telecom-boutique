import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { useToast } from "@/components/Toast";

// Page de REMERCIEMENT après une commande (/b/:slug/merci?numero=..&telephone=..) :
// affiche le numéro de commande en grand et mène au suivi pré-rempli.
export default function CommandeConfirmee() {
  const { boutique } = useOutletContext();
  const [params] = useSearchParams();
  const toast = useToast();
  const numero = params.get("numero") || "";
  const telephone = params.get("telephone") || "";

  // Adresse du suivi, avec le numéro et le téléphone déjà remplis
  const lienSuivi = `/b/${boutique.slug}/suivi-commande?numero=${encodeURIComponent(numero)}&telephone=${encodeURIComponent(telephone)}`;

  // Copie du numéro de commande dans le presse-papiers
  const copier = async () => {
    try {
      await navigator.clipboard.writeText(numero);
      toast.succes("Numéro copié");
    } catch {
      toast.erreur("Copie impossible : notez le numéro à la main.");
    }
  };

  return (
    <div className="mx-auto max-w-lg">
      <div className="card text-center">
        {/* Grande coche de confirmation */}
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-green-100 text-4xl">✅</div>
        <h1 className="mt-4 text-2xl font-extrabold">Merci pour votre commande !</h1>
        <p className="mt-1 text-gray-600">{boutique.nom} a bien reçu votre commande.</p>

        {/* Numéro de commande bien visible */}
        {numero && (
          <div className="mt-6 rounded-2xl border-2 border-dashed border-gray-300 bg-gray-50 p-4">
            <p className="text-sm text-gray-500">Votre numéro de commande</p>
            <p className="mt-1 break-all font-mono text-3xl font-extrabold tracking-wider text-boutique">{numero}</p>
            <button type="button" className="mt-2 text-sm font-semibold text-boutique" onClick={copier}>📋 Copier le numéro</button>
          </div>
        )}

        {/* Explications : ce qui va se passer ensuite */}
        <ul className="mt-6 space-y-2 text-left text-sm text-gray-700">
          <li className="flex gap-2"><span>📝</span><span><b>Conservez ce numéro</b> : avec votre téléphone, il vous permet de suivre votre commande.</span></li>
          <li className="flex gap-2"><span>📞</span><span>La boutique va vous <b>contacter</b> pour confirmer la commande et convenir du retrait ou de la livraison.</span></li>
          <li className="flex gap-2"><span>🔔</span><span>Si vous avez indiqué un e-mail, vous recevrez un message à chaque étape.</span></li>
        </ul>

        <div className="mt-6 flex flex-col gap-2">
          <Link to={lienSuivi} className="btn-boutique py-3">📦 Suivre ma commande</Link>
          <Link to={`/b/${boutique.slug}`} className="btn-outline">Retour au catalogue</Link>
        </div>
      </div>
    </div>
  );
}
