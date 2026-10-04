import { useEffect, useRef, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure, prix } from "@/lib/format";
import { useToast } from "@/components/Toast";
import Chargement from "@/components/Chargement";
import Patientez from "@/components/Patientez";
import QrCode from "@/components/QrCode";
import { Case, Champ } from "./communs";

// Onglet « Encaissement PI-SPI » des Paramètres (gérant).
// PI-SPI = paiement instantané de la BCEAO. La banque de la boutique fournit un QR code
// STANDARD (il contient l'adresse de paiement, jamais un numéro de téléphone) : on le
// recopie ici (texte décodé) ou on téléverse son image. Il est alors imprimé TEL QUEL sur
// les factures et proformas, avec le montant restant dû et la référence (n° du document).
// Les paiements reçus sont saisis comme règlement « PI-SPI » sur la facture, avec la
// référence bancaire (aucune API bancaire n'est encore disponible : connecteur manuel).
export default function ParamPispi() {
  const toast = useToast();
  const [etat, setEtat] = useState(null);
  const [form, setForm] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [occupe, setOccupe] = useState(false);
  const champImage = useRef(null);

  // Recopie des paramètres reçus du serveur dans le formulaire
  function appliquer(data) {
    setEtat(data);
    setForm({ actif: !!data.actif, banque: data.banque || "UBA", banque_libelle: data.banque_libelle || "",
      titulaire: data.titulaire || "", adresse_paiement: data.adresse_paiement || "",
      qr_contenu: data.qr_contenu || "", consigne: data.consigne || "" });
  }

  // Chargement des paramètres et des derniers encaissements PI-SPI
  useEffect(() => {
    apiClient.get("/boutique/pispi").then(({ data }) => appliquer(data))
      .catch((err) => toast.erreur(messageErreur(err, "Paramètres PI-SPI indisponibles")));
    apiClient.get("/boutique/pispi/transactions").then(({ data }) => setTransactions(data)).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const maj = (champ, valeur) => setForm((f) => ({ ...f, [champ]: valeur }));

  async function enregistrer(e) {
    e.preventDefault();
    setOccupe(true);
    try {
      const { data } = await apiClient.put("/boutique/pispi", form);
      appliquer(data);
      toast.succes("Encaissement PI-SPI enregistré");
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible"));
    } finally {
      setOccupe(false);
    }
  }

  // Image du QR fournie par la banque (PNG / JPG, 1 Mo au plus)
  async function envoyerImage(e) {
    const fichier = e.target.files?.[0];
    e.target.value = "";
    if (!fichier) return;
    if (fichier.size > 1024 * 1024) { toast.erreur("Image trop lourde (1 Mo au maximum)"); return; }
    setOccupe(true);
    try {
      const corps = new FormData();
      corps.append("fichier", fichier);
      const { data } = await apiClient.post("/boutique/pispi/qr-image", corps);
      setEtat(data);
      toast.succes("Image du QR enregistrée");
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi de l'image impossible"));
    } finally {
      setOccupe(false);
    }
  }

  async function retirerImage() {
    setOccupe(true);
    try {
      setEtat((await apiClient.delete("/boutique/pispi/qr-image")).data);
    } catch (err) {
      toast.erreur(messageErreur(err, "Suppression impossible"));
    } finally {
      setOccupe(false);
    }
  }

  if (!etat || !form) return <Chargement />;

  return (
    <div className="space-y-6">
      <Patientez actif={occupe} />
      <form onSubmit={enregistrer} className="card space-y-4">
        <div>
          <h2 className="text-lg font-bold">Encaissement PI-SPI</h2>
          <p className="text-sm text-gray-600">
            Paiement instantané interopérable (BCEAO). Le QR code fourni par votre banque est imprimé sur vos
            factures et proformas, avec le montant restant dû et la référence à indiquer (n° du document).
          </p>
        </div>
        <Case label="Afficher « Payer par PI-SPI » sur les factures et proformas" checked={form.actif} onChange={(v) => maj("actif", v)}
          aide="Le QR (texte ou image) est obligatoire pour activer." />
        <div className="grid gap-4 md:grid-cols-2">
          <Champ label="Banque">
            <select className="input" value={form.banque} onChange={(e) => maj("banque", e.target.value)}>
              {etat.banques.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </Champ>
          {form.banque === "Autre" && (
            <Champ label="Nom de la banque"><input className="input" maxLength={80} value={form.banque_libelle} onChange={(e) => maj("banque_libelle", e.target.value)} /></Champ>
          )}
          <Champ label="Titulaire (nom affiché)"><input className="input" maxLength={120} value={form.titulaire} onChange={(e) => maj("titulaire", e.target.value)} /></Champ>
          <Champ label="Adresse de paiement PI-SPI (alias)" aide="Telle que fournie par votre banque.">
            <input className="input" maxLength={200} value={form.adresse_paiement} onChange={(e) => maj("adresse_paiement", e.target.value)} />
          </Champ>
        </div>
        <Champ label="Contenu du QR code (texte décodé, facultatif)"
          aide="Recopiez exactement le texte du QR fourni par la banque : il est réimprimé tel quel, sans aucune modification. Sinon, téléversez l'image ci-dessous.">
          <textarea className="input min-h-[80px] font-mono text-xs" maxLength={1500} value={form.qr_contenu} onChange={(e) => maj("qr_contenu", e.target.value)} />
        </Champ>
        <div className="flex flex-wrap items-center gap-3">
          <input ref={champImage} type="file" accept="image/png,image/jpeg" className="hidden" onChange={envoyerImage} />
          <button type="button" className="btn-outline btn-sm" onClick={() => champImage.current?.click()}>🖼 Téléverser l'image du QR (PNG/JPG, 1 Mo)</button>
          {etat.qr_image_url && <button type="button" className="btn-outline btn-sm text-red-600" onClick={retirerImage}>Retirer l'image</button>}
        </div>
        <Champ label="Consigne imprimée sous le QR" aide={`Vide = « ${etat.consigne_defaut} »`}>
          <input className="input" maxLength={300} value={form.consigne} onChange={(e) => maj("consigne", e.target.value)} />
        </Champ>

        {/* Aperçu de ce qui sera imprimé */}
        {(etat.qr_image_url || form.qr_contenu) && (
          <div className="flex items-center gap-4 rounded-xl border border-gray-200 p-3">
            {etat.qr_image_url
              ? <img src={etat.qr_image_url} alt="QR PI-SPI" className="h-28 w-28 object-contain" />
              : <QrCode valeur={form.qr_contenu} taille={112} />}
            <div className="text-sm text-gray-700">
              <p className="font-bold">Aperçu « Payer par PI-SPI »</p>
              {form.adresse_paiement && <p>Adresse : {form.adresse_paiement}</p>}
              <p>{[form.titulaire, form.banque === "Autre" ? form.banque_libelle : form.banque].filter(Boolean).join(" · ")}</p>
              <p className="text-xs text-gray-500">+ montant restant dû et référence du document, à l'impression</p>
            </div>
          </div>
        )}
        <p className="text-xs text-gray-500">
          Encaissement : {etat.connecteur?.libelle}. Quand un paiement arrive sur votre compte, enregistrez-le sur la facture
          (mode « PI-SPI », avec la référence bancaire).
        </p>
        <button type="submit" className="btn-primary" disabled={occupe}>Enregistrer</button>
      </form>

      {/* Derniers encaissements PI-SPI saisis */}
      <section className="card overflow-x-auto p-0">
        <h3 className="p-4 font-bold">Encaissements PI-SPI</h3>
        {transactions.length === 0 ? <p className="px-4 pb-4 text-sm text-gray-500">Aucun encaissement PI-SPI enregistré.</p> : (
          <table className="table">
            <thead><tr><th>Date</th><th>Référence</th><th>Réf. bancaire</th><th className="text-right">Montant</th><th>Statut</th></tr></thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.id}>
                  <td>{dateHeure(t.date)}</td><td>{t.reference}</td><td>{t.reference_bancaire}</td>
                  <td className="text-right">{prix(t.montant)}</td>
                  <td>{{ rapproche: "Rapproché", rejete: "Rejeté", attendu: "Attendu", recu: "Reçu" }[t.statut] || t.statut}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
