import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import Chargement from "@/components/Chargement";
import EnTetePage from "@/components/EnTetePage";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import ClientFormulaire from "./_ventes/ClientFormulaire";
import { ListeVide } from "./_ventes/outils";

// Liste des clients avec recherche ; création et modification dans une fenêtre.
export default function Clients() {
  const navigate = useNavigate();
  const toast = useToast();
  const [recherche, setRecherche] = useState("");
  const [clients, setClients] = useState(null);
  const [erreur, setErreur] = useState("");
  // Fenêtre de saisie : null = fermée ; {} = nouveau client ; {id,...} = modification
  const [edition, setEdition] = useState(null);
  const [version, setVersion] = useState(0); // incrémentée pour recharger la liste

  // Chargement (avec 250 ms de délai après la dernière frappe dans la recherche)
  useEffect(() => {
    let annule = false;
    const t = setTimeout(() => {
      apiClient.get("/clients", { params: { q: recherche.trim() } })
        .then(({ data }) => { if (!annule) { setClients(data); setErreur(""); } })
        .catch((err) => { if (!annule) { setClients([]); setErreur(messageErreur(err, "Impossible de charger les clients")); } });
    }, 250);
    return () => { annule = true; clearTimeout(t); };
  }, [recherche, version]);

  // Enregistrement depuis la fenêtre : POST (création) ou PUT (modification)
  async function enregistrer(donnees) {
    try {
      if (edition?.id) {
        await apiClient.put(`/clients/${edition.id}`, donnees);
        toast.succes("Client modifié");
        setEdition(null);
        setVersion((v) => v + 1);
      } else {
        const { data } = await apiClient.post("/clients", donnees);
        toast.succes("Client créé");
        setEdition(null);
        navigate(`/gestion/clients/${data.id}`);
      }
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez le nom, le téléphone (6 caractères minimum) et l'e-mail"));
    }
  }

  return (
    <div>
      <EnTetePage titre="Clients" sousTitre="Particuliers et entreprises de la boutique">
        <button type="button" className="btn-primary btn-sm" onClick={() => setEdition({})}>+ Nouveau client</button>
      </EnTetePage>

      <input className="input mb-4" type="search" placeholder="Rechercher un client (nom, téléphone, e-mail)…" value={recherche}
        onChange={(e) => setRecherche(e.target.value)} />

      {erreur && <p className="card mb-4 text-red-600">{erreur}</p>}
      {!clients ? <Chargement /> : clients.length === 0 ? (
        !erreur && <ListeVide>{recherche ? "Aucun client ne correspond à cette recherche." : "Aucun client pour l'instant."}</ListeVide>
      ) : (
        <>
          {/* Grand écran : tableau */}
          <div className="card hidden overflow-x-auto p-0 md:block">
            <table className="table">
              <thead><tr><th>Nom</th><th>Téléphone</th><th>E-mail</th><th>Adresse</th><th /></tr></thead>
              <tbody>
                {clients.map((c) => (
                  <tr key={c.id} className="cursor-pointer hover:bg-gray-50" onClick={() => navigate(`/gestion/clients/${c.id}`)}>
                    <td>
                      <Link to={`/gestion/clients/${c.id}`} className="font-semibold text-primary" onClick={(e) => e.stopPropagation()}>{c.nom}</Link>
                      {c.type_client === "ENTR" && <span className="badge ml-2 bg-indigo-50 text-indigo-700">Entreprise</span>}
                    </td>
                    <td className="whitespace-nowrap">{c.telephone}</td>
                    <td>{c.email || <span className="text-gray-400">—</span>}</td>
                    <td className="max-w-xs truncate">{c.adresse || <span className="text-gray-400">—</span>}</td>
                    <td className="text-right">
                      <button type="button" className="btn-outline btn-sm" onClick={(e) => { e.stopPropagation(); setEdition(c); }}>Modifier</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Téléphone : cartes */}
          <div className="space-y-2 md:hidden">
            {clients.map((c) => (
              <Link key={c.id} to={`/gestion/clients/${c.id}`} className="card flex items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{c.nom}</p>
                  <p className="text-sm text-gray-500">{c.telephone}{c.type_client === "ENTR" ? " · Entreprise" : ""}</p>
                </div>
                <span className="text-gray-400">›</span>
              </Link>
            ))}
          </div>
          <p className="mt-3 text-xs text-gray-500">{clients.length} client(s)</p>
        </>
      )}

      {/* Fenêtre de création / modification */}
      <Modal ouvert={edition !== null} titre={edition?.id ? `Modifier « ${edition.nom} »` : "Nouveau client"} onFermer={() => setEdition(null)}>
        {edition !== null && (
          <ClientFormulaire key={edition.id || "nouveau"} initial={edition} onEnregistrer={enregistrer}
            libelleBouton={edition.id ? "Enregistrer les modifications" : "Créer le client"} />
        )}
      </Modal>
    </div>
  );
}
