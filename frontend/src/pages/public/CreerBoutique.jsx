import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { LogoAdlyn } from "@/components/Marque";
import PoweredBySawali from "@/components/PoweredBySawali";
import Patientez from "@/components/Patientez";
import VersionApp from "@/components/VersionApp";
import EtatServeur from "@/components/EtatServeur";
import { ChampCode, IconeWhatsapp, useCompteARebours } from "@/components/CodeWhatsapp";

// ============================================================================
// Lot B — page publique « Créer ma boutique » (inscription LIBRE d'un commerçant).
// On y arrive depuis l'accueil et la page de connexion.
//   Étape 1 « Vos informations » : numéro WhatsApp, prénom, nom, nom de la boutique,
//            secteur d'activité (liste GET /secteurs, avec pictogrammes), ville,
//            quartier / adresse, position GPS FACULTATIVE (« Utiliser ma position »).
//            -> POST /inscription/demander-code : le serveur contrôle tout, vérifie
//            que le numéro est libre et envoie un code à 6 chiffres par WhatsApp.
//            RIEN n'est créé à cette étape.
//   Étape 2 « Code WhatsApp » : le code reçu -> POST /inscription/confirmer : la
//            boutique est créée EN ATTENTE DE VALIDATION et la session s'ouvre
//            aussitôt (le commerçant arrive dans son espace, bandeau d'attente).
// ============================================================================
const FORMULAIRE_VIDE = {
  telephone: "", prenom: "", nom: "", email: "", nom_boutique: "", secteur: "",
  pays: "Burkina Faso", ville: "", adresse: "", latitude: null, longitude: null, accepte_conditions: false,
  accepte_whatsapp: false, // lot 55 : consentement WhatsApp FACULTATIF, jamais coché d'office
};

