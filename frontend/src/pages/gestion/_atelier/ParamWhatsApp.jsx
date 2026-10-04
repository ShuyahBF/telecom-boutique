import { useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { dateHeure } from "@/lib/format";
import Chargement from "@/components/Chargement";
import Patientez from "@/components/Patientez";
import ChampMotDePasse from "@/components/ChampMotDePasse";
import { Case, Champ } from "./communs";

// Jeton masqué renvoyé par le serveur : le jeton n'est JAMAIS renvoyé en clair
const JETON_MASQUE = "********";

// Libellés des canaux d'envoi WhatsApp (ordre de priorité de la Transmission WA)
const CANAUX = {
  waba_boutique: "✅ Votre propre numéro WhatsApp Business (ce réglage)",
  waba_plateforme: "Numéro WhatsApp de la plateforme adLyn",
  liluvine: "Transmission WA Universelle (Liluvine), au nom de votre boutique",
};

// Onglet « WhatsApp » des Paramètres : le gérant (ou le super-administrateur qui
// consulte la boutique) saisit le compte WhatsApp Business (WABA) PROPRE à sa
// boutique. S'il est actif, tous les WhatsApp de la boutique partent de SON numéro ;
// sinon, celui de la plateforme, sinon la Transmission WA Universelle (Liluvine).
export default function ParamWhatsApp() {
  const toast = useToast();
  const [etat, setEtat] = useState(null); // réglage enregistré (jeton masqué)
  const [form, setForm] = useState({ phone_number_id: "", access_token: "", actif: true });
  const [occupe, setOccupe] = useState(false); // enregistrement ou test en cours
  const [numeroTest, setNumeroTest] = useState("");
  const [test, setTest] = useState(null); // résultat du dernier test

  // Recopie le réglage reçu dans le formulaire (jeton : le masque « ******** »)
  const appliquer = (data) => {
    setEtat(data);
    setForm({ phone_number_id: data.phone_number_id || "", access_token: data.access_token || "", actif: data.actif });
  };

  // Chargement du réglage à l'ouverture de l'onglet
  useEffect(() => {
    apiClient.get("/boutique/whatsapp-waba").then(({ data }) => appliquer(data))
      .catch((err) => toast.erreur(messageErreur(err, "Réglage WhatsApp indisponible")));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const maj = (champ, valeur) => setForm((f) => ({ ...f, [champ]: valeur }));

  // Enregistrement : jeton vide ou masque = jeton enregistré conservé (côté serveur)
  async function enregistrer(e) {
    e.preventDefault();
    setOccupe(true);
    try {
      const jeton = form.access_token === JETON_MASQUE ? null : form.access_token.trim() || null;
      const { data } = await apiClient.put("/boutique/whatsapp-waba", { ...form, phone_number_id: form.phone_number_id.trim(), access_token: jeton });
      appliquer(data);
      setTest(null);
      toast.succes("Réglage WhatsApp enregistré");
    } catch (err) {
      toast.erreur(messageErreur(err, "Vérifiez l'identifiant du numéro (chiffres) et le jeton"));
    } finally {
      setOccupe(false);
    }
  }

  // Suppression du réglage : la boutique revient au canal suivant
  async function supprimer() {
    if (!window.confirm("Supprimer le compte WhatsApp Business de la boutique ?")) return;
    setOccupe(true);
    try {
      const { data } = await apiClient.delete("/boutique/whatsapp-waba");
      appliquer(data);
      setTest(null);
      toast.succes("Réglage WhatsApp supprimé");
    } catch (err) {
      toast.erreur(messageErreur(err, "Suppression impossible"));
    } finally {
      setOccupe(false);
    }
  }

  // Bouton « Tester » : vérifie le compte chez Meta (et envoie un message si un numéro est saisi)
  async function tester() {
    setOccupe(true);
    setTest(null);
    try {
      const { data } = await apiClient.post("/boutique/whatsapp-waba/tester", { numero: numeroTest.trim() || null }, { timeout: 60000 });
      setTest(data);
    } catch (err) {
      setTest({ ok: false, verification: { ok: false, erreur: messageErreur(err, "Test impossible") } });
    } finally {
      setOccupe(false);
    }
  }

  if (!etat) return <Chargement />;

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <Patientez actif={occupe} />
      <form onSubmit={enregistrer} className="card grid gap-4 sm:grid-cols-2 lg:col-span-2">
        <h2 className="font-bold sm:col-span-2">💬 Compte WhatsApp Business de la boutique</h2>
        <p className="text-sm text-gray-600 sm:col-span-2">
          Facultatif. Avec votre propre compte WhatsApp Business (Meta), les messages de la boutique partent de
          <b> votre numéro</b>. Sans ce réglage, ils partent du numéro de la plateforme ou, à défaut, de la Transmission
          WA Universelle, au nom de votre boutique.
        </p>

        {/* Identifiant du numéro chez Meta (Business Manager > WhatsApp > Configuration de l'API) */}
        <Champ label="Identifiant du numéro (phone number ID)" aide="Chiffres uniquement, affichés dans la configuration de l'API WhatsApp de Meta.">
          <input className="input font-mono" inputMode="numeric" maxLength={30} required value={form.phone_number_id}
            onChange={(e) => maj("phone_number_id", e.target.value.replace(/\D/g, ""))} placeholder="123456789012345" />
        </Champ>

        {/* Jeton d'accès : chiffré en base, jamais réaffiché (masque « ******** ») */}
        <Champ label="Jeton d'accès (access token)"
          aide={etat.a_jeton ? "✔ Jeton enregistré. Laissez « ******** » pour le conserver." : "Jeton permanent d'un utilisateur système."}>
          <ChampMotDePasse maxLength={1000} autoComplete="new-password" value={form.access_token}
            onChange={(e) => maj("access_token", e.target.value)} placeholder={etat.a_jeton ? JETON_MASQUE : "Collez le jeton d'accès"} />
        </Champ>

        <div className="sm:col-span-2">
          <Case label="Utiliser ce compte pour les WhatsApp de la boutique" checked={form.actif} onChange={(v) => maj("actif", v)}
            aide="Décoché : le réglage est gardé, mais les messages passent par le canal suivant." />
        </div>

        {/* Canal réellement utilisé aujourd'hui */}
        <p className="rounded-xl bg-gray-50 p-3 text-sm sm:col-span-2">
          Canal utilisé actuellement : <b>{CANAUX[etat.canal_prevu] || "aucun (WhatsApp non branché)"}</b>
          {etat.modifie_le && <span className="block text-xs text-gray-500">Modifié le {dateHeure(etat.modifie_le)}{etat.modifie_par ? ` par ${etat.modifie_par}` : ""}</span>}
        </p>

        <div className="flex flex-wrap gap-2 sm:col-span-2">
          <button className="btn-primary" disabled={occupe}>💾 Enregistrer</button>
          {etat.a_jeton && <button type="button" className="btn-outline" disabled={occupe} onClick={supprimer}>🗑️ Supprimer</button>}
        </div>
      </form>

      {/* Test du compte enregistré */}
      <div className="card space-y-3">
        <h2 className="font-bold">🧪 Tester</h2>
        <p className="text-xs text-gray-500">
          Enregistrez d'abord, puis testez : adLyn vérifie l'identifiant et le jeton auprès de Meta. Si vous indiquez un numéro,
          un message de test lui est envoyé (il ne passe que si ce numéro a écrit à la boutique dans les dernières 24 h).
        </p>
        <input className="input" type="tel" value={numeroTest} onChange={(e) => setNumeroTest(e.target.value)} placeholder="+226 70 00 00 00 (facultatif)" />
        <button type="button" className="btn-outline w-full" disabled={occupe || !etat.a_jeton} onClick={tester}>Tester</button>
        {test && (
          test.ok ? (
            <p className="rounded-xl bg-green-50 p-3 text-sm text-green-800">
              ✔ Compte valide{test.verification?.numero_affiche ? ` : ${test.verification.numero_affiche}` : ""}
              {test.verification?.nom_verifie ? ` (${test.verification.nom_verifie})` : ""}.
              {test.envoi && " Message de test envoyé."}
            </p>
          ) : (
            <div className="rounded-xl bg-red-50 p-3 text-sm text-red-800">
              <p className="font-semibold">✖ Échec du test</p>
              <p className="mt-1 break-words font-mono text-xs">{test.envoi?.erreur || test.verification?.erreur}</p>
            </div>
          )
        )}
      </div>
    </div>
  );
}
