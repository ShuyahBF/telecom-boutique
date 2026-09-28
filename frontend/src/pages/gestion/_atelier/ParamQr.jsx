import { useAuth } from "@/context/AuthContext";
import QrCode from "@/components/QrCode";
import { useToast } from "@/components/Toast";

// Onglet « QR code & partage » : QR code géant vers la vitrine, lien à partager,
// et affiche A4 à imprimer pour la vitrine du magasin.
export default function ParamQr() {
  const { boutique } = useAuth();
  const toast = useToast();
  const lien = `${window.location.origin}/b/${boutique.slug}`;

  // Copie du lien dans le presse-papiers
  async function copier() {
    try {
      await navigator.clipboard.writeText(lien);
      toast.succes("Lien copié");
    } catch {
      toast.erreur("Copie impossible : sélectionnez le lien à la main");
    }
  }

  return (
    <>
      {/* Partie visible à l'écran (jamais imprimée) */}
      <div className="no-print grid gap-5 lg:grid-cols-2">
        <div className="card flex flex-col items-center text-center">
          <QrCode valeur={lien} taille={320} className="h-auto w-full max-w-[320px]" />
          <p className="mt-3 text-sm text-gray-500">Vos clients scannent ce QR code avec l'appareil photo de leur téléphone.</p>
        </div>
        <div className="card space-y-4">
          <div>
            <p className="label">Lien de votre vitrine</p>
            <div className="flex gap-2">
              <input className="input font-mono text-sm" readOnly value={lien} onFocus={(e) => e.target.select()} />
              <button type="button" className="btn-outline shrink-0" onClick={copier}>Copier</button>
            </div>
            <a href={lien} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm font-semibold text-primary">Ouvrir ma vitrine ↗</a>
          </div>
          <div>
            <p className="label">Code marchand</p>
            <p className="font-mono text-3xl font-extrabold tracking-widest">{boutique.code_marchand}</p>
            <p className="text-xs text-gray-500">Les clients peuvent aussi retrouver votre boutique en tapant ce code sur la page d'accueil.</p>
          </div>
          <div className="rounded-xl bg-gray-50 p-4">
            <p className="mb-2 font-semibold">Affiche pour votre vitrine</p>
            <p className="mb-3 text-sm text-gray-600">Imprimez cette affiche au format A4 et collez-la sur votre vitrine ou votre comptoir.</p>
            <button type="button" className="btn-primary" onClick={() => window.print()}>🖨️ Imprimer l'affiche</button>
          </div>
        </div>
      </div>

      {/* Affiche A4 : invisible à l'écran, seule chose imprimée depuis cet onglet */}
      <style>{"@page { size: A4; margin: 12mm }"}</style>
      <div className="hidden print:block">
        <div className="flex min-h-[260mm] flex-col items-center justify-between rounded-3xl border-8 p-10 text-center"
          style={{ borderColor: boutique.couleur || "#0b5ed7" }}>
          <div className="flex flex-col items-center">
            {boutique.logo_url && <img src={boutique.logo_url} alt="" className="mb-4 h-28 w-28 object-contain" />}
            <h1 className="text-5xl font-extrabold">{boutique.nom}</h1>
            {boutique.slogan && <p className="mt-2 text-xl text-gray-600">{boutique.slogan}</p>}
          </div>
          <p className="text-3xl font-bold leading-snug">Scannez pour voir nos téléphones,<br />commander et suivre vos réparations</p>
          <QrCode valeur={lien} taille={600} className="h-[110mm] w-[110mm]" />
          <div>
            <p className="text-lg text-gray-600">{window.location.host}/b/{boutique.slug}</p>
            <p className="mt-2 text-2xl">Code marchand : <b className="font-mono tracking-widest">{boutique.code_marchand}</b></p>
          </div>
        </div>
      </div>
    </>
  );
}
