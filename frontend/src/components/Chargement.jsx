// Indicateur de chargement (roue qui tourne + texte facultatif)
export default function Chargement({ texte = "Chargement…", plein = false }) {
  return (
    <div className={`flex items-center justify-center gap-3 text-gray-500 ${plein ? "min-h-[60vh]" : "py-10"}`}>
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-primary" />
      <span>{texte}</span>
    </div>
  );
}
