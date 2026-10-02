import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Case, Champ } from "./communs";
import ChampMotDePasse from "@/components/ChampMotDePasse";
import { AideService, AvertissementSmtp, HOTES_ZEPTOMAIL, SERVICES_EMAIL } from "@/components/ServicesEmail";

// Onglet « Messagerie (e-mails) » : choix du service d'envoi (celui de la plateforme
// par défaut, ou le propre compte Resend / ZeptoMail / Brevo / SMTP de la boutique)
// et envoi d'un e-mail de test.
export default function ParamMessagerie() {
  const { user, boutique, setBoutique } = useAuth();
  const toast = useToast();
  const actuel = boutique.messagerie || {};

  // Réglages modifiables. Ni le mot de passe ni la clé API ne sont renvoyés par l'API :
  // les champs restent vides, et vide = « garder la valeur enregistrée ».
  const [reglages, setReglages] = useState({
    email_actif: !!actuel.email_actif, fournisseur: actuel.fournisseur || "plateforme", cle_api: "",
    zeptomail_hote: actuel.zeptomail_hote || "api.zeptomail.com",
    smtp_hote: actuel.smtp_hote || "", smtp_port: actuel.smtp_port || 587,
    smtp_utilisateur: actuel.smtp_utilisateur || "", smtp_mot_de_passe: "", smtp_tls: actuel.smtp_tls ?? true,
    smtp_ssl: !!actuel.smtp_ssl, expediteur_nom: actuel.expediteur_nom || "", expediteur_email: actuel.expediteur_email || "",
    email_equipe: actuel.email_equipe || "",
  });
  const [envoi, setEnvoi] = useState(false);
  const [destinataire, setDestinataire] = useState(boutique.email || user.email || "");
  const [test, setTest] = useState(null); // résultat du dernier e-mail de test
  const [testEnCours, setTestEnCours] = useState(false);
  const maj = (champ, valeur) => setReglages((r) => ({ ...r, [champ]: valeur, ...(champ === "fournisseur" ? { cle_api: "" } : {}) }));
  // Service d'envoi de la plateforme (utilisé par le choix « Service de la plateforme »)
  const [plateforme, setPlateforme] = useState({ plateforme_pret: false, plateforme_expediteur: "", plateforme_raison: "" });
  useEffect(() => {
    apiClient.get("/boutique/messagerie/fournisseur").then(({ data }) => setPlateforme(data)).catch(() => {});
  }, []);
  const f = reglages.fournisseur;
  const cleConnue = !!(actuel.cles || {})[f];

  // Enregistrement des réglages (PUT /boutique/messagerie)
  async function enregistrer(e) {
    e.preventDefault();
    setEnvoi(true);
    try {
      const { data } = await apiClient.put("/boutique/messagerie", {
        ...reglages, smtp_port: Number(reglages.smtp_port) || 587,
        smtp_mot_de_passe: reglages.smtp_mot_de_passe || null, cle_api: reglages.cle_api || null,
        expediteur_email: reglages.expediteur_email || null, email_equipe: reglages.email_equipe || null,
      });
      setBoutique({ ...boutique, messagerie: data });
      setReglages((r) => ({ ...r, smtp_mot_de_passe: "", cle_api: "" }));
      toast.succes("Réglages de messagerie enregistrés");
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez le port et les adresses e-mail"));
    } finally {
      setEnvoi(false);
    }
  }

  // E-mail de test (POST /boutique/messagerie/test) : on affiche le résultat tel quel
  async function tester(e) {
    e.preventDefault();
    setTestEnCours(true);
    setTest(null);
    try {
      const { data } = await apiClient.post("/boutique/messagerie/test", { destinataire });
      setTest(data);
    } catch (err) {
      setTest({ statut: "ECHEC", erreur: messageErreur(err, "Adresse du destinataire invalide") });
    } finally {
      setTestEnCours(false);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <form onSubmit={enregistrer} className="card grid gap-4 sm:grid-cols-2 lg:col-span-2">
        <h2 className="font-bold sm:col-span-2">Service d'envoi des e-mails</h2>
        <div className="sm:col-span-2"><Case label="Envoyer des e-mails aux clients et à l'équipe" aide="Confirmations de commande, avancement des réparations, réponses aux demandes de conseil…" checked={reglages.email_actif} onChange={(v) => maj("email_actif", v)} /></div>

        {/* Choix du service : celui de la plateforme (défaut) ou le sien */}
        <Champ label="Service d'envoi" className="sm:col-span-2">
          <select className="input" value={f} onChange={(e) => maj("fournisseur", e.target.value)}>
            <option value="plateforme">Service de la plateforme (recommandé)</option>
            {SERVICES_EMAIL.map((s) => <option key={s.code} value={s.code}>Mon compte {s.libelle}</option>)}
          </select>
        </Champ>
        {f === "plateforme" && (
          plateforme.plateforme_pret ? (
            <p className="rounded-xl bg-green-50 p-3 text-sm text-green-900 sm:col-span-2">
              ✅ Les e-mails partent de l'adresse de la plateforme (<b className="font-mono">{plateforme.plateforme_expediteur}</b>),
              au nom de votre boutique. Les réponses des clients arrivent à votre « adresse de l'expéditeur ».
            </p>
          ) : (
            <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900 sm:col-span-2">
              ⚠️ Le service d'envoi de la plateforme n'est pas encore opérationnel : contactez l'administrateur, ou choisissez votre propre service.
            </p>
          )
        )}
        <div className="sm:col-span-2"><AideService code={f} /></div>

        {/* Propre compte Resend / ZeptoMail / Brevo : clé API (chiffrée, jamais réaffichée) */}
        {["resend", "zeptomail", "brevo"].includes(f) && (
          <>
            <Champ label="Clé API" className={f === "zeptomail" ? "" : "sm:col-span-2"}
              aide={cleConnue ? "✔ Clé enregistrée. Laissez vide pour la conserver." : "Aucune clé enregistrée."}>
              <ChampMotDePasse maxLength={500} autoComplete="new-password" value={reglages.cle_api}
                onChange={(e) => maj("cle_api", e.target.value)} placeholder={cleConnue ? "•••••••• (inchangée)" : "Collez la clé API"} />
            </Champ>
            {f === "zeptomail" && (
              <Champ label="Région">
                <select className="input" value={reglages.zeptomail_hote} onChange={(e) => maj("zeptomail_hote", e.target.value)}>
                  {HOTES_ZEPTOMAIL.map((h) => <option key={h.code} value={h.code}>{h.libelle}</option>)}
                </select>
              </Champ>
            )}
          </>
        )}

        {/* Propre serveur SMTP : avertissement Render et champs historiques */}
        {f === "smtp" && (
          <>
            <div className="sm:col-span-2"><AvertissementSmtp /></div>
            <Champ label="Serveur SMTP"><input className="input" maxLength={150} value={reglages.smtp_hote} onChange={(e) => maj("smtp_hote", e.target.value)} placeholder="smtp.gmail.com" /></Champ>
            <Champ label="Port"><input className="input" type="number" min={1} max={65535} value={reglages.smtp_port} onChange={(e) => maj("smtp_port", e.target.value)} /></Champ>
            <Champ label="Utilisateur"><input className="input" maxLength={150} autoComplete="off" value={reglages.smtp_utilisateur} onChange={(e) => maj("smtp_utilisateur", e.target.value)} placeholder="votre.adresse@gmail.com" /></Champ>
            <Champ label="Mot de passe" aide={actuel.a_mot_de_passe ? "✔ Mot de passe enregistré. Laissez vide pour le conserver." : "Aucun mot de passe enregistré."}>
              <ChampMotDePasse maxLength={150} autoComplete="new-password" value={reglages.smtp_mot_de_passe}
                onChange={(e) => maj("smtp_mot_de_passe", e.target.value)} placeholder={actuel.a_mot_de_passe ? "•••••••• (inchangé)" : ""} />
            </Champ>
            <Case label="STARTTLS (port 587)" checked={reglages.smtp_tls} onChange={(v) => maj("smtp_tls", v)} />
            <Case label="SSL direct (port 465)" checked={reglages.smtp_ssl} onChange={(v) => maj("smtp_ssl", v)} />
          </>
        )}

        <Champ label="Nom de l'expéditeur"><input className="input" maxLength={100} value={reglages.expediteur_nom} onChange={(e) => maj("expediteur_nom", e.target.value)} /></Champ>
        <Champ label="Adresse de l'expéditeur" aide={f === "plateforme" ? "Reçoit les réponses des clients." : "Sur un domaine validé chez votre fournisseur."}>
          <input className="input" type="email" value={reglages.expediteur_email} onChange={(e) => maj("expediteur_email", e.target.value)} />
        </Champ>
        <Champ label="E-mail de l'équipe" aide="Reçoit les alertes : nouvelle commande, nouvelle demande de conseil." className="sm:col-span-2">
          <input className="input" type="email" value={reglages.email_equipe} onChange={(e) => maj("email_equipe", e.target.value)} />
        </Champ>
        <button className="btn-primary sm:col-span-2 sm:justify-self-start" disabled={envoi}>{envoi ? "Enregistrement…" : "💾 Enregistrer les réglages"}</button>
      </form>

      <div className="space-y-5">
        {/* Aide pour Gmail (seulement avec son propre serveur SMTP) */}
        {f === "smtp" && (
          <div className="card text-sm">
            <h2 className="mb-2 font-bold">💡 Avec une adresse Gmail</h2>
            <ul className="list-inside list-disc space-y-1 text-gray-700">
              <li>Serveur : <b className="font-mono">smtp.gmail.com</b></li>
              <li>Port : <b>587</b>, STARTTLS coché, SSL décoché</li>
              <li>Utilisateur : votre adresse Gmail complète</li>
              <li>Mot de passe : un <b>mot de passe d'application</b> (Compte Google → Sécurité → Validation en deux étapes → Mots de passe des applications), pas votre mot de passe habituel.</li>
            </ul>
          </div>
        )}

        {/* E-mail de test */}
        <form onSubmit={tester} className="card space-y-3">
          <h2 className="font-bold">✉️ E-mail de test</h2>
          <p className="text-xs text-gray-500">Enregistrez d'abord vos réglages, puis envoyez-vous un e-mail pour vérifier.</p>
          <input className="input" type="email" required value={destinataire} onChange={(e) => setDestinataire(e.target.value)} placeholder="adresse@exemple.com" />
          <button className="btn-outline w-full" disabled={testEnCours}>{testEnCours ? "Envoi en cours…" : "Envoyer un e-mail de test"}</button>
          {test && (
            test.statut === "ENVOYE"
              ? <p className="rounded-xl bg-green-50 p-3 text-sm text-green-800">✔ E-mail envoyé. Vérifiez la boîte de réception (et les indésirables).</p>
              : test.statut === "NON_ENVOYE"
                ? <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Non envoyé : {test.erreur || "la messagerie est désactivée"}.</p>
                : <div className="rounded-xl bg-red-50 p-3 text-sm text-red-800"><p className="font-semibold">✖ Échec de l'envoi</p><p className="mt-1 break-words font-mono text-xs">{test.erreur}</p></div>
          )}
        </form>
      </div>
    </div>
  );
}
