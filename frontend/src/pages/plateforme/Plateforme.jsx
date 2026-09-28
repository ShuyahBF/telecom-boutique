import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, montant } from "@/lib/format";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import QrCode from "@/components/QrCode";
import { useToast } from "@/components/Toast";

// Formulaire vierge de création d'une boutique (+ son premier gérant)
const CREATION_VIDE = {
  nom: "", ville: "", telephone: "", email: "", code_marchand: "",
  gerant_nom: "", gerant_email: "", gerant_mot_de_passe: "",
};

// Petit champ de formulaire (libellé + contrôle)
function Champ({ label, aide, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="label">{label}</span>
      {children}
      {aide && <span className="mt-1 block text-xs text-gray-500">{aide}</span>}
    </label>
  );
}

// Page d'administration de la PLATEFORME (super-administrateur) :
// statistiques globales et gestion de toutes les boutiques.
export default function Plateforme() {
  const { user, deconnexion, choisirBoutique } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();

  // --- État ---
  const [stats, setStats] = useState(null);
  const [boutiques, setBoutiques] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [recherche, setRecherche] = useState("");
  const [creation, setCreation] = useState(null); // formulaire de création (null = fermé)
  const [edition, setEdition] = useState(null); // boutique en cours de modification
  const [qr, setQr] = useState(null); // boutique dont on affiche le QR code
  const [occupe, setOccupe] = useState(false);

  // Chargement des statistiques et de la liste des boutiques
  const charger = useCallback(() => {
    apiClient.get("/plateforme/statistiques").then(({ data }) => setStats(data)).catch(() => {});
    apiClient.get("/plateforme/boutiques")
      .then(({ data }) => setBoutiques(data))
      .catch((err) => toast.erreur(messageErreur(err, "Impossible de charger les boutiques")))
      .finally(() => setChargement(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { charger(); }, [charger]);

  // Modification partielle d'une boutique (PATCH) : suspension, mise en avant, nom…
  async function modifier(b, changements, message) {
    try {
      const { data } = await apiClient.patch(`/plateforme/boutiques/${b.id}`, changements);
      setBoutiques((liste) => liste.map((x) => (x.id === data.id ? { ...x, ...data } : x)));
      toast.succes(message);
      return true;
    } catch (err) {
      toast.erreur(messageErreur(err, "Modification impossible"));
      return false;
    }
  }

  // Création d'une boutique + compte gérant (POST /plateforme/boutiques)
  async function creer(e) {
    e.preventDefault();
    setOccupe(true);
    try {
      const { data } = await apiClient.post("/plateforme/boutiques", {
        ...creation, email: creation.email || null, code_marchand: creation.code_marchand || null,
      });
      toast.succes(`Boutique « ${data.boutique.nom} » créée (code ${data.boutique.code_marchand})`);
      setCreation(null);
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez les champs (e-mails, mot de passe de 8 caractères minimum)"));
    } finally {
      setOccupe(false);
    }
  }

  // Enregistrement de la fenêtre « Modifier » (nom, code marchand, ordre)
  async function enregistrerEdition(e) {
    e.preventDefault();
    const ok = await modifier(edition, { nom: edition.nom, code_marchand: edition.code_marchand, ordre: Number(edition.ordre) || 0 }, "Boutique modifiée");
    if (ok) setEdition(null);
  }

  // Ouvrir le back-office d'une boutique en tant qu'administrateur
  async function ouvrirBackOffice(b) {
    await choisirBoutique(b.id);
    navigate("/gestion");
  }

  // Filtrage local (nom, code marchand, ville)
  const q = recherche.trim().toLowerCase();
  const affichees = q ? boutiques.filter((b) => [b.nom, b.code_marchand, b.ville].some((v) => (v || "").toLowerCase().includes(q))) : boutiques;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* En-tête simple de la plateforme */}
      <header className="sticky top-0 z-30 border-b border-gray-200 bg-ink text-white">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary">📱</span>
          <div className="min-w-0 flex-1">
            <p className="font-extrabold leading-tight">TelecomBoutique</p>
            <p className="truncate text-xs text-gray-300">Administration de la plateforme · {user?.nom}</p>
          </div>
          <a href="/" target="_blank" rel="noreferrer" className="hidden text-sm font-semibold text-gray-200 hover:text-white sm:inline">Portail public ↗</a>
          <button type="button" className="btn btn-sm border border-white/30 text-white hover:bg-white/10" onClick={() => { deconnexion(); navigate("/connexion"); }}>Déconnexion</button>
        </div>
      </header>

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

        {/* Titre + actions */}
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold">Boutiques</h1>
            <p className="text-sm text-gray-500">Les boutiques « mises en avant » apparaissent en tête du carrousel de la page d'accueil.</p>
          </div>
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
            <input className="input sm:w-64" placeholder="🔍 Nom, code, ville…" value={recherche} onChange={(e) => setRecherche(e.target.value)} />
            <button type="button" className="btn-primary" onClick={() => setCreation({ ...CREATION_VIDE })}>+ Créer une boutique</button>
          </div>
        </div>

        {/* Liste des boutiques : une carte par boutique */}
        {chargement ? <Chargement /> : affichees.length === 0 ? <p className="py-10 text-center text-gray-500">Aucune boutique.</p> : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {affichees.map((b) => (
              <div key={b.id} className={`card flex flex-col gap-3 ${b.actif === false ? "border-red-200 bg-red-50/40" : ""}`}>
                <div className="flex items-start gap-3">
                  {b.logo_url
                    ? <img src={b.logo_url} alt="" className="h-14 w-14 shrink-0 rounded-xl border bg-white object-contain" />
                    : <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl text-2xl text-white" style={{ background: b.couleur || "#0b5ed7" }}>{b.nom.slice(0, 1)}</span>}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-lg font-bold">{b.nom}</p>
                    <p className="text-sm text-gray-500">{b.ville || "Ville non renseignée"} · créée le {date(b.created_at)}</p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <span className="badge bg-gray-100 font-mono text-gray-700">{b.code_marchand}</span>
                      {b.actif === false ? <span className="badge bg-red-100 text-red-700">Suspendue</span> : <span className="badge bg-green-100 text-green-800">Active</span>}
                      {b.mise_en_avant && <span className="badge bg-amber-100 text-amber-800">⭐ En avant</span>}
                      <span className="badge bg-blue-50 text-blue-800">{b.nb_utilisateurs} utilisateur(s)</span>
                    </div>
                  </div>
                </div>

                {/* Actions principales */}
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" className="btn-primary btn-sm col-span-2" onClick={() => ouvrirBackOffice(b)}>Ouvrir le back-office de cette boutique →</button>
                  <a href={`/b/${b.slug}`} target="_blank" rel="noreferrer" className="btn-outline btn-sm">Vitrine ↗</a>
                  <button type="button" className="btn-outline btn-sm" onClick={() => setQr(b)}>QR code</button>
                  <button type="button" className="btn-outline btn-sm" onClick={() => setEdition({ ...b, ordre: b.ordre ?? 0 })}>✏️ Modifier</button>
                  <button type="button" className={`btn-outline btn-sm ${b.mise_en_avant ? "text-amber-700" : ""}`}
                    onClick={() => modifier(b, { mise_en_avant: !b.mise_en_avant }, b.mise_en_avant ? "Retirée du carrousel" : "Mise en avant dans le carrousel")}>
                    {b.mise_en_avant ? "☆ Ne plus mettre en avant" : "⭐ Mettre en avant"}
                  </button>
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

      {/* Fenêtre de création d'une boutique */}
      <Modal ouvert={!!creation} titre="Créer une boutique" onFermer={() => setCreation(null)} large>
        {creation && (
          <form onSubmit={creer} className="grid gap-3 sm:grid-cols-2">
            <p className="font-semibold text-gray-700 sm:col-span-2">La boutique</p>
            <Champ label="Nom *" className="sm:col-span-2"><input className="input" required minLength={2} maxLength={120} value={creation.nom} onChange={(e) => setCreation({ ...creation, nom: e.target.value })} /></Champ>
            <Champ label="Ville"><input className="input" value={creation.ville} onChange={(e) => setCreation({ ...creation, ville: e.target.value })} /></Champ>
            <Champ label="Téléphone"><input className="input" value={creation.telephone} onChange={(e) => setCreation({ ...creation, telephone: e.target.value })} /></Champ>
            <Champ label="E-mail"><input className="input" type="email" value={creation.email} onChange={(e) => setCreation({ ...creation, email: e.target.value })} /></Champ>
            <Champ label="Code marchand" aide="Facultatif : laissé vide, un code est créé automatiquement."><input className="input font-mono uppercase" maxLength={12} value={creation.code_marchand} onChange={(e) => setCreation({ ...creation, code_marchand: e.target.value })} /></Champ>
            <p className="mt-2 border-t pt-3 font-semibold text-gray-700 sm:col-span-2">Premier compte gérant</p>
            <Champ label="Nom du gérant *"><input className="input" required minLength={2} value={creation.gerant_nom} onChange={(e) => setCreation({ ...creation, gerant_nom: e.target.value })} /></Champ>
            <Champ label="E-mail du gérant *"><input className="input" type="email" required value={creation.gerant_email} onChange={(e) => setCreation({ ...creation, gerant_email: e.target.value })} /></Champ>
            <Champ label="Mot de passe *" aide="8 caractères minimum ; à transmettre au gérant." className="sm:col-span-2"><input className="input" type="text" required minLength={8} autoComplete="new-password" value={creation.gerant_mot_de_passe} onChange={(e) => setCreation({ ...creation, gerant_mot_de_passe: e.target.value })} /></Champ>
            <button className="btn-primary sm:col-span-2" disabled={occupe}>{occupe ? "Création…" : "Créer la boutique"}</button>
          </form>
        )}
      </Modal>

      {/* Fenêtre de modification (nom, code marchand, ordre d'affichage) */}
      <Modal ouvert={!!edition} titre="Modifier la boutique" onFermer={() => setEdition(null)}>
        {edition && (
          <form onSubmit={enregistrerEdition} className="space-y-3">
            <Champ label="Nom" aide="Changer le nom change aussi l'adresse de la vitrine (et donc son QR code)."><input className="input" required minLength={2} maxLength={120} value={edition.nom} onChange={(e) => setEdition({ ...edition, nom: e.target.value })} /></Champ>
            <Champ label="Code marchand"><input className="input font-mono uppercase" required minLength={3} maxLength={12} value={edition.code_marchand} onChange={(e) => setEdition({ ...edition, code_marchand: e.target.value })} /></Champ>
            <Champ label="Ordre dans le carrousel" aide="Les plus petits nombres passent en premier."><input className="input" type="number" value={edition.ordre} onChange={(e) => setEdition({ ...edition, ordre: e.target.value })} /></Champ>
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
            <p className="text-sm text-gray-500">Code marchand : <b className="font-mono">{qr.code_marchand}</b></p>
          </div>
        )}
      </Modal>
    </div>
  );
}
