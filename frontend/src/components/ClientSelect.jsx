import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import Modal from "@/components/Modal";

// Choix d'un client (recherche par nom ou téléphone) avec création rapide.
// value = client sélectionné ({id, nom, telephone...}) ; onChange(client)
export default function ClientSelect({ value, onChange, disabled = false }) {
  const [recherche, setRecherche] = useState("");
  const [resultats, setResultats] = useState([]);
  const [ouvert, setOuvert] = useState(false);
  const [creation, setCreation] = useState(false);
  const [nouveau, setNouveau] = useState({ nom: "", telephone: "", email: "", adresse: "", type_client: "PART", ifu: "" });
  const [erreur, setErreur] = useState("");

  // Recherche avec un petit délai (évite une requête à chaque lettre tapée)
  useEffect(() => {
    if (!ouvert) return undefined;
    const t = setTimeout(() => {
      apiClient.get("/clients", { params: { q: recherche } }).then(({ data }) => setResultats(data.slice(0, 20))).catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [recherche, ouvert]);

  async function creer(e) {
    e.preventDefault();
    setErreur("");
    try {
      const { data } = await apiClient.post("/clients", { ...nouveau, email: nouveau.email || null });
      onChange(data);
      setCreation(false);
      setOuvert(false);
    } catch (err) {
      setErreur(messageErreur(err, "Vérifiez le nom et le téléphone"));
    }
  }

  return (
    <div className="relative">
      {value && !ouvert ? (
        <div className="flex items-center justify-between gap-2 rounded-xl border border-gray-300 px-3 py-2.5">
          <div>
            <div className="font-semibold">{value.nom}</div>
            <div className="text-xs text-gray-500">{value.telephone}</div>
          </div>
          {!disabled && <button type="button" className="text-sm font-semibold text-primary" onClick={() => setOuvert(true)}>Changer</button>}
        </div>
      ) : (
        <input
          className="input" placeholder="Rechercher un client (nom, téléphone)…" value={recherche} disabled={disabled}
          onFocus={() => setOuvert(true)} onChange={(e) => setRecherche(e.target.value)}
        />
      )}
      {ouvert && !disabled && (
        <div className="absolute z-30 mt-1 w-full rounded-xl border border-gray-200 bg-white shadow-lg">
          <div className="max-h-64 overflow-y-auto">
            {resultats.map((c) => (
              <button key={c.id} type="button" className="block w-full px-3 py-2 text-left hover:bg-gray-50"
                onClick={() => { onChange(c); setOuvert(false); setRecherche(""); }}>
                <span className="font-medium">{c.nom}</span> <span className="text-sm text-gray-500">{c.telephone}</span>
              </button>
            ))}
            {resultats.length === 0 && <p className="px-3 py-2 text-sm text-gray-500">Aucun client trouvé.</p>}
          </div>
          <div className="flex justify-between border-t border-gray-100 p-2">
            <button type="button" className="btn-outline btn-sm" onClick={() => { setNouveau((n) => ({ ...n, nom: recherche })); setCreation(true); }}>+ Nouveau client</button>
            <button type="button" className="btn-sm text-gray-500" onClick={() => setOuvert(false)}>Fermer</button>
          </div>
        </div>
      )}
      <Modal ouvert={creation} titre="Nouveau client" onFermer={() => setCreation(false)}>
        <form onSubmit={creer} className="space-y-3">
          <div><label className="label">Nom / Raison sociale</label><input className="input" required value={nouveau.nom} onChange={(e) => setNouveau({ ...nouveau, nom: e.target.value })} /></div>
          <div><label className="label">Téléphone</label><input className="input" required value={nouveau.telephone} onChange={(e) => setNouveau({ ...nouveau, telephone: e.target.value })} /></div>
          <div><label className="label">E-mail (facultatif)</label><input className="input" type="email" value={nouveau.email} onChange={(e) => setNouveau({ ...nouveau, email: e.target.value })} /></div>
          <div><label className="label">Adresse</label><input className="input" value={nouveau.adresse} onChange={(e) => setNouveau({ ...nouveau, adresse: e.target.value })} /></div>
          {erreur && <p className="text-sm text-red-600">{erreur}</p>}
          <button className="btn-primary w-full">Créer le client</button>
        </form>
      </Modal>
    </div>
  );
}
