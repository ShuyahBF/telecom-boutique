import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { messageErreur } from "@/lib/api";
import { apiEspace, definirJeton, qrMemorise } from "@/lib/espaceClient";
import { date, prix } from "@/lib/format";
import ChampMotDePasse from "@/components/ChampMotDePasse";
import EtatServeur from "@/components/EtatServeur";
import FeuilleDocument from "@/components/FeuilleDocument";
import { LogoAdlyn } from "@/components/Marque";
import Patientez from "@/components/Patientez";
import VersionApp from "@/components/VersionApp";

// =============================================================================
// « MON ESPACE » : espace client public d'une boutique (lecture seule)
// =============================================================================
// Adresses : /mon-espace/<slug>       (depuis la vitrine de la boutique)
//            /q/<jeton>/mon-espace    (depuis le QR code d'une facture / proforma)
// Connexion en deux étapes :
//   1. le client saisit SON numéro de téléphone (son « mot de passe ») ;
//   2. il reçoit un code à 6 chiffres par WhatsApp (ou SMS), valable 10 minutes.
// Ensuite : achats et factures (impression / PDF), devis et proformas, règlements et
// reste à payer, suivi SAV. Session de 30 minutes, prolongée à chaque action.
// =============================================================================

const ONGLETS = [
  ["factures", "Achats & factures"],
  ["proformas", "Devis & proformas"],
  ["reglements", "Règlements"],
  ["sav", "Suivi SAV"],
];

const LIBELLES_STATUT = { VALIDE: "Validée", ANNULE: "Annulée", BROUILLON: "En cours" };

export default function EspaceClient() {
  const { slug, jeton: jetonAdresse } = useParams();
  // Jeton du QR code : celui de l'adresse, sinon celui retenu quand le QR code a été scanné
  const jetonQr = jetonAdresse || (slug ? qrMemorise(slug) : "");

  const [boutique, setBoutique] = useState(null);
  const [introuvable, setIntrouvable] = useState("");
  const [session, setSession] = useState(null); // { client, boutique, resume } une fois connecté
  const [verification, setVerification] = useState(true); // reprise éventuelle d'une session (cookie)
  const [message, setMessage] = useState(""); // ex. « Session expirée »

  // 1) Boutique concernée (par QR code ou par adresse)
  useEffect(() => {
    const url = jetonAdresse ? `/espace-client/qr/${jetonAdresse}` : `/espace-client/b/${slug}`;
    apiEspace.get(url)
      .then(({ data }) => { setBoutique(data.boutique); document.title = `Mon espace — ${data.boutique.nom}`; })
      .catch((err) => setIntrouvable(messageErreur(err, "Boutique introuvable")));
  }, [slug, jetonAdresse]);

  // 2) Session déjà ouverte (cookie HttpOnly) pour CETTE boutique ? On la reprend.
  const chargerSession = useCallback(async () => {
    try {
      const { data } = await apiEspace.get("/espace-client/moi");
      return data;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    if (!boutique) return;
    chargerSession().then((data) => {
      if (data && data.boutique?.nom === boutique.nom && data.boutique?.code_marchand === boutique.code_marchand) setSession(data);
      setVerification(false);
    });
  }, [boutique, chargerSession]);

  // Session perdue (30 minutes sans action, déconnexion) : retour à la connexion
  const sessionPerdue = useCallback((texte) => {
    definirJeton("");
    setSession(null);
    setMessage(texte || "Session expirée : reconnectez-vous.");
  }, []);

  if (introuvable) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-gray-50 p-6 text-center">
        <LogoAdlyn className="h-10" />
        <h1 className="text-xl font-bold">Espace indisponible</h1>
        <p className="text-gray-600">{introuvable}</p>
        <Link to="/" className="btn-primary">Voir les boutiques</Link>
      </div>
    );
  }
  if (!boutique || verification) return <Patientez actif />;

  return (
    <div style={{ "--couleur-boutique": boutique.couleur || "#1e90ff" }} className="min-h-screen bg-papier">
      {session
        ? <Espace boutique={boutique} session={session} setSession={setSession} sessionPerdue={sessionPerdue} retour={retourBoutique(boutique, jetonAdresse)} />
        : <ConnexionClient boutique={boutique} jetonQr={jetonQr} slug={slug} message={message}
            onConnecte={async (jetonSession) => {
              definirJeton(jetonSession);
              setMessage("");
              const data = await chargerSession();
              if (data) setSession(data);
              else setMessage("Connexion impossible : réessayez.");
            }}
            retour={retourBoutique(boutique, jetonAdresse)} />}
    </div>
  );
}

