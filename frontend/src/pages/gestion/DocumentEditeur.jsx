import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { aujourdhui, date, dateHeure, prix } from "@/lib/format";
import { STATUTS_DOCUMENT } from "@/lib/statuts";
import Badge from "@/components/Badge";
import Chargement from "@/components/Chargement";
import ClientSelect from "@/components/ClientSelect";
import { useToast } from "@/components/Toast";
import { arrondi, calculerLignes, nombre } from "./_ventes/calculs";
import Confirmation from "./_ventes/Confirmation";
import ConversionProforma from "./_ventes/ConversionProforma";
import LignesDocument, { nouvelleCle } from "./_ventes/LignesDocument";
import Reglements from "./_ventes/Reglements";
import { libelleType } from "./_ventes/outils";

// Éditeur d'une facture ou d'une proforma (création et modification).
// Adresses : /gestion/documents/nouveau?type=FAC|PRO[&client=<id>]
//            /gestion/documents/<id>
// Les totaux sont calculés en direct dans le navigateur pour l'aperçu, mais
// le serveur recalcule tout à l'enregistrement : ce sont SES montants qui font foi.
export default function DocumentEditeur() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { boutique } = useAuth();
  const devise = boutique?.devise || "FCFA";
  const tauxDefaut = boutique?.taux_tva_defaut ?? 18;

  // Paramètres d'une création : type de document et client pré-choisi
  const typeParam = params.get("type") === "PRO" ? "PRO" : "FAC";
  const clientParam = params.get("client");

  // --- État de la page ---
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [doc, setDoc] = useState(null); // document tel qu'enregistré sur le serveur (null = nouveau)
  const [entete, setEntete] = useState(null); // client, dates, objet, notes, prix TTC
  const [lignes, setLignes] = useState([]); // lignes en cours de saisie
  const [modifie, setModifie] = useState(false); // vrai s'il y a des modifications non enregistrées
  const [enCours, setEnCours] = useState(""); // action en cours (bloque les boutons)
  const [confirmation, setConfirmation] = useState(null); // "valider" | "convertir" | "annuler" | "supprimer"

  // Recopie un document du serveur dans les champs de l'écran
  function remplir(data) {
    setDoc(data);
    setEntete({
      type_document: data.type_document,
      client: { id: data.client_id, ...data.client },
      date: data.date,
      date_echeance: data.date_echeance || "",
      objet: data.objet || "",
      notes: data.notes || "",
      prix_ttc: data.prix_ttc ?? true,
    });
    setLignes((data.lignes || []).map((l) => ({
      cle: nouvelleCle(), produit_id: l.produit_id, reference: l.reference, designation: l.designation,
      quantite: String(l.quantite), prix_unitaire: String(l.prix_unitaire),
      remise_pct: l.remise_pct ? String(l.remise_pct) : "", taux_tva: l.taux_tva === null || l.taux_tva === undefined ? "" : String(l.taux_tva),
      stockable: l.stockable,
    })));
    setModifie(false);
  }

  // Chargement : document existant, ou document vide (avec éventuellement le client de l'adresse)
  useEffect(() => {
    let annule = false;
    async function charger() {
      setChargement(true);
      setErreur("");
      try {
        if (id) {
          const { data } = await apiClient.get(`/documents/${id}`);
          if (!annule) remplir(data);
        } else {
          let client = null;
          if (clientParam) {
            try {
              client = (await apiClient.get(`/clients/${clientParam}`)).data;
            } catch {
              client = null; // client introuvable : on laisse le champ vide
            }
          }
          if (annule) return;
          setDoc(null);
          setEntete({
            type_document: typeParam, client, date: aujourdhui(), date_echeance: "", objet: "", notes: "",
            prix_ttc: boutique?.prix_ttc ?? true,
          });
          setLignes([]);
          setModifie(false);
        }
      } catch (err) {
        if (!annule) setErreur(messageErreur(err, "Document introuvable"));
      } finally {
        if (!annule) setChargement(false);
      }
    }
    charger();
    return () => { annule = true; };
    // boutique volontairement absente : seul le réglage prix_ttc est lu, au départ
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, typeParam, clientParam]);

  // Facture tout juste créée depuis une proforma (adresse ?valider=1) : on propose
  // directement « Valider la facture ». Le paramètre est retiré de l'adresse aussitôt,
  // pour que la fenêtre ne se rouvre pas à chaque rechargement.
  useEffect(() => {
    if (params.get("valider") !== "1" || !doc) return;
    if (doc.type_document === "FAC" && doc.statut === "BROUILLON") setConfirmation("valider");
    setParams((p) => { const n = new URLSearchParams(p); n.delete("valider"); return n; }, { replace: true });
  }, [doc, params, setParams]);

  // Un document validé, annulé (ou en cours de validation) ne se modifie plus
  const lectureSeule = !!doc && !doc.modifiable;

  // Aperçu des montants : recalcul à chaque frappe (même formule que le serveur).
  // En lecture seule, on affiche directement les montants enregistrés par le serveur.
  const calcul = useMemo(() => {
    if (lectureSeule) {
      return {
        lignes: doc.lignes.map((l, i) => ({ ...l, cle: `s${i}`, taux_effectif: l.taux_tva })),
        total_ht: doc.total_ht, total_tva: doc.total_tva, total_ttc: doc.total_ttc,
      };
    }
    return calculerLignes(lignes, tauxDefaut, entete?.prix_ttc ?? true);
  }, [lectureSeule, doc, lignes, tauxDefaut, entete?.prix_ttc]);

  // Modification d'un champ de l'en-tête
  function changer(champ, valeur) {
    setEntete((e) => ({ ...e, [champ]: valeur }));
    setModifie(true);
  }
  function changerLignes(nouvelles) {
    setLignes(nouvelles);
    setModifie(true);
  }

  // Données envoyées au serveur (voir DocumentSaisie dans backend/routes/documents.py)
  function construirePayload() {
    return {
      type_document: entete.type_document,
      client_id: entete.client?.id,
      date: entete.date,
      date_echeance: entete.date_echeance || null,
      objet: entete.objet.trim(),
      notes: entete.notes,
      prix_ttc: entete.prix_ttc,
      lignes: lignes.map((l) => ({
        produit_id: l.produit_id || null,
        designation: l.designation.trim(),
        quantite: Math.max(1, Math.trunc(nombre(l.quantite, 1))),
        prix_unitaire: Math.max(0, arrondi(nombre(l.prix_unitaire, 0))),
        remise_pct: Math.min(100, Math.max(0, nombre(l.remise_pct, 0))),
        taux_tva: l.taux_tva === "" ? null : nombre(l.taux_tva, tauxDefaut),
      })),
    };
  }

  // Contrôles avant envoi (le serveur vérifie aussi)
  function verifier() {
    if (!entete.client?.id) return "Choisissez un client";
    if (!entete.date) return "Indiquez la date du document";
    if (lignes.length === 0) return "Ajoutez au moins une ligne";
    if (lignes.some((l) => !l.produit_id && !l.designation.trim())) return "Chaque ligne libre doit avoir une désignation";
    if (lignes.some((l) => nombre(l.quantite, 0) < 1)) return "Chaque quantité doit être d'au moins 1";
    return "";
  }

  // Enregistrement : POST (création) ou PUT (modification). Renvoie le document enregistré.
  async function enregistrer({ silencieux = false } = {}) {
    const probleme = verifier();
    if (probleme) {
      toast.erreur(probleme);
      return null;
    }
    setEnCours("enregistrer");
    try {
      const payload = construirePayload();
      const { data } = doc
        ? await apiClient.put(`/documents/${doc.id}`, payload)
        : await apiClient.post("/documents", payload);
      if (!silencieux) toast.succes(doc ? "Modifications enregistrées" : `${libelleType(data.type_document)} créée`);
      if (!doc) {
        // Nouveau document : on passe sur son adresse définitive (il sera rechargé)
        navigate(`/gestion/documents/${data.id}`, { replace: true });
      } else {
        remplir(data);
      }
      return data;
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible : vérifiez les lignes"));
      return null;
    } finally {
      setEnCours("");
    }
  }

  // Exécute une action du cycle de vie (après confirmation)
  async function executer(action) {
    // Des modifications non enregistrées ? On les enregistre d'abord.
    if (modifie && action === "valider") {
      const ok = await enregistrer({ silencieux: true });
      if (!ok) return;
    }
    setEnCours(action);
    try {
      if (action === "valider") {
        const { data } = await apiClient.post(`/documents/${doc.id}/valider`);
        remplir(data);
        toast.succes(`Facture validée : n° ${data.numero}`);
      } else if (action === "annuler") {
        const { data } = await apiClient.post(`/documents/${doc.id}/annuler`);
        remplir(data);
        toast.succes("Document annulé");
      } else if (action === "supprimer") {
        await apiClient.delete(`/documents/${doc.id}`);
        toast.succes("Brouillon supprimé");
        navigate("/gestion/documents", { replace: true });
      }
      setConfirmation(null);
    } catch (err) {
      toast.erreur(messageErreur(err, "Action impossible"));
      setConfirmation(null);
    } finally {
      setEnCours("");
    }
  }

  if (chargement) return <Chargement plein />;
  if (erreur) {
    return (
      <div className="card text-center">
        <p className="text-red-600">{erreur}</p>
        <Link to="/gestion/documents" className="btn-outline btn-sm mt-4">← Retour à la liste</Link>
      </div>
    );
  }

  const type = entete.type_document;
  const titre = doc
    ? `${libelleType(type)} ${doc.numero || "(brouillon)"}`
    : type === "PRO" ? "Nouvelle proforma" : "Nouvelle facture";
  const brouillon = doc?.statut === "BROUILLON";

  return (
    <div className="pb-24">
      {/* En-tête : titre, statut et actions du cycle de vie */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/gestion/documents" className="text-sm font-semibold text-primary">← Factures & proformas</Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-2 text-2xl font-extrabold">
            {titre} {doc && <Badge table={STATUTS_DOCUMENT} statut={doc.statut} />}
          </h1>
          {doc && (
            <p className="text-sm text-gray-500">
              Créé le {dateHeure(doc.created_at)}{doc.cree_par ? ` par ${doc.cree_par}` : ""}
              {doc.date_validation ? ` · validé le ${dateHeure(doc.date_validation)}` : ""}
            </p>
          )}
        </div>
        {doc && (
          <div className="no-print flex flex-wrap gap-2">
            {type === "FAC" && brouillon && (
              <button type="button" className="btn-primary btn-sm" disabled={!!enCours} onClick={() => setConfirmation("valider")}>✓ Valider la facture</button>
            )}
            {/* Proforma en cours OU acceptée, pas encore convertie */}
            {type === "PRO" && doc.convertible && (
              <button type="button" className="btn-primary btn-sm" disabled={!!enCours} onClick={() => setConfirmation("convertir")}>→ Convertir en facture</button>
            )}
            <a href={`/gestion/documents/${doc.id}/imprimer`} target="_blank" rel="noreferrer" className="btn-outline btn-sm"
              onClick={(e) => { if (modifie) { e.preventDefault(); toast.info("Enregistrez d'abord vos modifications avant d'imprimer"); } }}>
              🖨 Imprimer / PDF
            </a>
            {["BROUILLON", "VALIDE"].includes(doc.statut) && (
              <button type="button" className="btn-outline btn-sm text-red-600" disabled={!!enCours} onClick={() => setConfirmation("annuler")}>Annuler</button>
            )}
            {type === "FAC" && brouillon && (
              <button type="button" className="btn-danger btn-sm" disabled={!!enCours} onClick={() => setConfirmation("supprimer")}>Supprimer</button>
            )}
          </div>
        )}
      </div>

      {/* Origines du document et liens associés */}
      {doc && (doc.proforma_origine || doc.commande_origine || doc.dossier_origine || doc.facture_generee_id) && (
        <div className="mb-4 flex flex-wrap gap-2 rounded-xl border border-blue-100 bg-blue-50 p-3 text-sm text-blue-900">
          {doc.proforma_origine && <span>Issue de la proforma <Link className="font-semibold underline" to={`/gestion/documents/${doc.proforma_origine.id}`}>{doc.proforma_origine.numero}</Link>.</span>}
          {doc.commande_origine && <span>Issue de la commande en ligne <Link className="font-semibold underline" to={`/gestion/commandes/${doc.commande_origine.id}`}>{doc.commande_origine.numero}</Link>.</span>}
          {doc.dossier_origine && <span>Issue du dossier SAV <Link className="font-semibold underline" to={`/gestion/maintenance/${doc.dossier_origine.id}`}>{doc.dossier_origine.numero}</Link>.</span>}
          {doc.facture_generee?.id && (
            <span>
              ✓ Proforma convertie en facture :{" "}
              <Link className="font-semibold underline" to={`/gestion/documents/${doc.facture_generee.id}`}>
                {doc.facture_generee.numero ? `facture ${doc.facture_generee.numero}` : "facture en brouillon (à valider)"}
              </Link>.
            </span>
          )}
        </div>
      )}

      {lectureSeule && (
        <p className="mb-4 rounded-xl bg-gray-100 p-3 text-sm text-gray-700">
          🔒 Ce document n'est plus modifiable{doc.statut === "VALIDE" && type === "FAC" ? " (facture validée : pour la corriger, annulez-la puis refaites-en une)" : ""}.
        </p>
      )}

      <div className="space-y-6">
        {/* Bloc « Informations » : client, dates, objet, mode de saisie des prix */}
        <section className="card">
          <h2 className="mb-4 text-lg font-bold">Informations</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="md:col-span-2">
              <label className="label">Client *</label>
              {lectureSeule ? (
                <div className="rounded-xl border border-gray-200 px-3 py-2.5">
                  <p className="font-semibold">{doc.client?.nom}</p>
                  <p className="text-xs text-gray-500">{doc.client?.telephone}{doc.client?.email ? ` · ${doc.client.email}` : ""}</p>
                </div>
              ) : (
                <ClientSelect value={entete.client} onChange={(c) => changer("client", c)} />
              )}
              {entete.client?.id && <Link to={`/gestion/clients/${entete.client.id}`} className="mt-1 inline-block text-xs font-semibold text-primary">Voir la fiche client →</Link>}
            </div>
            <div>
              <label className="label" htmlFor="doc-date">Date *</label>
              <input id="doc-date" className="input" type="date" required disabled={lectureSeule} value={entete.date} onChange={(e) => changer("date", e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="doc-echeance">{type === "PRO" ? "Valable jusqu'au" : "Échéance"}</label>
              <input id="doc-echeance" className="input" type="date" disabled={lectureSeule} value={entete.date_echeance} onChange={(e) => changer("date_echeance", e.target.value)} />
              {type === "PRO" && !lectureSeule && !entete.date_echeance && (
                <p className="mt-1 text-xs text-gray-500">Vide = {boutique?.validite_proforma_jours ?? 15} jours (réglage de la boutique).</p>
              )}
            </div>
            <div className="md:col-span-2">
              <label className="label" htmlFor="doc-objet">Objet</label>
              <input id="doc-objet" className="input" maxLength={200} disabled={lectureSeule} placeholder="ex. Équipement du bureau" value={entete.objet} onChange={(e) => changer("objet", e.target.value)} />
            </div>
            {/* Prix saisis TTC ou HT : change la façon dont la TVA est calculée */}
            <label className={`flex items-start gap-3 self-end rounded-xl border border-gray-200 p-3 md:col-span-2 ${lectureSeule ? "opacity-70" : "cursor-pointer"}`}>
              <input type="checkbox" className="mt-1 h-4 w-4" disabled={lectureSeule} checked={!!entete.prix_ttc} onChange={(e) => changer("prix_ttc", e.target.checked)} />
              <span className="text-sm">
                <b>Prix saisis TTC</b>
                <span className="block text-xs text-gray-500">{entete.prix_ttc ? "Les prix unitaires incluent la TVA (elle en est extraite)." : "Les prix unitaires sont HT : la TVA s'ajoute."}</span>
              </span>
            </label>
          </div>
        </section>

        {/* Bloc « Lignes », puis notes et totaux */}
        <section className="card">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-lg font-bold">Lignes <span className="text-sm font-normal text-gray-500">({calcul.lignes.length})</span></h2>
            {!lectureSeule && <span className="text-xs text-gray-500">TVA vide = taux par défaut ({tauxDefaut} %)</span>}
          </div>
          <LignesDocument lignesCalculees={calcul.lignes} lectureSeule={lectureSeule} prixTtc={!!entete.prix_ttc}
            tauxDefaut={tauxDefaut} estFacture={type === "FAC"} onChange={changerLignes} />

          <div className="mt-4 grid gap-6 border-t border-gray-100 pt-4 md:grid-cols-[minmax(0,1fr)_20rem]">
            {/* Notes imprimées sur le document */}
            <div>
              <label className="label" htmlFor="doc-notes">Notes (imprimées sur le document)</label>
              {lectureSeule
                ? <p className="whitespace-pre-line text-sm text-gray-700">{entete.notes || "—"}</p>
                : <textarea id="doc-notes" className="input" rows={3} maxLength={2000} placeholder="ex. Garantie 12 mois, livraison sous 48 h…" value={entete.notes} onChange={(e) => changer("notes", e.target.value)} />}
            </div>
            {/* Totaux (aperçu en direct pendant la saisie) */}
            <dl className="space-y-1 text-sm">
              <div className="flex justify-between"><dt className="text-gray-600">Total HT</dt><dd className="font-semibold">{prix(calcul.total_ht, devise)}</dd></div>
              <div className="flex justify-between"><dt className="text-gray-600">TVA</dt><dd className="font-semibold">{prix(calcul.total_tva, devise)}</dd></div>
              <div className="flex justify-between border-t border-gray-200 pt-2 text-base"><dt className="font-bold">Total TTC</dt><dd className="font-extrabold text-primary">{prix(calcul.total_ttc, devise)}</dd></div>
              {!lectureSeule && <p className="pt-1 text-right text-xs text-gray-400">Aperçu : les montants définitifs sont calculés par le serveur à l'enregistrement.</p>}
              {lectureSeule && doc.total_en_lettres && <p className="pt-1 text-right text-xs italic text-gray-500">{doc.total_en_lettres}</p>}
            </dl>
          </div>
        </section>
      </div>

      {/* Bloc « Règlements » : factures enregistrées et non annulées */}
      {doc && type === "FAC" && doc.statut !== "ANNULE" && (
        <div className="mt-6">
          <Reglements doc={doc} devise={devise} onMaj={(d) => setDoc(d)} />
          {brouillon && <p className="mt-2 text-xs text-gray-500">Un règlement peut être enregistré sur un brouillon (acompte) ; la facture reste à valider.</p>}
        </div>
      )}

      {/* Barre d'enregistrement fixée en bas de l'écran (saisie en cours) */}
      {!lectureSeule && (
        <div className="no-print fixed inset-x-0 bottom-0 z-20 border-t border-gray-200 bg-white/95 px-4 py-3 backdrop-blur lg:left-64">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-3">
            <div className="text-sm">
              <span className="text-gray-500">Total TTC </span><b className="text-lg">{prix(calcul.total_ttc, devise)}</b>
              {modifie && <span className="ml-2 hidden text-xs text-amber-700 sm:inline">● modifications non enregistrées</span>}
            </div>
            <button type="button" className="btn-primary" disabled={!!enCours || (doc && !modifie)} onClick={() => enregistrer()}>
              {enCours === "enregistrer" ? "Enregistrement…" : doc ? "Enregistrer" : `Créer la ${type === "PRO" ? "proforma" : "facture"}`}
            </button>
          </div>
        </div>
      )}

      {/* Fenêtres de confirmation des actions importantes */}
      <Confirmation ouvert={confirmation === "valider"} titre="Valider la facture ?" libelleBouton="Valider la facture"
        enCours={!!enCours} onConfirmer={() => executer("valider")} onFermer={() => setConfirmation(null)}>
        <p>La validation est <b>définitive</b> :</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>la facture reçoit son <b>numéro définitif</b> (FAC-…) ;</li>
          <li>les articles sont <b>sortis du stock</b> (refus si un article manque) ;</li>
          <li>elle ne pourra plus être modifiée, seulement annulée.</li>
        </ul>
        {modifie && <p className="text-amber-700">Vos modifications en cours seront d'abord enregistrées.</p>}
        <p>Montant : <b>{prix(calcul.total_ttc, devise)} TTC</b></p>
      </Confirmation>
      {/* Conversion de la proforma : « Créer la facture » ou « Convertir et valider » */}
      {confirmation === "convertir" && doc && (
        <ConversionProforma proforma={doc} devise={devise} onFermer={() => setConfirmation(null)}
          avantConversion={async () => (modifie ? !!(await enregistrer({ silencieux: true })) : true)} />
      )}
      <Confirmation ouvert={confirmation === "annuler"} titre={`Annuler ce document ?`} danger libelleBouton="Annuler le document"
        enCours={!!enCours} onConfirmer={() => executer("annuler")} onFermer={() => setConfirmation(null)}>
        {doc?.statut === "VALIDE" && type === "FAC"
          ? <p>La facture <b>{doc.numero}</b> sera annulée et les articles vendus <b>remis en stock</b>. Son numéro reste attribué (pas de trou dans la numérotation).</p>
          : <p>Le document sera marqué comme annulé. Cette opération est définitive.</p>}
      </Confirmation>
      <Confirmation ouvert={confirmation === "supprimer"} titre="Supprimer ce brouillon ?" danger libelleBouton="Supprimer définitivement"
        enCours={!!enCours} onConfirmer={() => executer("supprimer")} onFermer={() => setConfirmation(null)}>
        <p>Le brouillon de facture{doc?.client?.nom ? ` pour ${doc.client.nom}` : ""} du {date(doc?.date)} sera définitivement supprimé.</p>
      </Confirmation>
    </div>
  );
}
