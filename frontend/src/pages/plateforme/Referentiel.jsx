import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import { EnTetePlateforme } from "./_plateforme/composants";
import ModelesVendus from "./_plateforme/ModelesVendus";

// Référentiel MONDIAL des appareils (super-admin) : tous les modèles existants
// d'après la liste officielle Google Play (+ iPhone). On y cherche un appareil
// puis on crée sa fiche détaillée dans le catalogue public, éventuellement
// complétée tout de suite par l'assistant de recherche.
export default function Referentiel() {
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [resultat, setResultat] = useState(null);
  const [marques, setMarques] = useState([]);
  const [importEnCours, setImportEnCours] = useState(false);
  const [creation, setCreation] = useState(""); // clé de l'appareil en cours de création de fiche

  // Filtres gardés dans l'adresse (?q=&marque=&page=&sans_fiche=1)
  const q = params.get("q") || "";
  const marque = params.get("marque") || "";
  const page = Number(params.get("page") || 1);
  const sansFiche = params.get("sans_fiche") === "1";
  // Onglet affiché : tous les appareils du monde, ou modèles vendus dans les boutiques (?vue=vendus)
  const vue = params.get("vue") === "vendus" ? "vendus" : "monde";
  const majFiltre = (cle, valeur) => {
    const suivants = new URLSearchParams(params);
    if (valeur) suivants.set(cle, valeur); else suivants.delete(cle);
    if (cle !== "page") suivants.delete("page");
    setParams(suivants, { replace: true });
  };

  // Recherche (petit délai pendant la frappe)
  useEffect(() => {
    if (vue !== "monde") return undefined;
    const t = setTimeout(() => {
      apiClient.get("/plateforme/referentiel", { params: { q, marque, page, sans_fiche: sansFiche } })
        .then(({ data }) => setResultat(data))
        .catch((err) => toast.erreur(messageErreur(err, "Recherche impossible")));
    }, 250);
    return () => clearTimeout(t);
  }, [q, marque, page, sansFiche, toast, vue]);

  // Liste des marques (pour le filtre), rechargée après un import
  useEffect(() => {
    apiClient.get("/referentiel/marques").then(({ data }) => setMarques(data)).catch(() => {});
  }, [resultat?.dernier_import?.date]);

  // Import / mise à jour depuis la liste officielle Google Play
  async function importer() {
    if (!window.confirm("Télécharger la liste officielle Google Play et mettre le référentiel à jour ? (1 à 3 minutes)")) return;
    setImportEnCours(true);
    try {
      const { data } = await apiClient.post("/plateforme/referentiel/importer", null, { timeout: 600000 });
      toast.succes(`Référentiel à jour : ${data.total} appareils (${data.google.nouveaux + data.apple.nouveaux} nouveaux).`);
      majFiltre("page", "");
    } catch (err) {
      toast.erreur(messageErreur(err, "Import impossible"));
    } finally {
      setImportEnCours(false);
    }
  }

  // Création de la fiche détaillée (brouillon) dans le catalogue public
  async function creerFiche(appareil, avecAssistant) {
    setCreation(appareil.cle);
    try {
      const { data } = await apiClient.post(`/plateforme/referentiel/${appareil.cle}/fiche`,
        { avec_assistant: avecAssistant }, { timeout: 240000 });
      if (data.existante) {
        toast.info("Une fiche existait déjà sous ce code modèle : elle est maintenant reliée à cet appareil.");
      } else if (avecAssistant && data.proposition && !data.proposition.trouve) {
        toast.info(`Fiche créée, mais l'assistant n'a pas trouvé le modèle : ${data.proposition.remarques || ""}`);
      } else {
        toast.succes("Fiche créée en brouillon : relisez-la puis passez-la en « Prête » pour la publier ce soir.");
      }
      navigate(`/plateforme/catalogue?fiche=${data.fiche.id}`);
    } catch (err) {
      toast.erreur(messageErreur(err, "Création de la fiche impossible"));
    } finally {
      setCreation("");
    }
  }

  const dernier = resultat?.dernier_import;
  return (
    <div className="min-h-screen bg-papier">
      <EnTetePlateforme />
      <main className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold">Référentiel mondial des appareils</h1>
            <p className="text-sm text-gray-500">
              Tous les modèles connus (liste officielle Google Play des appareils Android + iPhone).
              {dernier && <> Dernière mise à jour : {dateHeure(dernier.date)} — {dernier.total} appareils.</>}
            </p>
          </div>
          {vue === "monde" && (
            <button type="button" className="btn-primary" disabled={importEnCours} onClick={importer}>
              {importEnCours ? "Import en cours…" : resultat?.total ? "↻ Mettre à jour la liste" : "⬇ Importer la liste mondiale"}
            </button>
          )}
        </div>

        {/* Choix de l'onglet (gardé dans l'adresse : ?vue=vendus) */}
        <div className="inline-flex rounded-xl border border-gray-200 bg-white p-1">
          {[["monde", "📚 Tous les appareils"], ["vendus", "🏪 Modèles vendus dans mes boutiques"]].map(([cle, libelle]) => (
            <button key={cle} type="button" onClick={() => setParams(cle === "vendus" ? { vue: "vendus" } : {}, { replace: true })}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${vue === cle ? "bg-primary text-white" : "text-gray-600"}`}>{libelle}</button>
          ))}
        </div>

        {vue === "vendus" ? <ModelesVendus /> : (<>

        {/* Filtres */}
        <div className="flex flex-wrap gap-3">
          <input className="input max-w-sm" placeholder="Nom ou code modèle (ex. Galaxy A15, SM-A155F)…" value={q}
            onChange={(e) => majFiltre("q", e.target.value)} />
          <select className="input max-w-[14rem]" value={marque} onChange={(e) => majFiltre("marque", e.target.value)}>
            <option value="">Toutes les marques ({marques.length})</option>
            {marques.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={sansFiche} onChange={(e) => majFiltre("sans_fiche", e.target.checked ? "1" : "")} />
            Seulement ceux sans fiche détaillée
          </label>
        </div>

        {!resultat ? <Chargement /> : resultat.total === 0 ? (
          <div className="card text-center text-gray-600">
            {q || marque ? "Aucun appareil ne correspond." : "Le référentiel est vide : cliquez sur « Importer la liste mondiale »."}
          </div>
        ) : (
          <>
            <p className="text-sm text-gray-500">{resultat.total.toLocaleString("fr-FR")} appareil(s)</p>
            {/* Liste des appareils */}
            <div className="card divide-y divide-gray-100 p-0">
              {resultat.appareils.map((a) => (
                <div key={a.cle} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">{a.marque} {a.nom} {a.annee_sortie ? <span className="font-normal text-gray-500">· {a.annee_sortie}</span> : null}</p>
                    <p className="truncate font-mono text-xs text-gray-500">{a.codes_modele.join(" · ") || "—"}</p>
                  </div>
                  {a.catalogue_id ? (
                    <button type="button" className="btn-outline btn-sm" onClick={() => navigate(`/plateforme/catalogue?fiche=${a.catalogue_id}`)}>
                      {a.fiche_publiee ? "✅ Fiche publiée" : "📝 Fiche en brouillon"}
                    </button>
                  ) : (
                    <div className="flex gap-2">
                      <button type="button" className="btn-outline btn-sm" disabled={!!creation} onClick={() => creerFiche(a, false)}>Créer la fiche</button>
                      <button type="button" className="btn-primary btn-sm" disabled={!!creation} onClick={() => creerFiche(a, true)}>
                        {creation === a.cle ? "Recherche…" : "🔎 Créer + rechercher"}
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
            {/* Pagination */}
            {resultat.pages > 1 && (
              <div className="flex items-center justify-center gap-3 text-sm">
                <button type="button" className="btn-outline btn-sm" disabled={page <= 1} onClick={() => majFiltre("page", String(page - 1))}>← Précédent</button>
                Page {page} / {resultat.pages}
                <button type="button" className="btn-outline btn-sm" disabled={page >= resultat.pages} onClick={() => majFiltre("page", String(page + 1))}>Suivant →</button>
              </div>
            )}
          </>
        )}
        <p className="text-xs text-gray-500">
          La liste Google ne contient que l'identité des appareils (marque, nom, codes modèle). Les caractéristiques,
          la photo et les pièces détachées sont ajoutées fiche par fiche, avec l'assistant de recherche.
        </p>
        </>)}
      </main>
    </div>
  );
}
