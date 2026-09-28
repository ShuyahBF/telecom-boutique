import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure, montant, prix } from "@/lib/format";
import { STATUTS_COMMANDE, STATUTS_DOCUMENT, STATUTS_PAIEMENT_COMMANDE } from "@/lib/statuts";
import Badge from "@/components/Badge";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import Confirmation from "./_ventes/Confirmation";
import { BadgePaiement, BoutonsContact } from "./_ventes/outils";

// Étapes normales d'une commande, dans l'ordre (l'annulation est à part)
const ETAPES = ["RECUE", "CONFIRMEE", "PREPARATION", "PRETE", "LIVREE"];

// Fiche d'une commande en ligne : détail, suivi du statut, facturation.
export default function CommandeFiche() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { boutique } = useAuth();
  const devise = boutique?.devise || "FCFA";

  const [cmd, setCmd] = useState(null);
  const [erreur, setErreur] = useState("");
  const [facture, setFacture] = useState(null); // facture liée (pour afficher son n° et son statut)
  // Formulaire de changement de statut (statut choisi + note interne)
  const [nouveauStatut, setNouveauStatut] = useState("");
  const [note, setNote] = useState("");
  const [enCours, setEnCours] = useState("");
  const [confirmerAnnulation, setConfirmerAnnulation] = useState(false);

  // Recopie la commande reçue du serveur dans l'écran
  function remplir(data) {
    setCmd(data);
    setNouveauStatut(data.statut);
    setNote(data.note_interne || "");
  }

  // Chargement de la commande
  useEffect(() => {
    apiClient.get(`/commandes/${id}`)
      .then(({ data }) => remplir(data))
      .catch((err) => setErreur(messageErreur(err, "Commande introuvable")));
  }, [id]);

  // Chargement de la facture liée, s'il y en a une
  useEffect(() => {
    if (!cmd?.facture_id) {
      setFacture(null);
      return;
    }
    apiClient.get(`/documents/${cmd.facture_id}`).then(({ data }) => setFacture(data)).catch(() => setFacture(null));
  }, [cmd?.facture_id]);

  // Changement de statut (et/ou note interne) : POST /commandes/{id}/statut
  async function changerStatut(statut, noteInterne = note) {
    setEnCours("statut");
    try {
      const { data } = await apiClient.post(`/commandes/${id}/statut`, { statut, note_interne: noteInterne.trim() });
      remplir(data);
      toast.succes(`Commande : ${STATUTS_COMMANDE[statut]?.libelle || statut}`);
      setConfirmerAnnulation(false);
    } catch (err) {
      toast.erreur(messageErreur(err, "Changement de statut impossible"));
    } finally {
      setEnCours("");
    }
  }

  // Création de la facture de la commande : POST /commandes/{id}/facture, puis ouverture
  async function genererFacture() {
    setEnCours("facture");
    try {
      const { data } = await apiClient.post(`/commandes/${id}/facture`);
      toast.succes("Facture brouillon créée : vérifiez-la puis validez-la");
      navigate(`/gestion/documents/${data.id}`);
    } catch (err) {
      toast.erreur(messageErreur(err, "Impossible de générer la facture"));
    } finally {
      setEnCours("");
    }
  }

  if (erreur) {
    return (
      <div className="card text-center">
        <p className="text-red-600">{erreur}</p>
        <Link to="/gestion/commandes" className="btn-outline btn-sm mt-4">← Retour aux commandes</Link>
      </div>
    );
  }
  if (!cmd) return <Chargement plein />;

  const indexEtape = ETAPES.indexOf(cmd.statut);
  const etapeSuivante = indexEtape >= 0 && indexEtape < ETAPES.length - 1 ? ETAPES[indexEtape + 1] : null;
  const annulee = cmd.statut === "ANNULEE";
  // On peut (re)générer une facture s'il n'y en a pas, ou si l'ancienne a été annulée
  const peutFacturer = !annulee && (!cmd.facture_id || facture?.statut === "ANNULE");
  const formulaireModifie = nouveauStatut !== cmd.statut || note.trim() !== (cmd.note_interne || "");

  return (
    <div>
      {/* En-tête : numéro, date, statut et actions principales */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/gestion/commandes" className="text-sm font-semibold text-primary">← Commandes en ligne</Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-2 text-2xl font-extrabold">
            Commande {cmd.numero} <Badge table={STATUTS_COMMANDE} statut={cmd.statut} />
          </h1>
          <p className="text-sm text-gray-500">Passée le {dateHeure(cmd.date)} · mise à jour le {dateHeure(cmd.date_maj)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {etapeSuivante && (
            <button type="button" className="btn-primary btn-sm" disabled={!!enCours} onClick={() => changerStatut(etapeSuivante)}>
              → Passer à « {STATUTS_COMMANDE[etapeSuivante].libelle} »
            </button>
          )}
          {peutFacturer && (
            <button type="button" className="btn-accent btn-sm" disabled={!!enCours} onClick={genererFacture}>
              {enCours === "facture" ? "Création…" : "🧾 Générer la facture"}
            </button>
          )}
          {cmd.facture_id && facture && facture.statut !== "ANNULE" && (
            <Link to={`/gestion/documents/${cmd.facture_id}`} className="btn-outline btn-sm">🧾 Voir la facture {facture.numero || "(brouillon)"}</Link>
          )}
        </div>
      </div>

      {/* Frise des étapes */}
      {!annulee ? (
        <ol className="mb-6 grid grid-cols-5 gap-1 text-center text-[11px] sm:text-xs">
          {ETAPES.map((e, i) => (
            <li key={e} className="flex flex-col items-center gap-1">
              <span className={`h-2 w-full rounded-full ${i <= indexEtape ? "bg-primary" : "bg-gray-200"}`} />
              <span className={i <= indexEtape ? "font-semibold text-primary" : "text-gray-500"}>{STATUTS_COMMANDE[e].libelle}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mb-6 rounded-xl bg-red-50 p-3 text-sm font-semibold text-red-700">Cette commande a été annulée.</p>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {/* Articles commandés */}
          <section className="card">
            <h2 className="mb-3 text-lg font-bold">Articles</h2>
            <div className="divide-y divide-gray-100">
              {cmd.lignes.map((l, i) => (
                <div key={i} className="flex items-start justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <p className="font-medium">{l.nom}</p>
                    <p className="text-xs text-gray-500">Réf. {l.reference} · {l.quantite} × {montant(l.prix_unitaire)}</p>
                  </div>
                  <span className="whitespace-nowrap font-semibold">{prix(l.montant, devise)}</span>
                </div>
              ))}
            </div>
            <div className="mt-3 flex justify-between border-t border-gray-200 pt-3 text-base">
              <span className="font-bold">Total (TTC)</span><span className="font-extrabold text-primary">{prix(cmd.total, devise)}</span>
            </div>
          </section>

          {/* Paiement */}
          <section className="card">
            <h2 className="mb-3 text-lg font-bold">Paiement</h2>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span>{cmd.paiement?.mode === "MOBILE_MONEY" ? "Mobile Money (en ligne)" : "À la livraison / au retrait"}</span>
              <Badge table={STATUTS_PAIEMENT_COMMANDE} statut={cmd.paiement?.statut} />
              {cmd.paiement?.montant_paye > 0 && <span className="text-gray-600">· {prix(cmd.paiement.montant_paye, devise)} reçus</span>}
            </div>
            {facture && (
              <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl bg-gray-50 p-3 text-sm">
                <span>Facture <Link to={`/gestion/documents/${facture.id}`} className="font-semibold text-primary">{facture.numero || "brouillon"}</Link></span>
                <Badge table={STATUTS_DOCUMENT} statut={facture.statut} />
                {facture.statut !== "ANNULE" && <BadgePaiement libelle={facture.statut_paiement} />}
              </div>
            )}
          </section>

          {/* Changement de statut et note interne */}
          <section className="card">
            <h2 className="mb-3 text-lg font-bold">Suivi de la commande</h2>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (nouveauStatut === "ANNULEE" && !annulee) setConfirmerAnnulation(true); else changerStatut(nouveauStatut); }}>
              <div>
                <label className="label" htmlFor="cmd-statut">Statut</label>
                <select id="cmd-statut" className="input" value={nouveauStatut} onChange={(e) => setNouveauStatut(e.target.value)}>
                  {Object.entries(STATUTS_COMMANDE).map(([k, s]) => <option key={k} value={k}>{s.libelle}</option>)}
                </select>
                {cmd.client?.email && nouveauStatut !== cmd.statut && (
                  <p className="mt-1 text-xs text-gray-500">Le client sera prévenu par e-mail ({cmd.client.email}) si la messagerie est activée.</p>
                )}
              </div>
              <div>
                <label className="label" htmlFor="cmd-note">Note interne <span className="font-normal text-gray-500">(visible seulement par l'équipe)</span></label>
                <textarea id="cmd-note" className="input" rows={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)}
                  placeholder="ex. Client rappelé, livraison prévue demain matin" />
              </div>
              <button className="btn-primary" disabled={!!enCours || !formulaireModifie}>{enCours === "statut" ? "Enregistrement…" : "Enregistrer"}</button>
            </form>
          </section>
        </div>

        <div className="space-y-6">
          {/* Client et moyens de le contacter */}
          <section className="card">
            <h2 className="mb-3 text-lg font-bold">Client</h2>
            <p className="font-semibold">{cmd.client?.nom}</p>
            <p className="text-sm text-gray-600">{cmd.client?.telephone}</p>
            {cmd.client?.email && <p className="text-sm text-gray-600">{cmd.client.email}</p>}
            <div className="mt-3"><BoutonsContact telephone={cmd.client?.telephone} email={cmd.client?.email} /></div>
            {cmd.client_id && <Link to={`/gestion/clients/${cmd.client_id}`} className="mt-3 inline-block text-sm font-semibold text-primary">Fiche client →</Link>}
          </section>

          {/* Livraison ou retrait, message du client */}
          <section className="card">
            <h2 className="mb-3 text-lg font-bold">{cmd.mode_livraison === "LIVRAISON" ? "🚚 Livraison" : "🏬 Retrait en boutique"}</h2>
            {cmd.mode_livraison === "LIVRAISON"
              ? <p className="whitespace-pre-line text-sm">{cmd.adresse_livraison || "Adresse non précisée"}</p>
              : <p className="text-sm text-gray-600">Le client passe récupérer sa commande.</p>}
            {cmd.message_client && (
              <div className="mt-3 rounded-xl bg-amber-50 p-3 text-sm">
                <p className="text-xs font-semibold text-amber-800">Message du client</p>
                <p className="whitespace-pre-line">{cmd.message_client}</p>
              </div>
            )}
          </section>

          {/* Historique des changements de statut */}
          <section className="card">
            <h2 className="mb-3 text-lg font-bold">Historique</h2>
            <ol className="space-y-3 border-l-2 border-gray-200 pl-4">
              {[...(cmd.historique || [])].reverse().map((h, i) => (
                <li key={i} className="relative text-sm">
                  <span className="absolute -left-[22px] top-1 h-2.5 w-2.5 rounded-full bg-primary" />
                  <p className="font-semibold">{STATUTS_COMMANDE[h.statut]?.libelle || h.statut}</p>
                  <p className="text-xs text-gray-500">{dateHeure(h.date)}{h.par ? ` · ${h.par}` : ""}</p>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>

      <Confirmation ouvert={confirmerAnnulation} titre="Annuler la commande ?" danger libelleBouton="Annuler la commande" enCours={!!enCours}
        onConfirmer={() => changerStatut("ANNULEE")} onFermer={() => setConfirmerAnnulation(false)}>
        <p>La commande <b>{cmd.numero}</b> sera marquée comme annulée{cmd.client?.email ? " et le client en sera informé par e-mail" : ""}.</p>
        {cmd.facture_id && facture?.statut !== "ANNULE" && <p className="text-amber-700">Pensez aussi à annuler sa facture si nécessaire.</p>}
      </Confirmation>
    </div>
  );
}
