import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { aLeRole, useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, prix } from "@/lib/format";
import { STATUTS_DOCUMENT, STATUTS_SAV } from "@/lib/statuts";
import Badge from "@/components/Badge";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import ClientFormulaire from "./_ventes/ClientFormulaire";
import { BoutonsContact, libelleType, numeroDocument } from "./_ventes/outils";

// Fiche d'un client : coordonnées (modifiables), historique des documents et
// des réparations, raccourcis pour lui faire une facture ou un dépôt SAV.
export default function ClientFiche() {
  const { id } = useParams();
  const toast = useToast();
  const { user, boutique } = useAuth();
  const devise = boutique?.devise || "FCFA";
  // Le technicien n'a pas accès aux factures : historique des documents masqué
  const vendeur = aLeRole(user, "gerant", "vendeur");

  const [client, setClient] = useState(null);
  const [erreur, setErreur] = useState("");
  const [edition, setEdition] = useState(false);

  // Chargement de la fiche (avec son historique)
  useEffect(() => {
    apiClient.get(`/clients/${id}`)
      .then(({ data }) => setClient(data))
      .catch((err) => setErreur(messageErreur(err, "Client introuvable")));
  }, [id]);

  // Modification des coordonnées : PUT /clients/{id} (l'historique déjà chargé est conservé)
  async function enregistrer(donnees) {
    try {
      const { data } = await apiClient.put(`/clients/${id}`, donnees);
      setClient((c) => ({ ...c, ...data }));
      setEdition(false);
      toast.succes("Coordonnées enregistrées");
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez le nom, le téléphone et l'e-mail"));
    }
  }

  if (erreur) {
    return (
      <div className="card text-center">
        <p className="text-red-600">{erreur}</p>
        <Link to="/gestion/clients" className="btn-outline btn-sm mt-4">← Retour aux clients</Link>
      </div>
    );
  }
  if (!client) return <Chargement plein />;

  // Chiffres utiles : total des factures validées
  const facturesValidees = (client.documents || []).filter((d) => d.type_document === "FAC" && d.statut === "VALIDE");
  const totalAchats = facturesValidees.reduce((s, d) => s + (d.total_ttc || 0), 0);

  return (
    <div>
      {/* En-tête : nom et raccourcis */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/gestion/clients" className="text-sm font-semibold text-primary">← Clients</Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-2 text-2xl font-extrabold">
            {client.nom}
            {client.type_client === "ENTR" && <span className="badge bg-indigo-50 text-indigo-700">Entreprise</span>}
          </h1>
          <p className="text-sm text-gray-500">Client depuis le {date(client.created_at)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {vendeur && <Link to={`/gestion/documents/nouveau?type=FAC&client=${client.id}`} className="btn-primary btn-sm">+ Nouvelle facture pour ce client</Link>}
          {vendeur && <Link to={`/gestion/documents/nouveau?type=PRO&client=${client.id}`} className="btn-outline btn-sm">+ Proforma</Link>}
          <Link to={`/gestion/maintenance/nouveau?client=${client.id}`} className="btn-accent btn-sm">🔧 Nouveau dépôt SAV</Link>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Coordonnées */}
        <section className="card space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold">Coordonnées</h2>
            <button type="button" className="btn-outline btn-sm" onClick={() => setEdition(true)}>Modifier</button>
          </div>
          <dl className="space-y-2 text-sm">
            <div><dt className="text-xs text-gray-500">Téléphone</dt><dd className="font-medium">{client.telephone}</dd></div>
            <div><dt className="text-xs text-gray-500">E-mail</dt><dd>{client.email || "—"}</dd></div>
            <div><dt className="text-xs text-gray-500">Adresse</dt><dd className="whitespace-pre-line">{client.adresse || "—"}</dd></div>
            {client.ifu && <div><dt className="text-xs text-gray-500">IFU</dt><dd>{client.ifu}</dd></div>}
            {client.notes && <div><dt className="text-xs text-gray-500">Notes internes</dt><dd className="whitespace-pre-line rounded-lg bg-amber-50 p-2">{client.notes}</dd></div>}
          </dl>
          <BoutonsContact telephone={client.telephone} email={client.email} />
          {vendeur && (
            <div className="rounded-xl bg-gray-50 p-3 text-sm">
              <p className="text-xs text-gray-500">Achats facturés (factures validées)</p>
              <p className="text-lg font-extrabold text-primary">{prix(totalAchats, devise)}</p>
              <p className="text-xs text-gray-500">{facturesValidees.length} facture(s)</p>
            </div>
          )}
        </section>

        <div className="space-y-6 lg:col-span-2">
          {/* Historique des factures et proformas */}
          {vendeur && (
            <section className="card p-0">
              <h2 className="border-b border-gray-100 px-5 py-3 text-lg font-bold">Factures & proformas <span className="text-sm font-normal text-gray-500">({client.documents?.length || 0})</span></h2>
              {client.documents?.length ? (
                <div className="divide-y divide-gray-100">
                  {client.documents.map((d) => (
                    <Link key={d.id} to={`/gestion/documents/${d.id}`} className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-gray-50">
                      <div className="min-w-0">
                        <p className={`font-semibold ${d.numero ? "" : "italic text-gray-500"}`}>{libelleType(d.type_document)} {numeroDocument(d)}</p>
                        <p className="text-xs text-gray-500">{date(d.date)}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-3">
                        <span className="whitespace-nowrap font-semibold">{prix(d.total_ttc, devise)}</span>
                        <Badge table={STATUTS_DOCUMENT} statut={d.statut} />
                      </div>
                    </Link>
                  ))}
                </div>
              ) : <p className="px-5 py-6 text-center text-sm text-gray-500">Aucun document pour ce client.</p>}
            </section>
          )}

          {/* Historique des réparations (dossiers SAV) */}
          <section className="card p-0">
            <h2 className="border-b border-gray-100 px-5 py-3 text-lg font-bold">Réparations (SAV) <span className="text-sm font-normal text-gray-500">({client.dossiers?.length || 0})</span></h2>
            {client.dossiers?.length ? (
              <div className="divide-y divide-gray-100">
                {client.dossiers.map((d) => (
                  <Link key={d.id} to={`/gestion/maintenance/${d.id}`} className="flex items-center justify-between gap-3 px-5 py-3 hover:bg-gray-50">
                    <div className="min-w-0">
                      <p className="font-semibold">{d.numero} <span className="font-normal text-gray-500">· {d.marque} {d.modele}</span></p>
                      <p className="text-xs text-gray-500">Déposé le {date(d.date_depot)}</p>
                    </div>
                    <Badge table={STATUTS_SAV} statut={d.statut} className="shrink-0" />
                  </Link>
                ))}
              </div>
            ) : <p className="px-5 py-6 text-center text-sm text-gray-500">Aucune réparation pour ce client.</p>}
          </section>
        </div>
      </div>

      {/* Fenêtre de modification des coordonnées */}
      <Modal ouvert={edition} titre="Modifier les coordonnées" onFermer={() => setEdition(false)}>
        {edition && <ClientFormulaire initial={client} onEnregistrer={enregistrer} libelleBouton="Enregistrer les modifications" />}
      </Modal>
    </div>
  );
}