// Lien « retour » : vitrine si elle est publique, sinon page minimale du QR code
function retourBoutique(boutique, jetonAdresse) {
  if (boutique.page_publique && boutique.slug) return `/b/${boutique.slug}`;
  return jetonAdresse ? `/q/${jetonAdresse}` : "/";
}

// État du serveur (actif, lent, injoignable) : composant partagé
// components/EtatServeur.jsx (aussi affiché sur la page de connexion du personnel).

// -----------------------------------------------------------------------------
// Connexion : numéro de téléphone puis code reçu par WhatsApp
// -----------------------------------------------------------------------------
function ConnexionClient({ boutique, jetonQr, slug, message, onConnecte, retour }) {
  const [etape, setEtape] = useState("numero"); // "numero" | "code"
  const [telephone, setTelephone] = useState("");
  const [code, setCode] = useState("");
  const [demande, setDemande] = useState(null); // { demande_id, canal, destinataire, expire_dans }
  const [attente, setAttente] = useState(false);
  const [erreur, setErreur] = useState("");

  // Étape 1 : demande du code (le serveur vérifie le numéro)
  async function demanderCode(e) {
    e?.preventDefault();
    setErreur("");
    setAttente(true);
    try {
      const corps = jetonQr ? { jeton: jetonQr, telephone } : { slug, telephone };
      const { data } = await apiEspace.post("/espace-client/demander-code", corps);
      setDemande(data);
      setCode("");
      setEtape("code");
    } catch (err) {
      setErreur(messageErreur(err, "Envoi du code impossible"));
    } finally {
      setAttente(false);
    }
  }

  // Étape 2 : vérification du code, ouverture de la session
  async function verifierCode(e) {
    e.preventDefault();
    setErreur("");
    setAttente(true);
    try {
      const { data } = await apiEspace.post("/espace-client/verifier-code", { demande_id: demande.demande_id, code: code.trim() });
      await onConnecte(data.jeton);
    } catch (err) {
      setErreur(messageErreur(err, "Code refusé"));
    } finally {
      setAttente(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-4">
      <Patientez actif={attente} />
      {/* Carte de connexion centrée, avec le logo de la boutique (sinon celui d'adLyn) */}
      <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
        <div className="text-center">
          <img src={boutique.logo_url || "/marque/logo-adlyn.png"} alt="" className="mx-auto h-16 w-16 object-contain" draggable="false" />
          <h1 className="mt-2 font-display text-xl font-bold">{boutique.nom}</h1>
          <p className="text-sm font-semibold text-gray-500">Mon espace client</p>
        </div>

        {message && <p className="mt-4 rounded-lg bg-amber-50 p-2 text-sm text-amber-800">{message}</p>}
        {erreur && <p className="mt-4 rounded-lg bg-red-50 p-2 text-sm text-red-700" role="alert">{erreur}</p>}

        {etape === "numero" ? (
          <form onSubmit={demanderCode} className="mt-5 space-y-4">
            <div>
              <label htmlFor="tel-client" className="label">Votre numéro de téléphone</label>
              {/* Le numéro sert de « mot de passe » : masqué, avec l'œil pour l'afficher */}
              <ChampMotDePasse id="tel-client" inputMode="tel" autoComplete="tel" required minLength={8} maxLength={30}
                placeholder="Ex. 70 11 22 33" value={telephone} onChange={(e) => setTelephone(e.target.value)} />
              <p className="mt-1 text-xs text-gray-500">Le numéro donné à la boutique lors de vos achats.</p>
            </div>
            <button type="submit" className="btn-primary w-full" disabled={attente || telephone.trim().length < 8}>
              Recevoir mon code par WhatsApp
            </button>
          </form>
        ) : (
          <form onSubmit={verifierCode} className="mt-5 space-y-4">
            <p className="text-sm text-gray-700">
              Code envoyé par <b>{demande?.canal}</b> au <b>{demande?.destinataire}</b>. Il est valable {Math.round((demande?.expire_dans || 600) / 60)} minutes.
            </p>
            <div>
              <label htmlFor="code-client" className="label">Code reçu (6 chiffres)</label>
              <ChampMotDePasse id="code-client" inputMode="numeric" autoComplete="one-time-code" required maxLength={6}
                pattern="\d{6}" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
            </div>
            <button type="submit" className="btn-primary w-full" disabled={attente || code.length !== 6}>Accéder à mon espace</button>
            <div className="flex justify-between text-sm">
              <button type="button" className="font-semibold text-primary" onClick={() => { setEtape("numero"); setErreur(""); }}>← Changer de numéro</button>
              <button type="button" className="font-semibold text-primary" disabled={attente} onClick={demanderCode}>Renvoyer le code</button>
            </div>
          </form>
        )}

        <div className="mt-6 space-y-2 border-t border-gray-100 pt-4 text-center">
          <EtatServeur />
          <VersionApp className="text-gray-400" />
          <Link to={retour} className="block text-xs font-semibold text-primary">← Retour à la boutique</Link>
        </div>
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------------
// Espace connecté (lecture seule)
// -----------------------------------------------------------------------------
function Espace({ boutique, session, setSession, sessionPerdue, retour }) {
  const [onglet, setOnglet] = useState("factures");
  const [documents, setDocuments] = useState(null);
  const [reglements, setReglements] = useState(null);
  const [sav, setSav] = useState(null);
  const [selection, setSelection] = useState(""); // ligne sélectionnée (fond orange)
  const [ouvert, setOuvert] = useState(null); // document affiché pour impression : { document, boutique }
  const [attente, setAttente] = useState(false);
  const devise = boutique.devise || "FCFA";

  // Appel commun : session expirée (401) -> retour à la connexion
  const charger = useCallback(async (url) => {
    try {
      return (await apiEspace.get(url)).data;
    } catch (err) {
      if (err?.response?.status === 401) sessionPerdue(messageErreur(err, "Session expirée : reconnectez-vous."));
      throw err;
    }
  }, [sessionPerdue]);

  // Chargement des données de l'onglet choisi (une seule fois par onglet)
  useEffect(() => {
    let annule = false;
    async function lire() {
      setAttente(true);
      try {
        if ((onglet === "factures" || onglet === "proformas") && !documents) {
          const data = await charger("/espace-client/documents");
          if (!annule) setDocuments(data);
        } else if (onglet === "reglements" && !reglements) {
          const data = await charger("/espace-client/reglements");
          if (!annule) setReglements(data);
        } else if (onglet === "sav" && !sav) {
          const data = await charger("/espace-client/sav");
          if (!annule) setSav(data);
        }
      } catch { /* message déjà géré */ } finally {
        if (!annule) setAttente(false);
      }
    }
    lire();
    return () => { annule = true; };
  }, [onglet, documents, reglements, sav, charger]);

  // Ouverture d'un document complet (affichage A4, impression / PDF)
  async function ouvrir(id) {
    setSelection(id);
    setAttente(true);
    try {
      setOuvert(await charger(`/espace-client/documents/${id}`));
      window.scrollTo(0, 0);
    } catch { /* géré */ } finally {
      setAttente(false);
    }
  }

  // Titre de l'onglet = nom du fichier proposé lors de l'enregistrement en PDF
  useEffect(() => {
    const d = ouvert?.document;
    document.title = d ? `${d.type_document === "PRO" ? "Proforma" : "Facture"} ${d.numero || ""} - ${boutique.nom}`
      : `Mon espace — ${boutique.nom}`;
  }, [ouvert, boutique.nom]);

  async function deconnecter() {
    setAttente(true);
    try { await apiEspace.post("/espace-client/deconnexion"); } catch { /* session déjà fermée */ }
    setAttente(false);
    definirJeton("");
    setSession(null);
  }

  // Vue « document » : feuille A4 + barre d'outils
  if (ouvert) {
    return (
      <FeuilleDocument doc={ouvert.document} boutique={ouvert.boutique} pispi={ouvert.pispi}>
        <button type="button" className="btn-outline btn-sm" onClick={() => setOuvert(null)}>← Retour à mon espace</button>
        <button type="button" className="btn-primary" onClick={() => window.print()}>🖨 Imprimer / Enregistrer en PDF</button>
      </FeuilleDocument>
    );
  }

  const r = session.resume || {};
  const factures = (documents || []).filter((d) => d.type_document === "FAC");
  const proformas = (documents || []).filter((d) => d.type_document === "PRO");

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <Patientez actif={attente} />
      {/* En-tête : boutique, client, déconnexion */}
      <header className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl bg-white p-4 shadow">
        <img src={boutique.logo_url || "/marque/logo-adlyn.png"} alt="" className="h-12 w-12 object-contain" draggable="false" />
        <div className="min-w-0 flex-1">
          <p className="font-display text-lg font-bold">{boutique.nom}</p>
          <p className="text-sm text-gray-600">Bonjour <b>{session.client?.nom}</b> — votre espace client</p>
        </div>
        <Link to={retour} className="btn-outline btn-sm">Boutique</Link>
        <button type="button" className="btn-outline btn-sm" onClick={deconnecter}>Se déconnecter</button>
      </header>

      {/* Résumé : facturé, réglé, reste à payer */}
      <section className="mb-6 grid gap-3 sm:grid-cols-3">
        <Tuile titre="Total facturé" valeur={prix(r.total_facture, devise)} detail={`${r.nb_factures || 0} facture(s)`} />
        <Tuile titre="Déjà réglé" valeur={prix(r.total_regle, devise)} />
        <Tuile titre="Reste à payer" valeur={prix(r.reste_a_payer, devise)} fort={r.reste_a_payer > 0} />
      </section>

      {/* Onglets */}
      <div className="mb-4 flex flex-wrap gap-1 rounded-xl border border-gray-200 bg-white p-1">
        {ONGLETS.map(([cle, libelle]) => (
          <button key={cle} type="button" onClick={() => { setOnglet(cle); setSelection(""); }}
            className={`flex-1 rounded-lg px-3 py-1.5 text-sm font-semibold ${onglet === cle ? "bg-primary text-white" : "text-gray-600 hover:bg-gray-100"}`}>
            {libelle}
          </button>
        ))}
      </div>

      <div className="card overflow-x-auto p-0">
        {onglet === "factures" && (
          <TableauDocuments liste={factures} devise={devise} selection={selection} onOuvrir={ouvrir} factures vide="Aucune facture pour le moment." />
        )}
        {onglet === "proformas" && (
          <TableauDocuments liste={proformas} devise={devise} selection={selection} onOuvrir={ouvrir} vide="Aucun devis ni proforma." />
        )}
        {onglet === "reglements" && reglements && (
          reglements.length === 0 ? <p className="p-6 text-center text-gray-500">Aucun règlement enregistré.</p> : (
            <table className="table">
              <thead><tr><th>Date</th><th>Facture</th><th>Mode</th><th className="text-right">Montant</th></tr></thead>
              <tbody>
                {reglements.map((x, i) => (
                  <tr key={i} aria-selected={selection === `r${i}`} className="cursor-pointer" onClick={() => setSelection(`r${i}`)}>
                    <td>{date(x.date)}</td><td>{x.numero}</td><td>{x.mode}</td>
                    <td className="text-right font-semibold">{prix(x.montant, devise)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
        {onglet === "sav" && sav && <TableauSav sav={sav} selection={selection} setSelection={setSelection} devise={devise} />}
      </div>

      <footer className="mt-8 flex flex-col items-center gap-1 text-gray-400">
        <p className="text-xs">Espace en lecture seule. Session fermée après 30 minutes sans action.</p>
        <VersionApp />
      </footer>
    </div>
  );
}

function Tuile({ titre, valeur, detail, fort = false }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow">
      <p className="text-xs font-semibold uppercase text-gray-500">{titre}</p>
      <p className={`mt-1 text-xl font-extrabold ${fort ? "text-red-600" : ""}`}>{valeur}</p>
      {detail && <p className="text-xs text-gray-500">{detail}</p>}
    </div>
  );
}

// Tableau des factures ou des proformas (clic = sélection + ouverture du document)
function TableauDocuments({ liste, devise, selection, onOuvrir, factures = false, vide }) {
  if (liste.length === 0) return <p className="p-6 text-center text-gray-500">{vide}</p>;
  return (
    <table className="table">
      <thead>
        <tr>
          <th>N°</th><th>Date</th><th>Objet</th><th className="text-right">Total TTC</th>
          {factures ? <><th className="text-right">Reste à payer</th><th>Paiement</th></> : <th>État</th>}
          <th />
        </tr>
      </thead>
      <tbody>
        {liste.map((d) => (
          <tr key={d.id} aria-selected={selection === d.id} className="cursor-pointer" onClick={() => onOuvrir(d.id)}>
            <td className="whitespace-nowrap font-semibold">{d.numero || "—"}</td>
            <td className="whitespace-nowrap">{date(d.date)}</td>
            <td>{d.objet || "—"}</td>
            <td className="whitespace-nowrap text-right font-semibold">{prix(d.total_ttc, devise)}</td>
            {factures ? (
              <>
                <td className="whitespace-nowrap text-right">{d.statut === "ANNULE" ? "—" : prix(d.reste_a_payer, devise)}</td>
                <td>{d.statut === "ANNULE" ? "Annulée" : d.statut_paiement}</td>
              </>
            ) : (
              <td>{d.convertie ? "Acceptée (facturée)" : d.statut === "VALIDE" ? "Acceptée" : LIBELLES_STATUT[d.statut] || d.statut}</td>
            )}
            <td className="whitespace-nowrap text-right"><span className="text-sm font-semibold text-primary">Voir / imprimer</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Suivi SAV : dossiers de réparation et maintenance des équipements
function TableauSav({ sav, selection, setSelection, devise }) {
  const lignes = [
    ...(sav.dossiers || []).map((d) => ({ cle: `d${d.id}`, numero: d.numero, objet: [d.marque, d.modele].filter(Boolean).join(" "),
      depot: d.date_depot, etat: d.statut_libelle, detail: d.devis_montant ? `Devis : ${prix(d.devis_montant, devise)}` : (d.diagnostic || "") })),
    ...(sav.maintenance || []).map((f) => ({ cle: `m${f.id}`, numero: f.numero, objet: [f.type_materiel, f.marque_modele].filter(Boolean).join(" "),
      depot: f.date_reception, etat: f.statut_libelle, detail: f.diagnostic || "" })),
  ];
  if (lignes.length === 0) return <p className="p-6 text-center text-gray-500">Aucun appareil en réparation.</p>;
  return (
    <table className="table">
      <thead><tr><th>N°</th><th>Appareil</th><th>Déposé le</th><th>État</th><th>Détail</th></tr></thead>
      <tbody>
        {lignes.map((l) => (
          <tr key={l.cle} aria-selected={selection === l.cle} className="cursor-pointer" onClick={() => setSelection(l.cle)}>
            <td className="whitespace-nowrap font-semibold">{l.numero}</td>
            <td>{l.objet}</td>
            <td className="whitespace-nowrap">{date(l.depot)}</td>
            <td>{l.etat}</td>
            <td className="text-sm text-gray-600">{l.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
