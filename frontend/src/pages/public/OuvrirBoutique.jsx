import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { LogoAdlyn } from "@/components/Marque";
import PoweredBySawali from "@/components/PoweredBySawali";

// Page publique « Ouvrir ma boutique » : on y arrive UNIQUEMENT par le lien
// d'invitation d'une boutique marraine (?parrain=<ID boutique>).
// L'invité accepte l'invitation, puis sa demande crée une boutique EN ATTENTE :
// l'équipe adLyn la vérifie avant de l'ouvrir (le parrain reçoit alors son bonus).
export default function OuvrirBoutique() {
  const [params] = useSearchParams();
  const code = (params.get("parrain") || "").trim();
  const [parrain, setParrain] = useState(undefined); // undefined = chargement, null = lien invalide
  const [form, setForm] = useState({ nom: "", ville: "", pays: "Burkina Faso", telephone: "", dg_nom: "",
    dg_email: "", dg_telephone: "", accepte_invitation: false, accepte_conditions: false });
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [resultat, setResultat] = useState(null);

  useEffect(() => {
    document.title = "adLyn";
    if (!code) { setParrain(null); return; }
    apiClient.get(`/public/parrainage/${encodeURIComponent(code)}`)
      .then(({ data }) => setParrain(data.parrain)).catch(() => setParrain(null));
  }, [code]);

  const champ = (cle) => (e) => setForm({ ...form, [cle]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const envoyer = async (e) => {
    e.preventDefault();
    setErreur("");
    setEnvoi(true);
    try {
      const { data } = await apiClient.post(`/public/parrainage/${encodeURIComponent(code)}/demande`, form);
      setResultat(data);
    } catch (err) {
      setErreur(messageErreur(err, "Demande impossible pour le moment"));
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center bg-nuit-900 px-4 py-10">
      <Link to="/" aria-label="adLyn, accueil"><LogoAdlyn clair className="h-10" /></Link>
      <div className="mt-6 w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl sm:p-8">
        {parrain === undefined && <p className="text-center text-gray-500">Chargement…</p>}

        {parrain === null && (
          <div className="space-y-3 text-center">
            <h1 className="text-xl font-bold">Lien d'invitation invalide</h1>
            <p className="text-sm text-gray-600">Demandez à la boutique qui vous invite de vous renvoyer son lien de parrainage.</p>
            <Link to="/" className="btn-outline">← Retour à l'accueil</Link>
          </div>
        )}

        {parrain && resultat && (
          <div className="space-y-3 text-center">
            <p className="text-4xl" aria-hidden="true">🎉</p>
            <h1 className="text-xl font-bold">Demande enregistrée</h1>
            <p className="text-sm text-gray-600">
              Votre boutique est créée et <b>en attente de vérification</b> par l'équipe adLyn. Vos identifiants ont été
              envoyés par e-mail{resultat.identifiants_envoyes?.sms ? " et par SMS" : ""}. Votre ID boutique : <b className="font-mono">{resultat.code_boutique}</b>.
            </p>
            <Link to="/connexion" className="btn-primary">Me connecter →</Link>
          </div>
        )}

        {parrain && !resultat && (
          <form onSubmit={envoyer} className="space-y-4">
            <div className="rounded-xl bg-blue-50 p-4 text-sm text-blue-900">
              <p className="surtitre">Invitation</p>
              <p className="mt-1"><b>{parrain.nom}</b>{parrain.ville ? ` (${parrain.ville})` : ""} vous invite à ouvrir votre boutique de téléphonie sur adLyn : vitrine en ligne, commandes, stock et réparations. 14 jours d'essai gratuit.</p>
            </div>
            <h1 className="text-xl font-bold">Ouvrir ma boutique</h1>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2"><label className="label" htmlFor="nom">Nom de la boutique</label>
                <input id="nom" className="input" required minLength={3} value={form.nom} onChange={champ("nom")} /></div>
              <div><label className="label" htmlFor="ville">Ville</label>
                <input id="ville" className="input" required value={form.ville} onChange={champ("ville")} /></div>
              <div><label className="label" htmlFor="pays">Pays</label>
                <input id="pays" className="input" required value={form.pays} onChange={champ("pays")} /></div>
              <div className="sm:col-span-2"><label className="label" htmlFor="tel">Téléphone de la boutique <span className="font-normal text-gray-400">(facultatif)</span></label>
                <input id="tel" className="input" type="tel" value={form.telephone} onChange={champ("telephone")} /></div>
              <div className="sm:col-span-2"><label className="label" htmlFor="dg">Nom du gérant (DG)</label>
                <input id="dg" className="input" required minLength={3} value={form.dg_nom} onChange={champ("dg_nom")} /></div>
              <div><label className="label" htmlFor="dgmail">E-mail du DG</label>
                <input id="dgmail" className="input" type="email" required value={form.dg_email} onChange={champ("dg_email")} /></div>
              <div><label className="label" htmlFor="dgtel">Téléphone du DG</label>
                <input id="dgtel" className="input" type="tel" required placeholder="70 00 00 00" value={form.dg_telephone} onChange={champ("dg_telephone")} /></div>
            </div>

            {/* Acceptation de l'invitation : condition du bonus de la boutique marraine */}
            <label className="flex items-start gap-3 rounded-xl border border-gray-200 p-3 text-sm">
              <input type="checkbox" className="mt-0.5 h-4 w-4" checked={form.accepte_invitation} onChange={champ("accepte_invitation")} />
              <span>J'accepte l'invitation de <b>{parrain.nom}</b>, qui devient ma boutique marraine sur adLyn.</span>
            </label>
            <label className="flex items-start gap-3 rounded-xl border border-gray-200 p-3 text-sm">
              <input type="checkbox" className="mt-0.5 h-4 w-4" checked={form.accepte_conditions} onChange={champ("accepte_conditions")} />
              <span>J'accepte les <Link to="/conditions" className="text-primary underline">conditions d'utilisation</Link> et la{" "}
                <Link to="/confidentialite" className="text-primary underline">politique de confidentialité</Link> d'adLyn.</span>
            </label>

            {erreur && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{erreur}</p>}
            <button type="submit" className="btn-primary w-full py-3" disabled={envoi || !form.accepte_invitation || !form.accepte_conditions}>
              {envoi ? "Envoi…" : "Demander l'ouverture de ma boutique"}
            </button>
            <p className="text-center text-xs text-gray-500">L'équipe adLyn vérifie chaque boutique avant de l'ouvrir au public (pièces d'identité, IFU, RCCM demandés ensuite).</p>
          </form>
        )}
      </div>
      <PoweredBySawali className="mt-6" />
    </div>
  );
}
