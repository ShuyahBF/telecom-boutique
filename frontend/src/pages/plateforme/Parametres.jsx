import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import { EnTetePlateforme } from "./_plateforme/composants";
import ChampMotDePasse from "@/components/ChampMotDePasse";

// Valeurs proposées quand rien n'est encore réglé (exemple : messagerie sawalismartsystems.com)
const VIDE = {
  hote: "", port: 465, ssl: true, utilisateur: "", mot_de_passe: "",
  expediteur: "", nom_expediteur: "adLyn", actif: true,
};

// ---------------------------------------------------------------------------
// Page « Paramètres » de la plateforme (super-administrateur) :
// serveur d'envoi des e-mails (SMTP) utilisé pour les identifiants, rappels,
// rapports de la nuit... Modifiable à tout moment, sans redéployer.
// ---------------------------------------------------------------------------
export default function Parametres() {
  const toast = useToast();
  const { user } = useAuth();

  // Réglages affichés dans le formulaire (null = chargement)
  const [form, setForm] = useState(null);
  // Infos en lecture seule renvoyées par le serveur : mot de passe déjà saisi ? origine des réglages ?
  const [etat, setEtat] = useState({ a_mot_de_passe: false, source: "" });
  const [enregistrement, setEnregistrement] = useState(false);
  // Adresse qui recevra l'e-mail d'essai (par défaut : celle du super-admin connecté)
  const [destinataire, setDestinataire] = useState(user?.email || "");
  const [essaiEnCours, setEssaiEnCours] = useState(false);

  // Copie la réponse du serveur dans le formulaire (le mot de passe n'est jamais renvoyé)
  const appliquer = (data) => {
    // Rien de réglé nulle part : on l'indique au lieu d'afficher une origine trompeuse
    if (!data.hote) data = { ...data, source: "" };
    setForm({ ...VIDE, ...Object.fromEntries(Object.entries(data).filter(([, v]) => v !== null && v !== "")), mot_de_passe: "" });
    setEtat({ a_mot_de_passe: data.a_mot_de_passe, source: data.source });
  };

  // Chargement initial des réglages
  useEffect(() => {
    apiClient.get("/plateforme/parametres/smtp")
      .then(({ data }) => appliquer(data))
      .catch((err) => { toast.erreur(messageErreur(err, "Impossible de charger les paramètres")); setForm(VIDE); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Mise à jour d'un champ ; cocher SSL propose le port 465, le décocher le port 587
  const maj = (champ, valeur) => setForm((f) => {
    const suite = { ...f, [champ]: valeur };
    if (champ === "ssl") suite.port = valeur ? 465 : 587;
    return suite;
  });

  // Enregistrement (mot de passe vide = on garde celui déjà enregistré)
  async function enregistrer(e) {
    e.preventDefault();
    setEnregistrement(true);
    try {
      const { data } = await apiClient.put("/plateforme/parametres/smtp", {
        ...form, port: Number(form.port), mot_de_passe: form.mot_de_passe || null,
      });
      appliquer(data);
      toast.succes("Paramètres d'envoi enregistrés.");
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible"));
    } finally {
      setEnregistrement(false);
    }
  }

  // Envoi d'un e-mail d'essai avec les réglages ENREGISTRÉS
  async function essayer() {
    setEssaiEnCours(true);
    try {
      await apiClient.post("/plateforme/parametres/smtp/essai", { destinataire }, { timeout: 60000 });
      toast.succes(`E-mail d'essai envoyé à ${destinataire}. Vérifiez la boîte de réception (et les indésirables).`);
    } catch (err) {
      toast.erreur(messageErreur(err, "L'essai a échoué"));
    } finally {
      setEssaiEnCours(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <EnTetePlateforme />
      <main className="mx-auto max-w-3xl space-y-6 px-4 py-6">
        <div>
          <h1 className="text-2xl font-extrabold">⚙️ Paramètres de la plateforme</h1>
          <p className="text-sm text-gray-500">Réglages généraux d'adLyn, modifiables sans redéploiement.</p>
        </div>

        {!form ? <Chargement /> : (
          <>
            {/* ---------- Formulaire du serveur d'envoi (SMTP) ---------- */}
            <form onSubmit={enregistrer} className="card space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-bold">✉️ Serveur d'envoi des e-mails (SMTP)</h2>
                {/* Origine des réglages : base de données (écran) ou variables d'environnement Render */}
                <span className={`badge ${etat.source ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"}`}>
                  {etat.source === "administration" ? "Réglé depuis cet écran"
                    : etat.source ? "Réglé par Render (variables)" : "Non réglé"}
                </span>
              </div>
              <p className="text-sm text-gray-500">
                Adresse qui envoie les identifiants des boutiques, les rappels et les rapports de la nuit
                (ex. <b>messenger@sawalismartsystems.com</b>). Les réglages se trouvent dans l'espace
                messagerie de votre hébergeur.
              </p>

              <div className="grid gap-4 sm:grid-cols-3">
                {/* Serveur (hôte) */}
                <label className="sm:col-span-2">
                  <span className="label">Serveur SMTP</span>
                  <input className="input" required value={form.hote} placeholder="mail.sawalismartsystems.com"
                    onChange={(e) => maj("hote", e.target.value.trim())} />
                </label>
                {/* Port : 465 (SSL) ou 587 (STARTTLS) */}
                <label>
                  <span className="label">Port</span>
                  <input className="input" type="number" required min={1} max={65535} value={form.port}
                    onChange={(e) => maj("port", e.target.value)} />
                </label>
              </div>

              {/* Type de chiffrement */}
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.ssl} onChange={(e) => maj("ssl", e.target.checked)} />
                Connexion SSL directe (port 465) — décochée : STARTTLS (port 587)
              </label>

              <div className="grid gap-4 sm:grid-cols-2">
                {/* Identifiant de connexion (souvent l'adresse complète) */}
                <label>
                  <span className="label">Identifiant</span>
                  <input className="input" value={form.utilisateur} placeholder="messenger@sawalismartsystems.com"
                    autoComplete="off" onChange={(e) => maj("utilisateur", e.target.value.trim())} />
                </label>
                {/* Mot de passe : jamais réaffiché ; vide = inchangé */}
                <label>
                  <span className="label">Mot de passe</span>
                  <ChampMotDePasse value={form.mot_de_passe} autoComplete="new-password"
                    placeholder={etat.a_mot_de_passe ? "•••••••• (laisser vide pour garder)" : "Mot de passe de la boîte"}
                    onChange={(e) => maj("mot_de_passe", e.target.value)} />
                </label>
                {/* Adresse d'expédition */}
                <label>
                  <span className="label">Adresse d'expédition</span>
                  <input className="input" type="email" required value={form.expediteur}
                    placeholder="messenger@sawalismartsystems.com"
                    onChange={(e) => maj("expediteur", e.target.value.trim())} />
                </label>
                {/* Nom affiché chez le destinataire */}
                <label>
                  <span className="label">Nom affiché</span>
                  <input className="input" value={form.nom_expediteur} maxLength={60}
                    onChange={(e) => maj("nom_expediteur", e.target.value)} />
                </label>
              </div>

              {/* Interrupteur général : décoché, la plateforme n'envoie plus aucun e-mail */}
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.actif} onChange={(e) => maj("actif", e.target.checked)} />
                Envoi des e-mails activé
              </label>

              <button type="submit" className="btn-primary" disabled={enregistrement}>
                {enregistrement ? "Enregistrement…" : "💾 Enregistrer"}
              </button>
            </form>

            {/* ---------- E-mail d'essai ---------- */}
            <div className="card space-y-3">
              <h2 className="text-lg font-bold">🧪 Tester l'envoi</h2>
              <p className="text-sm text-gray-500">Enregistrez d'abord, puis envoyez un e-mail d'essai pour vérifier les réglages.</p>
              <div className="flex flex-wrap gap-2">
                <input className="input flex-1" type="email" value={destinataire} placeholder="votre@adresse.com"
                  onChange={(e) => setDestinataire(e.target.value.trim())} />
                <button type="button" className="btn-outline" disabled={essaiEnCours || !destinataire} onClick={essayer}>
                  {essaiEnCours ? "Envoi…" : "Envoyer un essai"}
                </button>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
