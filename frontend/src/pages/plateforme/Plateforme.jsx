import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, montant } from "@/lib/format";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import QrCode from "@/components/QrCode";
import { useToast } from "@/components/Toast";
import { BadgeKyc, Champ, EnTetePlateforme } from "./_plateforme/composants";
import CreationBoutique from "./_plateforme/CreationBoutique";
import DossierBoutique from "./_plateforme/DossierBoutique";
import JournalWebhook, { LIBELLES_ENVOI } from "./_plateforme/JournalWebhook";
import Restauration from "./_plateforme/Restauration";
import { horodatage, messageErreurFichier, STATUTS_KYC, telechargerFichier } from "./_plateforme/outils";

// Page d'administration de la PLATEFORME (super-administrateur) :
// statistiques globales et gestion de toutes les boutiques (création,
// dossier KYC, sauvegarde / restauration, mise en avant, suspension…).
export default function Plateforme() {
  const { choisirBoutique } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();

  // --- État de la page ---
  const [stats, setStats] = useState(null);
  const [boutiques, setBoutiques] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [recherche, setRecherche] = useState("");
  const [filtreKyc, setFiltreKyc] = useState(""); // "" = tous les statuts KYC
  const [creation, setCreation] = useState(false); // fenêtre de création ouverte ?
  const [edition, setEdition] = useState(null); // boutique en cours de modification (nom, code, ordre)
  const [qr, setQr] = useState(null); // boutique dont on affiche le QR code
  const [dossierId, setDossierId] = useState(null); // boutique dont le « Dossier » est ouvert
  const [restauration, setRestauration] = useState(null); // boutique à restaurer
  const [telechargement, setTelechargement] = useState(null); // id de la boutique en cours de sauvegarde
  const [aValiderSeulement, setAValiderSeulement] = useState(false); // filtre « créées par le webhook, à valider »
  const [journalOuvert, setJournalOuvert] = useState(false); // fenêtre « Journal du webhook »

  // Chargement des statistiques et de la liste des boutiques
  const charger = useCallback(() => {
    apiClient.get("/plateforme/statistiques").then(({ data }) => setStats(data)).catch(() => {});
    apiClient.get("/plateforme/boutiques")
      .then(({ data }) => setBoutiques(data))
      .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger les boutiques")))
      .finally(() => setChargement(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  // Remplace une boutique dans la liste (après une modification)
  function remplacer(b) {
    setBoutiques((liste) => liste.map((x) => (x.id === b.id ? { ...x, ...b } : x)));
  }

  // Modification partielle d'une boutique (PATCH) : suspension, mise en avant, nom…
  async function modifier(b, changements, message) {
    try {
      const { data } = await apiClient.patch(`/plateforme/boutiques/${b.id}`, changements);
      remplacer(data);
      toast.succes(message);
      return true;
    } catch (err) {
      toast.erreur(messageErreur(err, "Modification impossible"));
      return false;
    }
  }

  // Enregistrement de la fenêtre « Modifier » (nom, code marchand, ordre)
  async function enregistrerEdition(e) {
    e.preventDefault();
    const ok = await modifier(edition, { nom: edition.nom, code_marchand: edition.code_marchand, ordre: Number(edition.ordre) || 0 }, "Boutique modifiée");
    if (ok) setEdition(null);
  }

  // Validation d'une boutique créée par le webhook : elle devient visible du public
  async function valider(b) {
    if (!window.confirm(`Valider « ${b.nom} » ? Elle apparaîtra sur le portail public.`)) return;
    try {
      remplacer((await apiClient.post(`/plateforme/boutiques/${b.id}/valider`)).data);
      toast.succes("Boutique validée : elle est maintenant visible du public");
    } catch (err) {
      toast.erreur(messageErreur(err, "Validation impossible"));
    }
  }

  // Nouveau mot de passe provisoire envoyé au DG (e-mail + SMS)
  async function renvoyerIdentifiants(b) {
    if (!window.confirm(`Envoyer un NOUVEAU mot de passe provisoire au DG de « ${b.nom} » ? L'actuel ne fonctionnera plus.`)) return;
    try {
      const { data } = await apiClient.post(`/plateforme/boutiques/${b.id}/renvoyer-identifiants`);
      remplacer({ id: b.id, identifiants_envoi: data });
      const ok = data.email === "ENVOYE" || data.sms === "ENVOYE";
      toast[ok ? "succes" : "erreur"](`E-mail : ${LIBELLES_ENVOI[data.email]} · SMS : ${LIBELLES_ENVOI[data.sms]}`);
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi impossible"));
    }
  }

  // Ouvrir le back-office d'une boutique en tant qu'administrateur
  async function ouvrirBackOffice(b) {
    await choisirBoutique(b.id);
    navigate("/gestion");
  }

  // Télécharger une sauvegarde chiffrée de la boutique (fichier .tlb.gz.enc)
  async function telechargerSauvegarde(b) {
    setTelechargement(b.id);
    try {
      const nom = await telechargerFichier(`/plateforme/boutiques/${b.id}/sauvegarde`, `sauvegarde_${b.code_marchand}_${horodatage()}.tlb.gz.enc`);
      toast.succes(`Sauvegarde téléchargée : ${nom}`);
    } catch (err) {
      toast.erreur(await messageErreurFichier(err, "Sauvegarde impossible"));
    } finally {
      setTelechargement(null);
    }
  }

  // Filtrage local : texte (nom, code marchand, ville, pays) + statut KYC
  const q = recherche.trim().toLowerCase();
  const affichees = boutiques.filter((b) =>
    (!q || [b.nom, b.code_marchand, b.ville, b.pays].some((v) => (v || "").toLowerCase().includes(q)))
    && (!filtreKyc || (b.kyc?.statut || "NON_FOURNI") === filtreKyc)
    && (!aValiderSeulement || b.validee === false));
  // Boutiques créées automatiquement (webhook) en attente de validation
  const nbAValider = boutiques.filter((b) => b.validee === false).length;

  // Boutique affichée dans la fenêtre « Dossier » (toujours la version à jour de la liste)
  const dossier = boutiques.find((b) => b.id === dossierId) || null;
  // Dossiers KYC à traiter (compteur affiché dans le filtre)
  const nbEnAttente = boutiques.filter((b) => b.kyc?.statut === "EN_ATTENTE").length;

  return (
    <div className="min-h-screen bg-gray-50">
      <EnTetePlateforme />

      <main className="mx-auto max-w-7xl p-4 sm:p-6">
        {/* Statistiques globales */}
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
          {[
            ["Boutiques", stats?.boutiques, "🏪"],
            ["Actives", stats?.boutiques_actives, "✅"],
            ["Utilisateurs", stats?.utilisateurs, "👥"],
            ["Commandes en ligne", stats?.commandes, "📦"],
            ["Factures validées", stats?.factures_validees, "🧾"],
          ].map(([libelle, valeur, icone]) => (
            <div key={libelle} className="card p-4">
              <p className="text-sm text-gray-500">{icone} {libelle}</p>
              <p className="text-2xl font-extrabold">{valeur === undefined ? "…" : montant(valeur)}</p>
            </div>
          ))}
        </div>

        {/* Titre + recherche + filtre KYC + création */}
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold">Boutiques</h1>
            <p className="text-sm text-gray-500">Les boutiques « mises en avant » apparaissent en tête du carrousel de la page d'accueil.</p>
          </div>
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
            <input className="input sm:w-64" placeholder="🔍 Nom, code, ville, pays…" value={recherche} onChange={(e) => setRecherche(e.target.value)} />
            <select className="input bg-white sm:w-56" value={filtreKyc} onChange={(e) => setFiltreKyc(e.target.value)} aria-label="Filtrer par statut KYC">
              <option value="">KYC : tous</option>
              {Object.entries(STATUTS_KYC).map(([code, s]) => (
                <option key={code} value={code}>KYC : {s.libelle}{code === "EN_ATTENTE" && nbEnAttente ? ` (${nbEnAttente})` : ""}</option>
              ))}
            </select>
            <button type="button" className="btn-outline whitespace-nowrap" onClick={() => setJournalOuvert(true)}>🔗 Webhook</button>
            <button type="button" className="btn-primary whitespace-nowrap" onClick={() => setCreation(true)}>+ Créer une boutique</button>
          </div>
        </div>

        {/* Bandeau : boutiques créées par le webhook, invisibles du public tant qu'elles ne sont pas validées */}
        {nbAValider > 0 && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <span>⏳ <b>{nbAValider}</b> boutique(s) créée(s) automatiquement attendent votre validation avant d'apparaître sur le portail.</span>
            <button type="button" className="btn-outline btn-sm bg-white" onClick={() => setAValiderSeulement(!aValiderSeulement)}>
              {aValiderSeulement ? "Voir toutes les boutiques" : "Voir seulement celles à valider"}
            </button>
          </div>
        )}

        {/* Liste des boutiques : une carte par boutique */}
        {chargement ? <Chargement /> : affichees.length === 0 ? <p className="py-10 text-center text-gray-500">Aucune boutique.</p> : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {affichees.map((b) => (
              <div key={b.id} className={`card flex flex-col gap-3 ${b.actif === false ? "border-red-200 bg-red-50/40" : b.validee === false ? "border-amber-300 bg-amber-50/40" : ""}`}>
                {/* Identité de la boutique + badges d'état */}
                <div className="flex items-start gap-3">
                  {b.logo_url
                    ? <img src={b.logo_url} alt="" className="h-14 w-14 shrink-0 rounded-xl border bg-white object-contain" />
                    : <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl text-2xl text-white" style={{ background: b.couleur || "#0b5ed7" }}>{b.nom.slice(0, 1)}</span>}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-lg font-bold">{b.nom}</p>
                    <p className="text-sm text-gray-500">
                      {[b.ville, b.pays].filter(Boolean).join(", ") || "Lieu non renseigné"} · créée le {date(b.created_at)}
                    </p>
                    {b.dg_nom && <p className="truncate text-xs text-gray-500">DG : {b.dg_nom}</p>}
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <span className="badge bg-gray-100 font-mono text-gray-700">{b.code_marchand}</span>
                      {b.actif === false ? <span className="badge bg-red-100 text-red-700">Suspendue</span> : <span className="badge bg-green-100 text-green-800">Active</span>}
                      {b.validee === false && <span className="badge bg-amber-100 text-amber-800">⏳ À valider</span>}
                      {b.origine === "webhook" && <span className="badge bg-purple-50 text-purple-800">Webhook</span>}
                      <BadgeKyc statut={b.kyc?.statut} />
                      {b.mise_en_avant && <span className="badge bg-amber-100 text-amber-800">⭐ En avant</span>}
                      <span className="badge bg-blue-50 text-blue-800">{b.nb_utilisateurs} utilisateur(s)</span>
                    </div>
                  </div>
                </div>

                {/* Envoi des identifiants au DG (boutiques créées par le webhook) */}
                {b.identifiants_envoi && (
                  <p className="text-xs text-gray-500">
                    Envoi des identifiants au DG le {date(b.identifiants_envoi.date)} — e-mail : {LIBELLES_ENVOI[b.identifiants_envoi.email]},
                    SMS : {LIBELLES_ENVOI[b.identifiants_envoi.sms]}
                  </p>
                )}

                {/* Actions principales */}
                <div className="grid grid-cols-2 gap-2">
                  {b.validee === false && (
                    <button type="button" className="btn-primary btn-sm col-span-2 bg-green-600 hover:bg-green-700" onClick={() => valider(b)}>
                      ✅ Valider la boutique (la rendre publique)
                    </button>
                  )}
                  <button type="button" className="btn-primary btn-sm col-span-2" onClick={() => ouvrirBackOffice(b)}>Ouvrir le back-office de cette boutique →</button>
                  <button type="button" className="btn-outline btn-sm col-span-2" onClick={() => setDossierId(b.id)}>
                    🗂️ Dossier de la boutique (identification & KYC)
                  </button>
                  <a href={`/b/${b.slug}`} target="_blank" rel="noreferrer" className="btn-outline btn-sm">Vitrine ↗</a>
                  <button type="button" className="btn-outline btn-sm" onClick={() => setQr(b)}>QR code</button>
                  <button type="button" className="btn-outline btn-sm" onClick={() => setEdition({ ...b, ordre: b.ordre ?? 0 })}>✏️ Modifier</button>
                  <button type="button" className={`btn-outline btn-sm ${b.mise_en_avant ? "text-amber-700" : ""}`}
                    onClick={() => modifier(b, { mise_en_avant: !b.mise_en_avant }, b.mise_en_avant ? "Retirée du carrousel" : "Mise en avant dans le carrousel")}>
                    {b.mise_en_avant ? "☆ Retirer" : "⭐ Mettre en avant"}
                  </button>

                  {/* Sauvegarde / restauration des données de la boutique */}
                  <button type="button" className="btn-outline btn-sm" disabled={telechargement === b.id} onClick={() => telechargerSauvegarde(b)}>
                    {telechargement === b.id ? "Préparation…" : "💾 Sauvegarde"}
                  </button>
                  <button type="button" className="btn-outline btn-sm text-red-700" onClick={() => setRestauration(b)}>♻️ Restaurer…</button>
                  <button type="button" className="btn-outline btn-sm col-span-2" onClick={() => renvoyerIdentifiants(b)}>✉️ Renvoyer les identifiants au DG</button>

                  {b.actif === false
                    ? <button type="button" className="btn-outline btn-sm col-span-2 text-green-700" onClick={() => modifier(b, { actif: true }, "Boutique réactivée")}>Réactiver la boutique</button>
                    : <button type="button" className="btn-outline btn-sm col-span-2 text-red-600"
                      onClick={() => window.confirm(`Suspendre « ${b.nom} » ? Sa vitrine ne sera plus visible.`) && modifier(b, { actif: false }, "Boutique suspendue")}>Suspendre la boutique</button>}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Journal des appels du webhook de création des boutiques */}
      <JournalWebhook ouvert={journalOuvert} onFermer={() => setJournalOuvert(false)} />

      {/* Fenêtre de création d'une boutique */}
      <CreationBoutique ouvert={creation} onFermer={() => setCreation(false)} onCreee={() => { setCreation(false); charger(); }} />

      {/* Fenêtre « Dossier de la boutique » (identification + KYC) */}
      <DossierBoutique boutique={dossier} onFermer={() => setDossierId(null)} onMaj={remplacer} />

      {/* Fenêtre de restauration d'une sauvegarde */}
      <Restauration boutique={restauration} onFermer={() => setRestauration(null)} onRestauree={charger} />

      {/* Fenêtre de modification (nom, code marchand, ordre d'affichage) */}
      <Modal ouvert={!!edition} titre="Modifier la boutique" onFermer={() => setEdition(null)}>
        {edition && (
          <form onSubmit={enregistrerEdition} className="space-y-3">
            <Champ label="Nom" aide="Changer le nom change aussi l'adresse de la vitrine (et donc son QR code)."><input className="input" required minLength={2} maxLength={120} value={edition.nom} onChange={(e) => setEdition({ ...edition, nom: e.target.value })} /></Champ>
            <Champ label="ID boutique (code marchand, 6 caractères)"><input className="input font-mono uppercase" required minLength={6} maxLength={6} pattern="[A-Za-z0-9]{6}" title="6 lettres ou chiffres" value={edition.code_marchand} onChange={(e) => setEdition({ ...edition, code_marchand: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "") })} /></Champ>
            <Champ label="Ordre dans le carrousel" aide="Les plus petits nombres passent en premier."><input className="input" type="number" value={edition.ordre} onChange={(e) => setEdition({ ...edition, ordre: e.target.value })} /></Champ>
            <p className="text-xs text-gray-500">Pays, adresse, DG, IFU… : bouton « Dossier de la boutique ».</p>
            <button className="btn-primary w-full">Enregistrer</button>
          </form>
        )}
      </Modal>

      {/* Fenêtre du QR code de la vitrine */}
      <Modal ouvert={!!qr} titre={qr ? `QR code — ${qr.nom}` : ""} onFermer={() => setQr(null)}>
        {qr && (
          <div className="flex flex-col items-center gap-3 text-center">
            <QrCode valeur={`${window.location.origin}/b/${qr.slug}`} taille={280} />
            <p className="break-all font-mono text-sm">{window.location.origin}/b/{qr.slug}</p>
            <p className="text-sm text-gray-500">ID boutique (code marchand) : <b className="font-mono">{qr.code_marchand}</b></p>
          </div>
        )}
      </Modal>
    </div>
  );
}
