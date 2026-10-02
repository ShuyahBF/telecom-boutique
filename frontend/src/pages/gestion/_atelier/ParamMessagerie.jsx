import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Case, Champ } from "./communs";
import ChampMotDePasse from "@/components/ChampMotDePasse";

// Onglet « Messagerie (e-mails) » : réglages du serveur d'envoi (SMTP)
// et envoi d'un e-mail de test.
export default function ParamMessagerie() {
  const { user, boutique, setBoutique } = useAuth();
  const toast = useToast();
  const actuel = boutique.messagerie || {};

  // Réglages modifiables. Le mot de passe n'est jamais renvoyé par l'API :
  // le champ reste vide, et vide = « garder le mot de passe enregistré ».
  const [reglages, setReglages] = useState({
    email_actif: !!actuel.email_actif, smtp_hote: actuel.smtp_hote || "", smtp_port: actuel.smtp_port || 587,
    smtp_utilisateur: actuel.smtp_utilisateur || "", smtp_mot_de_passe: "", smtp_tls: actuel.smtp_tls ?? true,
    smtp_ssl: !!actuel.smtp_ssl, expediteur_nom: actuel.expediteur_nom || "", expediteur_email: actuel.expediteur_email || "",
    email_equipe: actuel.email_equipe || "",
  });
  const [envoi, setEnvoi] = useState(false);
  const [destinataire, setDestinataire] = useState(boutique.email || user.email || "");
  const [test, setTest] = useState(null); // résultat du dernier e-mail de test
  const [testEnCours, setTestEnCours] = useState(false);
  const maj = (champ, valeur) => setReglages((r) => ({ ...r, [champ]: valeur }));

  // Enregistrement des réglages (PUT /boutique/messagerie)
  async function enregistrer(e) {
    e.preventDefault();
    setEnvoi(true);
    try {
      const { data } = await apiClient.put("/boutique/messagerie", {
        ...reglages, smtp_port: Number(reglages.smtp_port) || 587,
        smtp_mot_de_passe: reglages.smtp_mot_de_passe || null,
        expediteur_email: reglages.expediteur_email || null, email_equipe: reglages.email_equipe || null,
      });
      setBoutique({ ...boutique, messagerie: data });
      maj("smtp_mot_de_passe", "");
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
        <h2 className="font-bold sm:col-span-2">Serveur d'envoi (SMTP)</h2>
        <div className="sm:col-span-2"><Case label="Envoyer des e-mails aux clients et à l'équipe" aide="Confirmations de commande, avancement des réparations, réponses aux demandes de conseil…" checked={reglages.email_actif} onChange={(v) => maj("email_actif", v)} /></div>
        <Champ label="Serveur SMTP"><input className="input" maxLength={150} value={reglages.smtp_hote} onChange={(e) => maj("smtp_hote", e.target.value)} placeholder="smtp.gmail.com" /></Champ>
        <Champ label="Port"><input className="input" type="number" min={1} max={65535} value={reglages.smtp_port} onChange={(e) => maj("smtp_port", e.target.value)} /></Champ>
        <Champ label="Utilisateur"><input className="input" maxLength={150} autoComplete="off" value={reglages.smtp_utilisateur} onChange={(e) => maj("smtp_utilisateur", e.target.value)} placeholder="votre.adresse@gmail.com" /></Champ>
        <Champ label="Mot de passe" aide={actuel.a_mot_de_passe ? "✔ Mot de passe enregistré. Laissez vide pour le conserver." : "Aucun mot de passe enregistré."}>
          <ChampMotDePasse maxLength={150} autoComplete="new-password" value={reglages.smtp_mot_de_passe}
            onChange={(e) => maj("smtp_mot_de_passe", e.target.value)} placeholder={actuel.a_mot_de_passe ? "•••••••• (inchangé)" : ""} />
        </Champ>
        <Case label="STARTTLS (port 587)" checked={reglages.smtp_tls} onChange={(v) => maj("smtp_tls", v)} />
        <Case label="SSL direct (port 465)" checked={reglages.smtp_ssl} onChange={(v) => maj("smtp_ssl", v)} />
        <Champ label="Nom de l'expéditeur"><input className="input" maxLength={100} value={reglages.expediteur_nom} onChange={(e) => maj("expediteur_nom", e.target.value)} /></Champ>
        <Champ label="Adresse de l'expéditeur"><input className="input" type="email" value={reglages.expediteur_email} onChange={(e) => maj("expediteur_email", e.target.value)} /></Champ>
        <Champ label="E-mail de l'équipe" aide="Reçoit les alertes : nouvelle commande, nouvelle demande de conseil." className="sm:col-span-2">
          <input className="input" type="email" value={reglages.email_equipe} onChange={(e) => maj("email_equipe", e.target.value)} />
        </Champ>
        <button className="btn-primary sm:col-span-2 sm:justify-self-start" disabled={envoi}>{envoi ? "Enregistrement…" : "💾 Enregistrer les réglages"}</button>
      </form>

      <div className="space-y-5">
        {/* Aide pour Gmail */}
        <div className="card text-sm">
          <h2 className="mb-2 font-bold">💡 Avec une adresse Gmail</h2>
          <ul className="list-inside list-disc space-y-1 text-gray-700">
            <li>Serveur : <b className="font-mono">smtp.gmail.com</b></li>
            <li>Port : <b>587</b>, STARTTLS coché, SSL décoché</li>
            <li>Utilisateur : votre adresse Gmail complète</li>
            <li>Mot de passe : un <b>mot de passe d'application</b> (Compte Google → Sécurité → Validation en deux étapes → Mots de passe des applications), pas votre mot de passe habituel.</li>
          </ul>
        </div>

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
                ? <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Non envoyé : la messagerie est désactivée ou le serveur SMTP n'est pas renseigné.</p>
                : <div className="rounded-xl bg-red-50 p-3 text-sm text-red-800"><p className="font-semibold">✖ Échec de l'envoi</p><p className="mt-1 break-words font-mono text-xs">{test.erreur}</p></div>
          )}
        </form>
      </div>
    </div>
  );
}
