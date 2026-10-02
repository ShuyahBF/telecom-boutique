import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import { EnTetePlateforme } from "./_plateforme/composants";
import ChampMotDePasse from "@/components/ChampMotDePasse";
import DeconnexionGenerale from "./_plateforme/DeconnexionGenerale";
import ReglageInactivite from "@/components/ReglageInactivite";
import ReglageSessionsMax from "@/components/ReglageSessionsMax";
import { AideService, AvertissementSmtp, HOTES_ZEPTOMAIL, SERVICES_EMAIL, nomService } from "@/components/ServicesEmail";

// Valeurs proposées quand rien n'est encore réglé
const VIDE = {
  fournisseur: "resend", actif: true, expediteur: "", nom_expediteur: "adLyn", cle_api: "",
  zeptomail_hote: "api.zeptomail.com",
  // SMTP (exemple : messagerie sawalismartsystems.com)
  hote: "", port: 465, ssl: true, utilisateur: "", mot_de_passe: "",
};

// Origine du service réellement utilisé
const ORIGINES = { administration: "Réglé depuis cet écran", "variables d'environnement": "Réglé par Render (variables)" };

// ---------------------------------------------------------------------------
// Page « Paramètres » de la plateforme (super-administrateur) :
// service d'envoi des e-mails (Resend, ZeptoMail, Brevo ou SMTP) utilisé pour les
// identifiants, rappels, rapports de la nuit... Modifiable à tout moment, sans redéployer.
// ---------------------------------------------------------------------------
export default function Parametres() {
  const toast = useToast();
  const { user } = useAuth();

  // Réglages affichés dans le formulaire (null = chargement)
  const [form, setForm] = useState(null);
  // Infos en lecture seule renvoyées par le serveur : secrets déjà saisis (jamais leur valeur),
  // service réellement utilisé et son origine
  const [etat, setEtat] = useState({ a_cle: false, cles: {}, cles_env: {}, a_mot_de_passe: false,
    fournisseur_effectif: "", source: "", pret: false, raison: "" });
  const [journal, setJournal] = useState([]);
  const [enregistrement, setEnregistrement] = useState(false);
  // Adresse qui recevra l'e-mail d'essai (par défaut : celle du super-admin connecté)
  const [destinataire, setDestinataire] = useState(user?.email || "");
  const [essaiEnCours, setEssaiEnCours] = useState(false);
  const [erreurEssai, setErreurEssai] = useState("");

  // Copie la réponse du serveur dans le formulaire (aucun secret n'est renvoyé)
  const appliquer = (data) => {
    setForm({
      ...VIDE,
      // Rien de réglé dans l'écran : on propose le service des variables de repli
      fournisseur: data.fournisseur || data.fournisseur_effectif || VIDE.fournisseur,
      actif: data.actif ?? true, expediteur: data.expediteur || "", nom_expediteur: data.nom_expediteur || "adLyn",
      zeptomail_hote: data.zeptomail_hote || VIDE.zeptomail_hote,
      hote: data.smtp?.hote || "", port: data.smtp?.port || VIDE.port, ssl: data.smtp?.hote ? !!data.smtp.ssl : VIDE.ssl,
      utilisateur: data.smtp?.utilisateur || "",
    });
    setEtat({ a_cle: !!data.a_cle, cles: data.cles || {}, cles_env: data.cles_env || {},
      a_mot_de_passe: !!data.smtp?.a_mot_de_passe, fournisseur_effectif: data.fournisseur_effectif || "",
      source: data.source || "", pret: !!data.pret, raison: data.raison || "" });
  };

  // Journal des modifications (qui, quand, quel service)
  const chargerJournal = () => apiClient.get("/plateforme/parametres/email/journal")
    .then(({ data }) => setJournal(data)).catch(() => {});

  // Chargement initial des réglages
  useEffect(() => {
    apiClient.get("/plateforme/parametres/email")
      .then(({ data }) => appliquer(data))
      .catch((err) => { toast.erreur(messageErreur(err, "Impossible de charger les paramètres")); setForm(VIDE); });
    chargerJournal();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Mise à jour d'un champ ; cocher SSL propose le port 465, le décocher le port 587
  const maj = (champ, valeur) => setForm((f) => {
    const suite = { ...f, [champ]: valeur };
    if (champ === "ssl") suite.port = valeur ? 465 : 587;
    if (champ === "fournisseur") suite.cle_api = "";
    return suite;
  });

  // Une clé est-elle déjà connue pour le service choisi (écran ou variable Render) ?
  const cleConnue = !!etat.cles[form?.fournisseur];
  const cleEnv = !!etat.cles_env[form?.fournisseur];

  // Enregistrement (champ secret vide = valeur conservée)
  async function enregistrer(e) {
    e.preventDefault();
    setEnregistrement(true);
    try {
      const { data } = await apiClient.put("/plateforme/parametres/email", {
        ...form, port: Number(form.port), expediteur: form.expediteur || null,
        cle_api: form.cle_api || null, mot_de_passe: form.mot_de_passe || null,
      });
      appliquer(data);
      chargerJournal();
      toast.succes("Paramètres d'envoi enregistrés.");
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible"));
    } finally {
      setEnregistrement(false);
    }
  }

  // Envoi d'un e-mail d'essai avec les réglages ENREGISTRÉS ; le message du fournisseur est affiché
  async function essayer() {
    setEssaiEnCours(true);
    setErreurEssai("");
    try {
      await apiClient.post("/plateforme/parametres/email/essai", { destinataire }, { timeout: 60000 });
      toast.succes(`E-mail d'essai envoyé à ${destinataire}. Vérifiez la boîte de réception (et les indésirables).`);
    } catch (err) {
      const message = messageErreur(err, "L'essai a échoué");
      setErreurEssai(message);
      toast.erreur(message);
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

        {/* Maintenance : déconnexion programmée de tous les utilisateurs */}
        <DeconnexionGenerale />

        {/* Déconnexion après inactivité : valeur par défaut de toutes les boutiques */}
        <div className="card space-y-2">
          <h2 className="text-lg font-bold">⏳ Déconnexion après inactivité</h2>
          <ReglageInactivite mode="plateforme" />
        </div>

        {/* Sessions simultanées : nombre maximal par compte */}
        <div className="card space-y-2">
          <h2 className="text-lg font-bold">💻 Sessions simultanées par compte</h2>
          <ReglageSessionsMax />
        </div>

        {!form ? <Chargement /> : (
          <>
            {/* ---------- Service d'envoi des e-mails ---------- */}
            <form onSubmit={enregistrer} className="card space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-bold">✉️ Service d'envoi des e-mails</h2>
                {/* Service réellement utilisé et origine du réglage (écran ou variables Render) */}
                <span className={`badge ${etat.pret ? "bg-green-100 text-green-800" : "bg-amber-100 text-amber-800"}`}>
                  {etat.pret ? `${nomService(etat.fournisseur_effectif)} — ${ORIGINES[etat.source] || etat.source}` : "Non opérationnel"}
                </span>
              </div>
              <p className="text-sm text-gray-500">
                Envoie les identifiants des boutiques, les rappels, les rapports de la nuit, et les e-mails des boutiques
                réglées sur « Service de la plateforme ».
              </p>
              {!etat.pret && etat.raison && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">⚠️ {etat.raison}</p>}

              {/* Choix du service */}
              <label className="block">
                <span className="label">Service d'envoi</span>
                <select className="input" value={form.fournisseur} onChange={(e) => maj("fournisseur", e.target.value)}>
                  {SERVICES_EMAIL.map((s) => <option key={s.code} value={s.code}>{s.libelle}</option>)}
                  <option value="desactive">Désactivé</option>
                </select>
              </label>
              <AideService code={form.fournisseur} />

              {form.fournisseur !== "desactive" && (
                <>
                  {/* Champs communs : adresse (domaine validé chez le fournisseur) et nom affiché */}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label>
                      <span className="label">Adresse d'expéditeur</span>
                      <input className="input" type="email" required value={form.expediteur}
                        placeholder="noreply@mondomaine.com" onChange={(e) => maj("expediteur", e.target.value.trim())} />
                    </label>
                    <label>
                      <span className="label">Nom affiché</span>
                      <input className="input" value={form.nom_expediteur} maxLength={60}
                        onChange={(e) => maj("nom_expediteur", e.target.value)} />
                    </label>
                  </div>

                  {/* Resend / ZeptoMail / Brevo : clé API (jamais réaffichée ; vide = conservée) */}
                  {form.fournisseur !== "smtp" && (
                    <div className="grid gap-4 sm:grid-cols-2">
                      <label className={form.fournisseur === "zeptomail" ? "" : "sm:col-span-2"}>
                        <span className="label">Clé API</span>
                        <ChampMotDePasse value={form.cle_api} autoComplete="new-password" maxLength={500}
                          placeholder={cleConnue ? "•••••••• (laisser vide pour garder)"
                            : cleEnv ? "Clé des variables Render utilisée (laisser vide)" : "Collez la clé API"}
                          onChange={(e) => maj("cle_api", e.target.value)} />
                      </label>
                      {form.fournisseur === "zeptomail" && (
                        <label>
                          <span className="label">Région</span>
                          <select className="input" value={form.zeptomail_hote} onChange={(e) => maj("zeptomail_hote", e.target.value)}>
                            {HOTES_ZEPTOMAIL.map((h) => <option key={h.code} value={h.code}>{h.libelle}</option>)}
                          </select>
                        </label>
                      )}
                    </div>
                  )}

                  {/* SMTP : champs historiques et avertissement Render */}
                  {form.fournisseur === "smtp" && (
                    <>
                      <AvertissementSmtp />
                      <div className="grid gap-4 sm:grid-cols-3">
                        <label className="sm:col-span-2">
                          <span className="label">Serveur SMTP</span>
                          <input className="input" required value={form.hote} placeholder="mail.sawalismartsystems.com"
                            onChange={(e) => maj("hote", e.target.value.trim())} />
                        </label>
                        <label>
                          <span className="label">Port</span>
                          <input className="input" type="number" required min={1} max={65535} value={form.port}
                            onChange={(e) => maj("port", e.target.value)} />
                        </label>
                      </div>
                      <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={form.ssl} onChange={(e) => maj("ssl", e.target.checked)} />
                        Connexion SSL directe (port 465) — décochée : STARTTLS (port 587)
                      </label>
                      <div className="grid gap-4 sm:grid-cols-2">
                        <label>
                          <span className="label">Identifiant</span>
                          <input className="input" value={form.utilisateur} placeholder="messenger@sawalismartsystems.com"
                            autoComplete="off" onChange={(e) => maj("utilisateur", e.target.value.trim())} />
                        </label>
                        <label>
                          <span className="label">Mot de passe</span>
                          <ChampMotDePasse value={form.mot_de_passe} autoComplete="new-password"
                            placeholder={etat.a_mot_de_passe ? "•••••••• (laisser vide pour garder)" : "Mot de passe de la boîte"}
                            onChange={(e) => maj("mot_de_passe", e.target.value)} />
                        </label>
                      </div>
                    </>
                  )}

                  {/* Interrupteur général : décoché, la plateforme n'envoie plus aucun e-mail */}
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.actif} onChange={(e) => maj("actif", e.target.checked)} />
                    Envoi des e-mails activé
                  </label>
                </>
              )}

              <button type="submit" className="btn-primary" disabled={enregistrement}>
                {enregistrement ? "Enregistrement…" : "💾 Enregistrer"}
              </button>
            </form>

            {/* ---------- E-mail d'essai (réglages enregistrés) ---------- */}
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
              {/* Message d'erreur du fournisseur, tel quel */}
              {erreurEssai && <p className="break-words rounded-xl bg-red-50 p-3 font-mono text-xs text-red-800">{erreurEssai}</p>}
            </div>

            {/* ---------- Journal des modifications (jamais la clé) ---------- */}
            {journal.length > 0 && (
              <div className="card space-y-2">
                <h2 className="text-lg font-bold">🗒️ Modifications du service d'envoi</h2>
                <ul className="divide-y text-sm">
                  {journal.map((j) => (
                    <li key={j.id} className="flex flex-wrap justify-between gap-2 py-1.5">
                      <span>{nomService(j.fournisseur)} — {j.par || "?"}</span>
                      <span className="text-gray-500">{new Date(j.date).toLocaleString("fr-FR")}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
