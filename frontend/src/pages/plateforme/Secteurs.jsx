// ============================================================================
// PLATEFORME > SECTEURS D'ACTIVITÉ (super-administrateur) — lot A
// ============================================================================
// adLyn sert tout type de commerce. Chaque secteur (télécom, prêt-à-porter,
// cosmétiques, quincaillerie…) règle pour les boutiques qui le choisissent :
//   - le VOCABULAIRE de l'interface (« Article » au lieu de « Produit », « Rayon »…) ;
//   - les CHAMPS propres aux articles (Taille, Couleur, Date de péremption, ISBN…) ;
//   - les MODULES du menu activés d'office à la création de la boutique ;
//   - les CATÉGORIES créées pour une nouvelle boutique ;
//   - « catalogue télécom » : copie du catalogue public de téléphones + référentiel.
// La page affiche un tableau des secteurs ; un clic ouvre le formulaire d'édition.
// Routes : GET/POST /plateforme/secteurs, PUT/DELETE /plateforme/secteurs/{code}.
// ============================================================================
import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import Patientez from "@/components/Patientez";
import { useToast } from "@/components/Toast";
import { Champ, EnTetePlateforme, TitreSection } from "./_plateforme/composants";

// Libellés des types de champ proposés dans l'éditeur
const LIBELLES_TYPES = { texte: "Texte", nombre: "Nombre", date: "Date", liste: "Liste (un choix)", multi_liste: "Liste (plusieurs choix)" };

// Explication de chaque terme du vocabulaire (aide affichée sous le champ)
const AIDES_VOCABULAIRE = {
  article: "Un élément vendu (ex. Produit, Article, Référence)",
  articles: "Le pluriel (ex. Produits, Articles)",
  nouvel_article: "Bouton de création (ex. Nouveau produit, Nouvel article)",
  categorie: "Classement (ex. Catégorie, Rayon, Famille)",
  categories: "Le pluriel (ex. Catégories, Rayons, Familles)",
  catalogue: "Entrée du menu et titre de la liste",
  stock: "Entrée du menu Stock",
  caracteristiques: "Titre de la section des champs du secteur",
};

// Nouveau secteur : valeurs de départ du formulaire
const SECTEUR_VIDE = {
  code: "", libelle: "", icone: "🏪", actif: true, ordre: 50, vocabulaire: {}, champs: [],
  modules: ["produits", "stock", "clients", "documents"], categories_depart: [], catalogue_telecom: false,
};