export default function CreerBoutique() {
  const { ouvrirSession } = useAuth();
  const navigate = useNavigate();
  const [secteurs, setSecteurs] = useState([]); // secteurs d'activité actifs (code, libellé, icône)
  const [form, setForm] = useState(FORMULAIRE_VIDE);
  const [etape, setEtape] = useState("infos"); // "infos" puis "code"
  const [code, setCode] = useState("");
  const [envoiCode, setEnvoiCode] = useState(null); // réponse de la demande (numéro masqué, canal)
  const [erreur, setErreur] = useState(""); // message d'erreur affiché
  const [dejaInscrit, setDejaInscrit] = useState(false); // numéro déjà lié à une boutique
  const [attente, setAttente] = useState(""); // texte du toast « Patientez… » ("" = pas d'attente)
  const [reste, demarrer] = useCompteARebours(); // délai avant de redemander un code

  // Titre de l'onglet + liste des secteurs proposés
  useEffect(() => {
    document.title = "Créer ma boutique · adLyn";
    apiClient.get("/secteurs").then(({ data }) => setSecteurs(data)).catch(() => setSecteurs([]));
  }, []);

  // Mise à jour d'un champ (case à cocher ou texte)
  const champ = (cle) => (e) => setForm({ ...form, [cle]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  // Corps envoyé au serveur (e-mail vide = pas d'e-mail)
  const corps = () => ({ ...form, email: form.email.trim() || null });

  // Erreur du serveur : message lisible ; numéro déjà inscrit -> proposition de connexion
  function montrerErreur(err, repli) {
    const detail = err?.response?.data?.detail;
    setDejaInscrit(detail?.code === "numero_deja_inscrit");
    setErreur(messageErreur(err, repli));
  }

  // Bouton « Utiliser ma position » : coordonnées GPS du téléphone (facultatives)
  function utiliserMaPosition() {
    setErreur("");
    if (!navigator.geolocation) {
      setErreur("Votre navigateur ne permet pas de lire la position. Vous pouvez continuer sans.");
      return;
    }
    setAttente("Recherche de votre position…");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setForm((f) => ({ ...f, latitude: Number(pos.coords.latitude.toFixed(6)), longitude: Number(pos.coords.longitude.toFixed(6)) }));
        setAttente("");
      },
      () => {
        setErreur("Position indisponible (autorisation refusée ou signal GPS absent). Vous pouvez continuer sans.");
        setAttente("");
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    );
  }

  // Étape 1 (et « Renvoyer le code ») : contrôle du formulaire + envoi du code WhatsApp
  async function demanderCode(e) {
    e?.preventDefault();
    setErreur("");
    setDejaInscrit(false);
    if (!form.secteur) return setErreur("Choisissez le secteur d'activité principal de votre boutique.");
    setAttente("Envoi du code WhatsApp…");
    try {
      const { data } = await apiClient.post("/inscription/demander-code", corps());
      setEnvoiCode(data);
      setCode("");
      setEtape("code");
      demarrer(data.renvoi_dans_secondes);
    } catch (err) {
      montrerErreur(err, "Envoi du code impossible pour le moment");
    } finally {
      setAttente("");
    }
  }

  // Étape 2 : code reçu -> création de la boutique et ouverture de la session
  async function confirmer(e) {
    e.preventDefault();
    setErreur("");
    if (code.length !== 6) return setErreur("Le code contient 6 chiffres.");
    setAttente("Création de votre boutique…");
    try {
      const { data } = await apiClient.post("/inscription/confirmer", { ...corps(), code });
      ouvrirSession(data);
      navigate("/gestion", { replace: true, state: { bienvenue: true } });
    } catch (err) {
      montrerErreur(err, "Création impossible pour le moment");
    } finally {
      setAttente("");
    }
  }

  const secteurChoisi = secteurs.find((s) => s.code === form.secteur);

  return (
    <div className="fond-ondes flex min-h-screen flex-col items-center px-4 py-10">{/* fond « ondes » de la charte */}
      <Patientez actif={!!attente} texte={attente || undefined} />
      <Link to="/" aria-label="adLyn, accueil"><LogoAdlyn clair className="h-10" /></Link>

      <div className="carte-acces mt-6 w-full max-w-lg space-y-5">
        {/* En-tête + étapes */}
        <div>
          <p className="surtitre">14 jours d'essai gratuit</p>
          <h1 className="mt-1 text-2xl font-extrabold">Créer ma boutique</h1>
          <ol className="mt-3 flex items-center gap-2 text-xs font-semibold">
            <li className={`rounded-full px-3 py-1 ${etape === "infos" ? "bg-primary text-white" : "bg-green-100 text-green-800"}`}>
              {etape === "infos" ? "1" : "✓"} Vos informations
            </li>
            <li className="h-px flex-1 bg-gray-200" aria-hidden="true" />
            <li className={`rounded-full px-3 py-1 ${etape === "code" ? "bg-primary text-white" : "bg-gray-100 text-gray-500"}`}>2 Code WhatsApp</li>
          </ol>
        </div>

        {etape === "infos" ? (
          <form onSubmit={demanderCode} className="space-y-5">
            {/* --- Numéro WhatsApp : il sert d'identifiant de connexion --- */}
            <fieldset className="space-y-2">
              <legend className="label flex items-center gap-1.5"><IconeWhatsapp className="h-4 w-4" /> Votre numéro WhatsApp</legend>
              <input id="tel" className="input" type="tel" inputMode="tel" autoComplete="tel" required
                placeholder="70 12 34 56 ou +226 70 12 34 56" value={form.telephone} onChange={champ("telephone")} />
              <p className="text-xs text-gray-500">Vous y recevrez un code de vérification. Il vous servira ensuite à vous connecter.</p>
            </fieldset>

            {/* --- Identité du commerçant (DG de la boutique) --- */}
            <fieldset className="grid gap-3 sm:grid-cols-2">
              <legend className="label mb-2 sm:col-span-2">Vous</legend>
              <div><label className="label" htmlFor="prenom">Prénom</label>
                <input id="prenom" className="input" autoComplete="given-name" required minLength={2} value={form.prenom} onChange={champ("prenom")} /></div>
              <div><label className="label" htmlFor="nom">Nom</label>
                <input id="nom" className="input" autoComplete="family-name" required minLength={2} value={form.nom} onChange={champ("nom")} /></div>
              <div className="sm:col-span-2"><label className="label" htmlFor="email">E-mail <span className="font-normal text-gray-400">(facultatif)</span></label>
                <input id="email" className="input" type="email" autoComplete="email" value={form.email} onChange={champ("email")} /></div>
            </fieldset>

            {/* --- Boutique : nom et secteur d'activité principal --- */}
            <fieldset className="space-y-3">
              <legend className="label mb-2">Votre boutique</legend>
              <div><label className="label" htmlFor="nom_boutique">Nom de la boutique</label>
                <input id="nom_boutique" className="input" autoComplete="organization" required minLength={3} value={form.nom_boutique} onChange={champ("nom_boutique")} /></div>
              <div>
                <p className="label">Secteur d'activité principal</p>
                {secteurs.length === 0 ? <p className="text-sm text-gray-500">Chargement des secteurs…</p> : (
                  <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Secteur d'activité principal">
                    {secteurs.map((s) => (
                      <button key={s.code} type="button" role="radio" aria-checked={form.secteur === s.code}
                        onClick={() => setForm({ ...form, secteur: s.code })}
                        className={`flex items-center gap-2 rounded-xl border p-2.5 text-left text-sm transition ${form.secteur === s.code ? "border-primary bg-primary/5 font-semibold text-ink ring-2 ring-primary/30" : "border-gray-200 hover:border-primary/50"}`}>
                        <span className="text-xl" aria-hidden="true">{s.icone}</span>
                        <span className="leading-tight">{s.libelle}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </fieldset>

            {/* --- Adresse + géolocalisation facultative --- */}
            <fieldset className="grid gap-3 sm:grid-cols-2">
              <legend className="label mb-2 sm:col-span-2">Adresse</legend>
              <div><label className="label" htmlFor="ville">Ville</label>
                <input id="ville" className="input" autoComplete="address-level2" required minLength={2} value={form.ville} onChange={champ("ville")} /></div>
              <div><label className="label" htmlFor="pays">Pays</label>
                <input id="pays" className="input" autoComplete="country-name" required value={form.pays} onChange={champ("pays")} /></div>
              <div className="sm:col-span-2"><label className="label" htmlFor="adresse">Quartier / adresse</label>
                <input id="adresse" className="input" autoComplete="street-address" placeholder="Ex. Gounghin, près du marché" value={form.adresse} onChange={champ("adresse")} /></div>
              <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
                <button type="button" className="btn-outline btn-sm" onClick={utiliserMaPosition}>📍 Utiliser ma position</button>
                {form.latitude !== null ? (
                  <>
                    <span className="badge bg-green-100 text-green-800">Position enregistrée ({form.latitude}, {form.longitude})</span>
                    <button type="button" className="text-xs text-gray-500 underline" onClick={() => setForm({ ...form, latitude: null, longitude: null })}>Retirer</button>
                  </>
                ) : <span className="text-xs text-gray-500">Facultatif : aide vos clients à vous trouver.</span>}
              </div>
            </fieldset>

            <label className="flex items-start gap-3 rounded-xl border border-gray-200 p-3 text-sm">
              <input type="checkbox" className="mt-0.5 h-4 w-4" checked={form.accepte_conditions} onChange={champ("accepte_conditions")} />
              <span>J'accepte les <Link to="/conditions" className="text-primary underline">conditions d'utilisation</Link> et la{" "}
                <Link to="/confidentialite" className="text-primary underline">politique de confidentialité</Link> d'adLyn.</span>
            </label>

            {/* Lot 55 : consentement WhatsApp facultatif (décoché par défaut) */}
            <label className="flex items-start gap-3 rounded-xl border border-gray-200 p-3 text-sm">
              <input type="checkbox" className="mt-0.5 h-4 w-4" checked={form.accepte_whatsapp} onChange={champ("accepte_whatsapp")} data-testid="accepte-whatsapp" />
              <span>J'accepte de recevoir les nouveautés et offres d'adLyn sur WhatsApp{" "}
                <span className="text-gray-500">(facultatif — vous pourrez arrêter à tout moment en écrivant STOP)</span>.</span>
            </label>

            <BlocErreur erreur={erreur} dejaInscrit={dejaInscrit} />
            <button type="submit" className="btn-primary flex w-full items-center justify-center gap-2 py-3 text-base"
              disabled={!!attente || !form.accepte_conditions}>
              <IconeWhatsapp /> Recevoir mon code WhatsApp
            </button>
            <p className="text-center text-xs text-gray-500">
              Votre boutique sera visible du public après vérification par l'équipe adLyn (pièce d'identité demandée ensuite).
            </p>
          </form>
        ) : (
          <form onSubmit={confirmer} className="space-y-4">
            <div className="rounded-xl bg-green-50 p-3 text-sm text-green-900">
              Un code à 6 chiffres vient d'être envoyé par <b>{envoiCode?.canal || "WhatsApp"}</b> au{" "}
              <span className="whitespace-nowrap font-semibold">{envoiCode?.telephone_masque}</span>.
              Il est valable {envoiCode?.validite_minutes || 10} minutes.
            </div>
            {/* Rappel de ce qui va être créé */}
            <div className="rounded-xl border border-gray-200 p-3 text-sm">
              <p className="font-semibold">{secteurChoisi?.icone} {form.nom_boutique}</p>
              <p className="text-gray-500">{[form.adresse, form.ville, form.pays].filter(Boolean).join(", ")} · {form.prenom} {form.nom}</p>
            </div>
            <div>
              <label className="label" htmlFor="code">Code reçu par WhatsApp</label>
              <ChampCode id="code" value={code} onChange={setCode} />
            </div>
            <BlocErreur erreur={erreur} dejaInscrit={dejaInscrit} />
            <button type="submit" className="btn-primary w-full py-3 text-base" disabled={!!attente || code.length !== 6}>Créer ma boutique</button>
            <div className="flex items-center justify-between text-sm">
              <button type="button" className="text-gray-500 hover:text-primary" onClick={() => { setEtape("infos"); setErreur(""); }}>
                ← Modifier mes informations
              </button>
              <button type="button" className="font-semibold text-primary disabled:text-gray-400" disabled={reste > 0 || !!attente} onClick={demanderCode}>
                {reste > 0 ? `Renvoyer le code (${reste} s)` : "Renvoyer le code"}
              </button>
            </div>
          </form>
        )}

        <div className="border-t border-gray-100 pt-4 text-center text-sm text-gray-600">
          Déjà une boutique sur adLyn ? <Link to="/connexion" className="font-semibold text-primary">Me connecter</Link>
        </div>
        {/* État du serveur (actif, lent, injoignable) : règle du propriétaire */}
        <EtatServeur />
      </div>
      <PoweredBySawali className="mt-6" />
      <VersionApp className="mt-1 text-center text-gray-400" />
    </div>
  );
}

// Message d'erreur ; numéro déjà inscrit -> bouton de connexion par WhatsApp
function BlocErreur({ erreur, dejaInscrit }) {
  if (!erreur) return null;
  return (
    <div className="space-y-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
      <p>{erreur}</p>
      {dejaInscrit && (
        <Link to="/connexion?mode=whatsapp" className="btn-primary btn-sm inline-flex items-center gap-1.5">
          <IconeWhatsapp className="h-4 w-4" /> Me connecter avec WhatsApp
        </Link>
      )}
    </div>
  );
}
