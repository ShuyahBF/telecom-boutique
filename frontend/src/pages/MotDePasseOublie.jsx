import { useState } from "react";
import { Link } from "react-router-dom";
import { LogoAdlyn } from "@/components/Marque";
import { apiClient, idBoutiqueMemorise, messageErreur } from "@/lib/api";
import ChampMotDePasse from "@/components/ChampMotDePasse";
import { AvisMaintenance } from "@/components/MaintenancePlateforme";

// « Mot de passe oublié ? » (personnel des boutiques), en 2 étapes :
//   1. ID boutique + e-mail ou téléphone -> un code à 6 chiffres est envoyé
//      par WhatsApp (sinon par SMS, ou par e-mail si le compte n'a qu'un e-mail) ;
//   2. code reçu + nouveau mot de passe.
// Le serveur répond la même chose que le compte existe ou non : on ne dit
// jamais « ce compte n'existe pas ». Le code n'est jamais affiché ici.
export default function MotDePasseOublie() {
  const [etape, setEtape] = useState("demande"); // demande | code | termine
  const [codeBoutique, setCodeBoutique] = useState(idBoutiqueMemorise);
  const [identifiant, setIdentifiant] = useState("");
  const [form, setForm] = useState({ code: "", nouveau: "", confirmation: "" });
  const [info, setInfo] = useState("");
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(false);

  const saisirCodeBoutique = (v) => setCodeBoutique(v.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6));

  // Étape 1 : demande du code
  async function demander(e) {
    e?.preventDefault();
    setErreur("");
    if (codeBoutique.length !== 6) return setErreur("L'ID boutique contient 6 lettres ou chiffres.");
    setEnvoi(true);
    try {
      const { data } = await apiClient.post("/auth/mot-de-passe-oublie", { code_boutique: codeBoutique, identifiant: identifiant.trim() });
      setInfo(data.message);
      setEtape("code");
    } catch (err) {
      setErreur(messageErreur(err, "Demande impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  // Étape 2 : code + nouveau mot de passe
  async function confirmer(e) {
    e.preventDefault();
    setErreur("");
    if (!/^\d{6}$/.test(form.code.trim())) return setErreur("Le code contient 6 chiffres.");
    if (form.nouveau.length < 8) return setErreur("Le nouveau mot de passe doit contenir au moins 8 caractères.");
    if (form.nouveau !== form.confirmation) return setErreur("Les deux saisies du nouveau mot de passe sont différentes.");
    setEnvoi(true);
    try {
      await apiClient.post("/auth/mot-de-passe-oublie/confirmer", {
        code_boutique: codeBoutique, identifiant: identifiant.trim(), code: form.code.trim(), nouveau: form.nouveau,
      });
      setEtape("termine");
    } catch (err) {
      setErreur(messageErreur(err, "Code incorrect ou expiré"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-nuit-900 p-4">
      <div className="pointer-events-none absolute -right-40 -top-40 h-[30rem] w-[30rem] rounded-full bg-primary/20 blur-3xl" />
      <div className="relative w-full max-w-sm space-y-4 rounded-2xl border border-white/10 bg-white p-8 shadow-2xl">
        <div className="text-center">
          <LogoAdlyn className="mx-auto h-12" />
          <h1 className="mt-3 text-xl font-bold">Mot de passe oublié</h1>
          <p className="text-sm text-gray-500">
            {etape === "demande" && "Recevez un code sur WhatsApp (ou par SMS / e-mail) pour choisir un nouveau mot de passe."}
            {etape === "code" && info}
            {etape === "termine" && "C'est fait ! Toutes vos anciennes sessions ont été fermées."}
          </p>
        </div>
        {/* Maintenance de la plateforme : demande de code refusée pendant la maintenance */}
        <AvisMaintenance />

        {etape === "demande" && (
          <form onSubmit={demander} className="space-y-4">
            <div>
              <label className="label" htmlFor="code-boutique">ID boutique</label>
              <input id="code-boutique" className="input text-center font-mono text-lg tracking-[0.4em] uppercase" required
                placeholder="K7M2QD" maxLength={6} value={codeBoutique} onChange={(e) => saisirCodeBoutique(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="identifiant">E-mail ou téléphone de votre compte</label>
              <input id="identifiant" className="input" required autoComplete="username" placeholder="vous@exemple.com ou 70 12 34 56"
                value={identifiant} onChange={(e) => setIdentifiant(e.target.value)} />
            </div>
            {erreur && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{erreur}</p>}
            <button className="btn-primary w-full" disabled={envoi}>{envoi ? "Envoi…" : "Recevoir un code"}</button>
          </form>
        )}

        {etape === "code" && (
          <form onSubmit={confirmer} className="space-y-4">
            <div>
              <label className="label" htmlFor="code">Code reçu (6 chiffres)</label>
              <ChampMotDePasse id="code" className="input text-center font-mono text-2xl tracking-[0.5em]" required inputMode="numeric"
                autoComplete="one-time-code" maxLength={6} value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value.replace(/\D/g, "").slice(0, 6) })} />
            </div>
            <div><label className="label" htmlFor="nouveau">Nouveau mot de passe (8 caractères minimum)</label>
              <ChampMotDePasse id="nouveau" required autoComplete="new-password"
                value={form.nouveau} onChange={(e) => setForm({ ...form, nouveau: e.target.value })} /></div>
            <div><label className="label" htmlFor="confirmation">Nouveau mot de passe, encore une fois</label>
              <ChampMotDePasse id="confirmation" required autoComplete="new-password"
                value={form.confirmation} onChange={(e) => setForm({ ...form, confirmation: e.target.value })} /></div>
            {erreur && <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{erreur}</p>}
            <button className="btn-primary w-full" disabled={envoi}>{envoi ? "Enregistrement…" : "Changer mon mot de passe"}</button>
            <p className="text-center text-xs text-gray-500">
              Rien reçu après une minute ?{" "}
              <button type="button" className="font-semibold text-primary" disabled={envoi} onClick={() => demander()}>Renvoyer un code</button>
              {" "}— ou demandez au DG de votre boutique un mot de passe provisoire.
            </p>
          </form>
        )}

        {etape === "termine" && (
          <Link to="/connexion" className="btn-primary block w-full text-center">Se connecter →</Link>
        )}

        {etape !== "termine" && (
          <div className="text-center text-sm"><Link to="/connexion" className="text-primary">← Retour à la connexion</Link></div>
        )}
      </div>
    </div>
  );
}