export default function Secteurs() {
  const toast = useToast();
  const [donnees, setDonnees] = useState(null); // { secteurs, vocabulaire_defaut, modules, types_champ }
  const [edition, setEdition] = useState(null); // secteur ouvert dans le formulaire (null = fermé)
  const [creation, setCreation] = useState(false); // vrai : formulaire de création
  const [occupe, setOccupe] = useState(false); // attente longue -> toast « Patientez… »

  // Chargement de la liste (et des listes de l'éditeur : termes, modules, types)
  const charger = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/plateforme/secteurs");
      setDonnees(data);
    } catch (err) {
      toast.erreur(messageErreur(err, "Impossible de charger les secteurs"));
    }
  }, [toast]);
  useEffect(() => { charger(); }, [charger]);

  // Ouverture du formulaire : copie du secteur (on ne modifie pas la liste avant l'enregistrement)
  const ouvrir = (s) => { setCreation(false); setEdition(JSON.parse(JSON.stringify(s))); };
  const nouveau = () => { setCreation(true); setEdition(JSON.parse(JSON.stringify(SECTEUR_VIDE))); };

  // Enregistrement : POST (création) ou PUT (modification)
  async function enregistrer(e) {
    e.preventDefault();
    const corps = {
      libelle: edition.libelle, icone: edition.icone, actif: edition.actif, ordre: Number(edition.ordre) || 0,
      vocabulaire: edition.vocabulaire,
      // (options_texte = saisie brute de la zone « valeurs proposées », non envoyée)
      champs: edition.champs.map(({ options_texte, ...c }) => ({ ...c, options: (c.options || []).map((o) => o.trim()).filter(Boolean) })), // eslint-disable-line no-unused-vars
      modules: edition.modules, categories_depart: edition.categories_depart.map((c) => c.trim()).filter(Boolean),
      catalogue_telecom: edition.catalogue_telecom,
    };
    setOccupe(true);
    try {
      if (creation) await apiClient.post("/plateforme/secteurs", { ...corps, code: edition.code.trim() });
      else await apiClient.put(`/plateforme/secteurs/${edition.code}`, corps);
      toast.succes(`Secteur « ${edition.libelle} » enregistré`);
      setEdition(null);
      await charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible : vérifiez les champs"));
    } finally {
      setOccupe(false);
    }
  }

  // Suppression (refusée par le serveur si des boutiques l'utilisent)
  async function supprimer() {
    if (!window.confirm(`Supprimer le secteur « ${edition.libelle} » ?`)) return;
    setOccupe(true);
    try {
      await apiClient.delete(`/plateforme/secteurs/${edition.code}`);
      toast.succes("Secteur supprimé");
      setEdition(null);
      await charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Suppression impossible"));
    } finally {
      setOccupe(false);
    }
  }

  return (
    <div className="min-h-screen bg-papier">
      <EnTetePlateforme />
      <Patientez actif={occupe} />
      <main className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold">Secteurs d'activité</h1>
            <p className="max-w-3xl text-sm text-gray-500">
              Chaque boutique appartient à un secteur : il fixe le vocabulaire de son interface, les champs de ses
              articles, les modules activés et les catégories créées à l'ouverture. Seul le télécom reçoit le catalogue
              public de téléphones, la fiche technique et le SAV (activable ailleurs, boutique par boutique).
            </p>
          </div>
          <button type="button" className="btn-primary" onClick={nouveau}>+ Nouveau secteur</button>
        </div>

        {!donnees ? <Chargement /> : (
          <div className="card overflow-x-auto p-0">
            <table className="table min-w-[760px]">
              <thead>
                <tr>
                  <th>Ordre</th><th>Secteur</th><th>Code</th><th>Vocabulaire</th>
                  <th className="text-right">Champs</th><th className="text-right">Modules</th>
                  <th className="text-right">Boutiques</th><th className="text-center">État</th>
                </tr>
              </thead>
              <tbody>
                {donnees.secteurs.map((s) => (
                  <tr key={s.code} className={`cursor-pointer ${edition?.code === s.code && !creation ? "ligne-selectionnee" : ""}`}
                    aria-selected={edition?.code === s.code && !creation} onClick={() => ouvrir(s)}>
                    <td className="text-gray-500">{s.ordre}</td>
                    <td className="font-semibold"><span className="mr-2">{s.icone}</span>{s.libelle}
                      {s.catalogue_telecom && <span className="badge ml-2 bg-blue-100 text-blue-800">catalogue télécom</span>}</td>
                    <td className="font-mono text-xs">{s.code}</td>
                    <td className="text-sm text-gray-600">
                      {(s.vocabulaire.article || donnees.vocabulaire_defaut.article)} · {(s.vocabulaire.categorie || donnees.vocabulaire_defaut.categorie)}
                    </td>
                    <td className="text-right">{s.champs.length}</td>
                    <td className="text-right">{s.modules.length}</td>
                    <td className="text-right font-semibold">{s.nb_boutiques}</td>
                    <td className="text-center">{s.actif ? <span className="badge bg-green-100 text-green-800">Actif</span> : <span className="badge bg-gray-100 text-gray-600">Inactif</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {edition && donnees && (
        <EditeurSecteur secteur={edition} onChange={setEdition} creation={creation} donnees={donnees}
          onFermer={() => setEdition(null)} onEnregistrer={enregistrer} onSupprimer={supprimer} occupe={occupe} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formulaire d'édition d'un secteur (fenêtre modale)
// ---------------------------------------------------------------------------
function EditeurSecteur({ secteur, onChange, creation, donnees, onFermer, onEnregistrer, onSupprimer, occupe }) {
  const s = secteur;
  const maj = (champ, valeur) => onChange({ ...s, [champ]: valeur });
  const majVocabulaire = (cle, valeur) => maj("vocabulaire", { ...s.vocabulaire, [cle]: valeur });

  // --- Champs du secteur : ajout, modification, suppression, déplacement ---
  const majChamp = (i, cle, valeur) => maj("champs", s.champs.map((c, j) => (j === i ? { ...c, [cle]: valeur } : c)));
  const ajouterChamp = () => maj("champs", [...s.champs, { cle: "", libelle: "", type: "texte", options: [], obligatoire: false }]);
  const retirerChamp = (i) => maj("champs", s.champs.filter((_, j) => j !== i));
  const deplacerChamp = (i, sens) => {
    const j = i + sens;
    if (j < 0 || j >= s.champs.length) return;
    const liste = [...s.champs];
    [liste[i], liste[j]] = [liste[j], liste[i]];
    maj("champs", liste);
  };
  // Clé proposée à partir du libellé (« Date de péremption » -> date_de_peremption)
  const cleDepuis = (libelle) => libelle.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/^[^a-z]+/, "").slice(0, 40);

  // --- Modules : cases à cocher (les deux obligatoires sont toujours actifs) ---
  const basculerModule = (cle) => maj("modules", s.modules.includes(cle) ? s.modules.filter((m) => m !== cle) : [...s.modules, cle]);

  return (
    <Modal ouvert titre={creation ? "Nouveau secteur d'activité" : `${s.icone} ${s.libelle}`} onFermer={onFermer} large>
      <form onSubmit={onEnregistrer} className="grid gap-3 sm:grid-cols-2">
        {/* ----- Identité du secteur ----- */}
        <TitreSection premier>🧭 Le secteur</TitreSection>
        <Champ label="Libellé *"><input className="input" required minLength={2} maxLength={120} value={s.libelle} onChange={(e) => maj("libelle", e.target.value)} /></Champ>
        <Champ label="Code *" aide={creation ? "Minuscules, chiffres et _ (ex. bijouterie) ; non modifiable ensuite." : "Fixé à la création."}>
          <input className="input font-mono" required disabled={!creation} pattern="[a-z][a-z0-9_]{1,39}" value={s.code} onChange={(e) => maj("code", e.target.value)} />
        </Champ>
        <Champ label="Pictogramme du menu" aide="Affiché devant « Catalogue » (ex. 👗 💄 🔧).">
          <input className="input" maxLength={8} value={s.icone} onChange={(e) => maj("icone", e.target.value)} />
        </Champ>
        <Champ label="Ordre d'affichage"><input className="input" type="number" min={0} max={9999} value={s.ordre} onChange={(e) => maj("ordre", e.target.value)} /></Champ>
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" className="h-4 w-4 accent-primary" checked={s.actif} disabled={s.code === "telecom"} onChange={(e) => maj("actif", e.target.checked)} />
          Actif (proposé aux nouvelles boutiques)
        </label>
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" className="h-4 w-4 accent-primary" checked={s.catalogue_telecom} onChange={(e) => maj("catalogue_telecom", e.target.checked)} />
          Catalogue télécom (téléphones, fiche technique, référentiel)
        </label>

        {/* ----- Vocabulaire : vide = terme actuel de l'interface ----- */}
        <TitreSection>💬 Vocabulaire de l'interface</TitreSection>
        <p className="-mt-1 text-xs text-gray-500 sm:col-span-2">Laissez vide pour garder le terme actuel (indiqué en grisé).</p>
        {Object.entries(donnees.vocabulaire_defaut).map(([cle, defaut]) => (
          <Champ key={cle} label={cle.replace("_", " ")} aide={AIDES_VOCABULAIRE[cle]}>
            <input className="input" maxLength={60} placeholder={defaut} value={s.vocabulaire[cle] || ""} onChange={(e) => majVocabulaire(cle, e.target.value)} />
          </Champ>
        ))}

        {/* ----- Champs propres aux articles du secteur ----- */}
        <TitreSection>🏷️ Champs des articles</TitreSection>
        <div className="space-y-3 sm:col-span-2">
          {s.champs.length === 0 && <p className="text-sm text-gray-500">Aucun champ propre à ce secteur.</p>}
          {s.champs.map((c, i) => (
            <div key={i} className="grid gap-2 rounded-xl border border-gray-200 p-3 sm:grid-cols-[1fr_1fr_1fr_auto]">
              <input className="input" required placeholder="Libellé (ex. Taille)" maxLength={80} value={c.libelle}
                onChange={(e) => onChange({ ...s, champs: s.champs.map((x, j) => (j === i ? { ...x, libelle: e.target.value, cle: x.cle || cleDepuis(e.target.value) } : x)) })} />
              <input className="input font-mono" required placeholder="cle_technique" pattern="[a-z][a-z0-9_]{1,39}" maxLength={40} value={c.cle}
                title="Minuscules, chiffres et _ ; changer une clé « oublie » les valeurs déjà saisies" onChange={(e) => majChamp(i, "cle", e.target.value)} />
              <select className="input" value={c.type} onChange={(e) => majChamp(i, "type", e.target.value)}>
                {donnees.types_champ.map((t) => <option key={t} value={t}>{LIBELLES_TYPES[t] || t}</option>)}
              </select>
              <div className="flex items-center gap-1">
                <button type="button" className="btn-outline btn-sm" onClick={() => deplacerChamp(i, -1)} aria-label="Monter">↑</button>
                <button type="button" className="btn-outline btn-sm" onClick={() => deplacerChamp(i, 1)} aria-label="Descendre">↓</button>
                <button type="button" className="btn-sm rounded-lg text-red-600 hover:bg-red-50" onClick={() => retirerChamp(i)} aria-label="Retirer le champ">🗑️</button>
              </div>
              {(c.type === "liste" || c.type === "multi_liste") && (
                <input className="input sm:col-span-3" required placeholder="Valeurs proposées, séparées par des virgules (ex. S, M, L)"
                  value={c.options_texte ?? (c.options || []).join(", ")}
                  onChange={(e) => onChange({ ...s, champs: s.champs.map((x, j) => (j === i ? { ...x, options_texte: e.target.value, options: e.target.value.split(",") } : x)) })} />
              )}
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="h-4 w-4 accent-primary" checked={!!c.obligatoire} onChange={(e) => majChamp(i, "obligatoire", e.target.checked)} />
                Obligatoire
              </label>
            </div>
          ))}
          <button type="button" className="btn-outline btn-sm" onClick={ajouterChamp}>+ Ajouter un champ</button>
        </div>

        {/* ----- Modules activés d'office à la création d'une boutique ----- */}
        <TitreSection>🧩 Modules activés à la création</TitreSection>
        <p className="-mt-1 text-xs text-gray-500 sm:col-span-2">
          Tableau de bord et Caisse Aizenta sont toujours actifs. Maintenance (SAV) et Catalogue public sont propres au télécom.
          Le réglage boutique par boutique reste possible ensuite (« Barre latérale & Caisse Aizenta »).
        </p>
        <div className="grid gap-1 sm:col-span-2 sm:grid-cols-3">
          {donnees.modules.filter((m) => !m.obligatoire).map((m) => (
            <label key={m.cle} className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4 accent-primary" checked={s.modules.includes(m.cle)} onChange={() => basculerModule(m.cle)} />
              {m.libelle}
            </label>
          ))}
        </div>

        {/* ----- Catégories créées pour une nouvelle boutique ----- */}
        <TitreSection>🗂️ Catégories de départ</TitreSection>
        <Champ label="Une catégorie par ligne" className="sm:col-span-2" aide="Créées à l'ouverture d'une boutique de ce secteur (la boutique peut ensuite les modifier).">
          <textarea className="input min-h-[110px]" value={s.categories_depart.join("\n")} onChange={(e) => maj("categories_depart", e.target.value.split("\n"))} />
        </Champ>

        {/* ----- Boutons ----- */}
        <div className="flex flex-wrap justify-between gap-2 border-t border-gray-200 pt-4 sm:col-span-2">
          {!creation && s.code !== "telecom"
            ? <button type="button" className="btn-sm rounded-lg text-red-600 hover:bg-red-50" disabled={occupe} onClick={onSupprimer}>🗑️ Supprimer le secteur</button>
            : <span />}
          <div className="flex gap-2">
            <button type="button" className="btn-outline" onClick={onFermer}>Annuler</button>
            <button className="btn-primary" disabled={occupe}>{occupe ? "Patientez…" : "💾 Enregistrer"}</button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
