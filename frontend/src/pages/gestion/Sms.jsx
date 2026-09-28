import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { montant } from "@/lib/format";
import EnTetePage from "@/components/EnTetePage";
import JournalContacts from "@/components/JournalSms";
import ClientSelect from "@/components/ClientSelect";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";

// Nombre de SMS pour un texte (même règle que le serveur : 160 caractères,
// 70 si le texte contient un caractère hors de l'alphabet GSM, comme « ê » ou « ç »)
const GSM = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà^{}\\[~]|€";
function nombreSms(texte) {
  if ([...texte].every((c) => GSM.includes(c))) {
    const n = [...texte].reduce((t, c) => t + ("^{}\\[~]|€".includes(c) ? 2 : 1), 0);
    return n <= 160 ? 1 : Math.ceil(n / 153);
  }
  return texte.length <= 70 ? 1 : Math.ceil(texte.length / 67);
}

// Page « SMS » de la boutique : état du service (configuré par adLyn), envoi
// d'un SMS à un client, et journal de tous les envois regroupés par contact.
export default function Sms() {
  const toast = useToast();
  const [etat, setEtat] = useState(null);
  const [form, setForm] = useState({ telephone: "", contact_nom: "", texte: "" });
  const [client, setClient] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const [version, setVersion] = useState(0); // recharge le journal après un envoi

  useEffect(() => {
    apiClient.get("/boutique/sms").then(({ data }) => setEtat(data)).catch((err) => toast.erreur(messageErreur(err, "Service SMS indisponible")));
  }, [toast, version]);

  // Choix d'un client existant : son nom et son numéro sont repris
  function choisirClient(c) {
    setClient(c);
    if (c) setForm((f) => ({ ...f, telephone: c.telephone || "", contact_nom: c.nom }));
  }

  async function envoyer(e) {
    e.preventDefault();
    setEnvoi(true);
    try {
      const { data } = await apiClient.post("/boutique/sms/envoyer", { ...form, texte: form.texte.trim() });
      if (data.statut === "ENVOYE") toast.succes(`SMS envoyé (${data.nb_sms} SMS)`);
      else toast.erreur(`SMS non envoyé : ${data.erreur || data.statut}`);
      setForm({ telephone: "", contact_nom: "", texte: "" });
      setClient(null);
      setVersion((v) => v + 1);
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  if (!etat) return <Chargement />;
  const actif = etat.statut === "ACTIF";
  const nb = form.texte ? nombreSms(form.texte) : 0;

  return (
    <div className="space-y-5">
      <EnTetePage titre="SMS" sousTitre="Messages envoyés à vos clients au nom de votre boutique." />

      {/* État du service et consommation du mois */}
      <div className={`card flex flex-col gap-4 sm:flex-row sm:items-center ${actif ? "" : "border-amber-200 bg-amber-50/60"}`}>
        <div className="min-w-0 flex-1">
          <p className="font-bold">{actif ? "✅" : "⚠️"} {etat.libelle}</p>
          {etat.expediteur && <p className="text-sm text-gray-600">Expéditeur affiché chez vos clients : <b className="font-mono">{etat.expediteur}</b> · {montant(etat.prix_sms)} FCFA par SMS
            {etat.notifications_auto && " · SMS automatiques aux clients (commandes, réparations) activés"}</p>}
          {etat.statut === "SUSPENDU" && <p className="text-sm text-amber-900">Réglez vos factures SMS en retard (page Abonnement adLyn du DG) : le service reprend dès le paiement.</p>}
          {etat.statut === "NON_CONFIGURE" && <p className="text-sm text-gray-600">Contactez l'équipe adLyn pour activer l'envoi de SMS à vos clients.</p>}
        </div>
        {etat.expediteur && (
          <div className="sm:text-right">
            <p className="text-xs text-gray-500">Ce mois-ci (non encore facturé)</p>
            <p className="text-xl font-extrabold">{etat.mois_nb_sms} SMS · {montant(etat.mois_montant)} FCFA</p>
          </div>
        )}
      </div>

      {/* Envoi d'un SMS */}
      {actif && (
        <form onSubmit={envoyer} className="card grid gap-4 sm:grid-cols-2">
          <h2 className="font-bold sm:col-span-2">Envoyer un SMS</h2>
          <div className="sm:col-span-2"><span className="label">Client (facultatif)</span><ClientSelect value={client} onChange={choisirClient} /></div>
          <label className="block"><span className="label">Numéro *</span>
            <input className="input" type="tel" required minLength={8} maxLength={30} value={form.telephone} onChange={(e) => setForm({ ...form, telephone: e.target.value })} placeholder="70 00 00 00" /></label>
          <label className="block"><span className="label">Nom du contact</span>
            <input className="input" maxLength={120} value={form.contact_nom} onChange={(e) => setForm({ ...form, contact_nom: e.target.value })} /></label>
          <label className="block sm:col-span-2"><span className="label">Message *</span>
            <textarea className="input min-h-[100px]" required maxLength={918} value={form.texte} onChange={(e) => setForm({ ...form, texte: e.target.value })} />
            <span className={`mt-1 block text-xs ${nb > 1 ? "text-amber-700" : "text-gray-500"}`}>
              {form.texte.length} caractère(s) · {nb} SMS facturé(s){nb ? ` · ${montant(nb * etat.prix_sms)} FCFA` : ""}
            </span></label>
          <div className="sm:col-span-2 sm:text-right"><button className="btn-primary w-full sm:w-auto" disabled={envoi}>{envoi ? "Envoi…" : "📤 Envoyer"}</button></div>
        </form>
      )}

      {/* Journal par contact */}
      <div className="card">
        <h2 className="mb-3 font-bold">Envois par contact</h2>
        <JournalContacts base="/boutique/sms/contacts" version={version} />
      </div>
    </div>
  );
}
