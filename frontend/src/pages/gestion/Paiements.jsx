import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { peut, useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, dateHeure, montant, prix } from "@/lib/format";
import Chargement from "@/components/Chargement";
import EnTetePage from "@/components/EnTetePage";
import { useToast } from "@/components/Toast";
import ListePaiements from "./_paiements/ListePaiements";
import { bornesPeriode, CANAUX, PERIODES, STATUTS_DEFAUT } from "./_paiements/outils";

// Page « Historique des paiements » (DG et comptable) : TOUS les paiements de
// la boutique, réussis ou non — paiements Mobile Money en ligne (PawaPay) et
// règlements saisis en caisse (espèces, Orange Money, Moov Money, carte,
// virement, chèque) — avec totaux, export tableur et impression.
export default function Paiements() {
  const { user, boutique } = useAuth();
  const toast = useToast();
  const devise = boutique?.devise || "FCFA";

  // --- Filtres, gardés dans l'adresse (?periode=mois&statut=ECHEC…) ---
  // Avantage : un rechargement ou un lien partagé retrouve exactement la même vue.
  const [params, setParams] = useSearchParams();
  const periode = PERIODES.some((p) => p.code === params.get("periode")) ? params.get("periode") : "mois";
  const { du, au } = bornesPeriode(periode, params.get("du"), params.get("au"));
  const statut = params.get("statut") || "";
  const canal = params.get("canal") || "";
  const mode = params.get("mode") || "";

  // Modifie un ou plusieurs filtres (une valeur vide retire le filtre de l'adresse)
  function changerFiltres(changements) {
    const suivants = new URLSearchParams(params);
    Object.entries(changements).forEach(([cle, valeur]) => (valeur ? suivants.set(cle, valeur) : suivants.delete(cle)));
    // Les dates ne sont gardées dans l'adresse que pour la période personnalisée
    if (suivants.get("periode") !== "perso") {
      suivants.delete("du");
      suivants.delete("au");
    }
    setParams(suivants, { replace: true });
  }

  // Choix d'un raccourci de période. « Personnalisée » part des dates affichées.
  function choisirPeriode(code) {
    changerFiltres(code === "perso" ? { periode: "perso", du, au } : { periode: code });
  }

  // --- Chargement des paiements à chaque changement de filtre ---
  const [donnees, setDonnees] = useState(null);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [exportEnCours, setExportEnCours] = useState(false);

  useEffect(() => {
    let annule = false; // évite d'afficher une réponse arrivée trop tard (filtre déjà changé)
    setChargement(true);
    apiClient.get("/journal-paiements", { params: { du, au, statut, canal, mode } })
      .then(({ data }) => { if (!annule) { setDonnees(data); setErreur(""); } })
      .catch((err) => { if (!annule) setErreur(messageErreur(err, "Impossible de charger l'historique des paiements")); })
      .finally(() => { if (!annule) setChargement(false); });
    return () => { annule = true; };
  }, [du, au, statut, canal, mode]);

  // --- Export tableur : le fichier CSV est protégé, on le télécharge avec le jeton ---
  async function exporter() {
    setExportEnCours(true);
    try {
      const { data } = await apiClient.get("/journal-paiements/export.csv", {
        params: { du, au, statut, canal, mode }, responseType: "blob",
      });
      // Lien de téléchargement invisible, cliqué par programme puis retiré
      const url = URL.createObjectURL(data);
      const lien = document.createElement("a");
      lien.href = url;
      lien.download = `paiements_${boutique.code_marchand}_${du}_${au}.csv`;
      document.body.appendChild(lien);
      lien.click();
      lien.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (err) {
      toast.erreur(messageErreur(err, "Export impossible"));
    } finally {
      setExportEnCours(false);
    }
  }

  // Valeurs d'affichage (les libellés viennent du serveur quand ils sont arrivés)
  const statuts = donnees?.statuts || STATUTS_DEFAUT;
  const modes = donnees?.modes || {};
  const parStatut = donnees?.par_statut || {};
  const nb = (s) => parStatut[s]?.nombre || 0;
  const somme = (s) => parStatut[s]?.montant || 0;
  const libellePeriode = PERIODES.find((p) => p.code === periode)?.libelle;
  const filtresActifs = [
    statut && `statut « ${statuts[statut] || statut} »`,
    canal && `canal « ${CANAUX[canal] || canal} »`,
    mode && `mode « ${modes[mode] || mode} »`,
  ].filter(Boolean);

  // Tuiles de synthèse de la période
  const tuiles = [
    { libelle: "Total encaissé", valeur: prix(donnees?.total_encaisse || 0, devise), detail: "paiements réussis", couleur: "text-green-700", fond: "border-green-200 bg-green-50" },
    { libelle: "Réussis", valeur: nb("SUCCES"), detail: "paiement(s)", couleur: "text-ink" },
    { libelle: "Échoués", valeur: nb("ECHEC"), detail: `${prix(somme("ECHEC"), devise)} non encaissés`, couleur: nb("ECHEC") ? "text-red-600" : "text-ink" },
    { libelle: "En attente", valeur: nb("EN_ATTENTE"), detail: prix(somme("EN_ATTENTE"), devise), couleur: nb("EN_ATTENTE") ? "text-amber-700" : "text-ink" },
    { libelle: "Annulés", valeur: nb("ANNULE"), detail: prix(somme("ANNULE"), devise), couleur: "text-gray-600" },
  ];

  // Encaissé par mode, du plus gros au plus petit montant
  const parMode = Object.entries(donnees?.encaisse_par_mode || {}).sort((a, b) => b[1].montant - a[1].montant);

  return (
    <div>
      {/* En-tête imprimé seulement : identité de la boutique et période du rapport */}
      <div className="mb-4 hidden border-b border-gray-300 pb-3 print:block">
        <div className="flex items-center gap-3">
          {boutique.logo_url && <img src={boutique.logo_url} alt="" className="h-12 w-12 object-contain" />}
          <div>
            <p className="text-lg font-extrabold">{boutique.nom}</p>
            <p className="text-xs text-gray-600">
              Code marchand {boutique.code_marchand}
              {boutique.ifu ? ` · IFU ${boutique.ifu}` : ""}{boutique.rccm ? ` · RCCM ${boutique.rccm}` : ""}
            </p>
            <p className="text-xs text-gray-600">{[boutique.adresse, boutique.ville, boutique.telephone].filter(Boolean).join(" · ")}</p>
          </div>
        </div>
        <h1 className="mt-3 text-xl font-extrabold">Rapport des paiements du {date(du)} au {date(au)}</h1>
        <p className="text-xs text-gray-600">
          {filtresActifs.length ? `Filtres : ${filtresActifs.join(", ")}. ` : "Tous les paiements. "}
          Édité le {dateHeure(new Date().toISOString())} par {user.nom}.
        </p>
      </div>

      {/* En-tête écran avec les boutons Exporter / Imprimer (jamais imprimé) */}
      <div className="no-print">
        <EnTetePage titre="Historique des paiements" sousTitre="Paiements en ligne (PawaPay) et règlements en caisse, réussis ou non">
          <button type="button" className="btn-outline btn-sm" onClick={exporter} disabled={exportEnCours || chargement}>
            {exportEnCours ? "Export…" : "📥 Exporter (Excel/CSV)"}
          </button>
          <button type="button" className="btn-outline btn-sm" onClick={() => window.print()} disabled={chargement}>🖨️ Imprimer</button>
        </EnTetePage>
      </div>

      {/* Filtres (jamais imprimés) */}
      <section className="no-print card mb-5 space-y-4 p-4">
        {/* Raccourcis de période : boutons « pilules » qui défilent sur téléphone */}
        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
          {PERIODES.map((p) => (
            <button key={p.code} type="button" onClick={() => choisirPeriode(p.code)}
              className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-sm font-semibold transition ${
                periode === p.code ? "border-primary bg-primary text-white" : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"}`}>
              {p.libelle}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {/* Dates : modifiables seulement en période personnalisée */}
          <label className="block">
            <span className="label">Du</span>
            <input type="date" className="input disabled:bg-gray-50" value={du} max={au} disabled={periode !== "perso"}
              onChange={(e) => e.target.value && changerFiltres({ periode: "perso", du: e.target.value, au })} />
          </label>
          <label className="block">
            <span className="label">Au</span>
            <input type="date" className="input disabled:bg-gray-50" value={au} min={du} disabled={periode !== "perso"}
              onChange={(e) => e.target.value && changerFiltres({ periode: "perso", du, au: e.target.value })} />
          </label>
          {/* Filtres par statut, canal et mode (listes fournies par le serveur) */}
          <label className="block">
            <span className="label">Statut</span>
            <select className="input" value={statut} onChange={(e) => changerFiltres({ statut: e.target.value })}>
              <option value="">Tous</option>
              {Object.entries(statuts).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="label">Canal</span>
            <select className="input" value={canal} onChange={(e) => changerFiltres({ canal: e.target.value })}>
              <option value="">Tous</option>
              {Object.entries(CANAUX).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
            </select>
          </label>
          <label className="col-span-2 block lg:col-span-1">
            <span className="label">Mode</span>
            <select className="input" value={mode} onChange={(e) => changerFiltres({ mode: e.target.value })}>
              <option value="">Tous</option>
              {Object.entries(modes).map(([code, libelle]) => <option key={code} value={code}>{libelle}</option>)}
            </select>
          </label>
        </div>

        {/* Rappel de la période affichée + effacement des filtres */}
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-gray-500">
          <span>{libellePeriode} : du <b>{date(du)}</b> au <b>{date(au)}</b></span>
          {filtresActifs.length > 0 && (
            <button type="button" className="font-semibold text-primary" onClick={() => changerFiltres({ statut: "", canal: "", mode: "" })}>
              ✕ Effacer les filtres
            </button>
          )}
        </div>
      </section>

      {erreur && <p className="card mb-5 text-red-600">{erreur}</p>}

      {/* Premier chargement : roue ; rechargements suivants : contenu grisé */}
      {!donnees && chargement ? <Chargement /> : donnees && (
        <div className={chargement ? "opacity-60 transition" : "transition"}>
          {/* Tuiles de synthèse (2 colonnes sur téléphone, 5 sur grand écran) */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5 print:grid-cols-5">
            {tuiles.map((t, i) => (
              <div key={t.libelle} className={`card flex flex-col gap-1 p-4 ${t.fond || ""} ${i === 0 ? "col-span-2 lg:col-span-1 print:col-span-1" : ""}`}>
                <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">{t.libelle}</span>
                <span className={`text-lg font-extrabold sm:text-2xl ${t.couleur}`}>{t.valeur}</span>
                <span className="text-xs text-gray-500">{t.detail}</span>
              </div>
            ))}
          </div>

          {/* Petit tableau « Encaissé par mode » (paiements réussis uniquement) */}
          <section className="card mt-5 p-0 print:break-inside-avoid">
            <h2 className="border-b border-gray-100 px-4 py-3 font-bold">Encaissé par mode de paiement</h2>
            {parMode.length === 0 ? <p className="px-4 py-4 text-sm text-gray-500">Aucun encaissement sur la période.</p> : (
              <table className="table">
                <thead><tr><th>Mode</th><th className="text-right">Nombre</th><th className="text-right">Montant</th></tr></thead>
                <tbody>
                  {parMode.map(([libelle, v]) => (
                    <tr key={libelle}><td>{libelle}</td><td className="text-right">{v.nombre}</td><td className="text-right font-semibold">{prix(v.montant, devise)}</td></tr>
                  ))}
                  <tr className="font-bold">
                    <td>Total</td>
                    <td className="text-right">{nb("SUCCES")}</td>
                    <td className="text-right text-green-700">{prix(donnees.total_encaisse, devise)}</td>
                  </tr>
                </tbody>
              </table>
            )}
          </section>

          {/* Liste détaillée des paiements */}
          <div className="mb-3 mt-6 flex items-baseline justify-between gap-2">
            <h2 className="font-bold">Détail des paiements</h2>
            <span className="text-sm text-gray-500">{donnees.entrees.length} ligne(s){donnees.entrees.length >= 5000 ? " (limite atteinte : réduisez la période)" : ""}</span>
          </div>
          {donnees.entrees.length === 0 ? (
            <div className="card py-12 text-center text-gray-500">
              <div className="mb-2 text-4xl">💳</div>
              <p>Aucun paiement ne correspond à ces critères.</p>
            </div>
          ) : (
            <ListePaiements entrees={donnees.entrees} statuts={statuts}
              liens={{ factures: peut(user, "facturation"), commandes: peut(user, "commandes") }} />
          )}
          <p className="mt-3 hidden text-right text-xs text-gray-500 print:block">Total encaissé sur la période : {montant(donnees.total_encaisse)} {devise}.</p>
        </div>
      )}
    </div>
  );
}
