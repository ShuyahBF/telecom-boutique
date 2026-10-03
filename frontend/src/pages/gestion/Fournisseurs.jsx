import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import EnTetePage from "@/components/EnTetePage";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { Case, Champ, Vide } from "./_atelier/communs";

// Fiche fournisseur vierge (mêmes champs que FournisseurSaisie côté API)
const FOURNISSEUR_VIDE = { nom: "", contact: "", telephone: "", email: "", adresse: "", pays: "", notes: "", actif: true };

// Page « Fournisseurs » : liste, recherche, création et modification.
export default function Fournisseurs() {
  const toast = useToast();
  const [fournisseurs, setFournisseurs] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [recherche, setRecherche] = useState("");
  const [edition, setEdition] = useState(null); // fournisseur ouvert dans la fenêtre (null = fermée)
  const [envoi, setEnvoi] = useState(false);

  // Chargement (GET /fournisseurs?q=) avec un petit délai pendant la frappe
  const charger = useCallback((q) => {
    apiClient.get("/fournisseurs", { params: { q } })
      .then(({ data }) => setFournisseurs(data))
      .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger les fournisseurs")))
      .finally(() => setChargement(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const t = setTimeout(() => charger(recherche), 250);
    return () => clearTimeout(t);
  }, [recherche, charger]);

  const maj = (champ, valeur) => setEdition((f) => ({ ...f, [champ]: valeur }));

  // Enregistrement : POST (nouveau) ou PUT (existant)
  async function enregistrer(e) {
    e.preventDefault();
    setEnvoi(true);
    const corps = {
      nom: edition.nom, contact: edition.contact, telephone: edition.telephone, email: edition.email || null,
      adresse: edition.adresse, pays: edition.pays, notes: edition.notes, actif: edition.actif,
    };
    try {
      if (edition.id) await apiClient.put(`/fournisseurs/${edition.id}`, corps);
      else await apiClient.post("/fournisseurs", corps);
      toast.succes(edition.id ? "Fournisseur modifié" : "Fournisseur créé");
      setEdition(null);
      charger(recherche);
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez le nom et l'adresse e-mail"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div>
      <EnTetePage titre="Fournisseurs" sousTitre="Grossistes et distributeurs chez qui vous achetez">
        <button type="button" className="btn-primary" onClick={() => setEdition({ ...FOURNISSEUR_VIDE })}>+ Nouveau fournisseur</button>
      </EnTetePage>

      <input className="input mb-4 sm:max-w-sm" placeholder="🔍 Nom, contact, téléphone…" value={recherche} onChange={(e) => setRecherche(e.target.value)} />

      {/* Liste des fournisseurs ; un clic ouvre la fiche */}
      <div className="card overflow-x-auto p-0">
        {chargement ? <Chargement /> : fournisseurs.length === 0 ? <Vide icone="🚚">Aucun fournisseur.</Vide> : (
          <table className="table min-w-[640px]">
            <thead><tr><th>Nom</th><th>Contact</th><th>Téléphone</th><th>E-mail</th><th>Pays</th><th>État</th></tr></thead>
            <tbody>
              {fournisseurs.map((f) => (
                <tr key={f.id} /* fiche ouverte = ligne sélectionnée (fond orange, index.css) */ aria-selected={edition?.id === f.id} className={`cursor-pointer hover:bg-gray-50 ${f.actif === false ? "opacity-50" : ""}`} onClick={() => setEdition({ ...FOURNISSEUR_VIDE, ...f })}>
                  <td className="font-semibold">{f.nom}</td>
                  <td>{f.contact || "—"}</td>
                  <td className="whitespace-nowrap">{f.telephone ? <a href={`tel:${f.telephone}`} className="text-primary" onClick={(e) => e.stopPropagation()}>{f.telephone}</a> : "—"}</td>
                  <td>{f.email || "—"}</td>
                  <td>{f.pays || "—"}</td>
                  <td>{f.actif === false ? <span className="badge bg-gray-100 text-gray-600">Inactif</span> : <span className="badge bg-green-100 text-green-800">Actif</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Fenêtre de création / modification */}
      <Modal ouvert={!!edition} titre={edition?.id ? "Modifier le fournisseur" : "Nouveau fournisseur"} onFermer={() => setEdition(null)}>
        {edition && (
          <form onSubmit={enregistrer} className="grid gap-3 sm:grid-cols-2">
            <Champ label="Nom *" className="sm:col-span-2"><input className="input" required maxLength={150} value={edition.nom} onChange={(e) => maj("nom", e.target.value)} /></Champ>
            <Champ label="Personne à contacter"><input className="input" maxLength={100} value={edition.contact} onChange={(e) => maj("contact", e.target.value)} /></Champ>
            <Champ label="Téléphone"><input className="input" maxLength={30} value={edition.telephone} onChange={(e) => maj("telephone", e.target.value)} /></Champ>
            <Champ label="E-mail"><input className="input" type="email" value={edition.email} onChange={(e) => maj("email", e.target.value)} /></Champ>
            <Champ label="Pays"><input className="input" maxLength={60} value={edition.pays} onChange={(e) => maj("pays", e.target.value)} placeholder="ex. Burkina Faso, Chine…" /></Champ>
            <Champ label="Adresse" className="sm:col-span-2"><textarea className="input" rows={2} maxLength={500} value={edition.adresse} onChange={(e) => maj("adresse", e.target.value)} /></Champ>
            <Champ label="Notes" className="sm:col-span-2"><textarea className="input" rows={2} maxLength={2000} value={edition.notes} onChange={(e) => maj("notes", e.target.value)} /></Champ>
            <div className="sm:col-span-2"><Case label="Fournisseur actif" aide="Un fournisseur inactif n'est plus proposé dans les nouvelles réceptions." checked={edition.actif} onChange={(v) => maj("actif", v)} /></div>
            <button className="btn-primary sm:col-span-2" disabled={envoi}>{envoi ? "Enregistrement…" : "Enregistrer"}</button>
          </form>
        )}
      </Modal>
    </div>
  );
}
