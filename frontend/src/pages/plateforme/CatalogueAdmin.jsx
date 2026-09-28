import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import { TYPES_PRODUIT } from "@/lib/statuts";
import Chargement from "@/components/Chargement";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";

// Types de fiches du catalogue public (pas de « service » ici)
const TYPES = { TEL: TYPES_PRODUIT.TEL, PIE: TYPES_PRODUIT.PIE, ACC: TYPES_PRODUIT.ACC };

// Fiche vide (création)
const FICHE_VIDE = {
  type_produit: "TEL", marque: "", nom: "", reference: "", annee_sortie: "", description: "",
  caracteristiques: "", photo_url: "", modeles_compatibles: [], sources: "", statut: "BROUILLON",
};

/** État de publication d'une fiche, pour le badge de la liste */
function etatFiche(f) {
  if (!f.publie) return f.statut === "PRET"
    ? { libelle: "Publication ce soir", classe: "bg-amber-100 text-amber-800" }
    : { libelle: "Brouillon", classe: "bg-gray-100 text-gray-700" };
  if (f.modifie_apres_publication) return f.statut === "PRET"
    ? { libelle: `Modifiée — republiée ce soir (v${f.version_publiee})`, classe: "bg-amber-100 text-amber-800" }
    : { libelle: `Modifiée, brouillon (v${f.version_publiee})`, classe: "bg-gray-100 text-gray-700" };
  return { libelle: `Publiée (v${f.version_publiee})`, classe: "bg-green-100 text-green-800" };
}

// ---------------------------------------------------------------------------
// Page : catalogue public commun (administrateur de la plateforme)
// ---------------------------------------------------------------------------
export default function CatalogueAdmin() {
  const toast = useToast();
  // useToast() renvoie un NOUVEL objet à chaque affichage : s'il figurait dans
  // les dépendances de `charger`, la liste serait rechargée en boucle (toutes
  // les 250 ms). On passe donc par une référence stable.
  const toastRef = useRef(toast);
  toastRef.current = toast;
  const [fiches, setFiches] = useState(null);
  const [publication, setPublication] = useState(null);
  const [filtres, setFiltres] = useState({ q: "", type_produit: "", statut: "" });
  const [edition, setEdition] = useState(null); // fiche ouverte dans l'éditeur (null = fermé)

  // Chargement de la liste (avec les filtres) et de l'état de la publication
  const charger = useCallback(async () => {
    try {
      const [liste, etat] = await Promise.all([
        apiClient.get("/plateforme/catalogue", { params: filtres }),
        apiClient.get("/plateforme/catalogue/publication"),
      ]);
      setFiches(liste.data);
      setPublication(etat.data);
    } catch (err) {
      toastRef.current.erreur(messageErreur(err, "Chargement du catalogue impossible"));
    }
  }, [filtres]);

  useEffect(() => {
    const t = setTimeout(charger, 250); // petit délai pendant la frappe dans la recherche
    return () => clearTimeout(t);
  }, [charger]);

  // Publication immédiate (sans attendre 23h)
  async function publierMaintenant() {
    if (!window.confirm("Publier maintenant toutes les fiches prêtes dans toutes les boutiques ?")) return;
    try {
      const { data } = await apiClient.post("/plateforme/catalogue/publier");
      toast.succes(`Publication faite : ${data.nouveaux} nouveauté(s), ${data.mises_a_jour} mise(s) à jour, ${data.boutiques} boutique(s).`);
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Publication impossible"));
    }
  }

  // Téléphones du catalogue (pour les compatibilités des pièces)
  const telephones = useMemo(() => (fiches || []).filter((f) => f.type_produit === "TEL"), [fiches]);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="flex items-center justify-between gap-3 border-b border-gray-200 bg-white px-4 py-3">
        <div>
          <Link to="/plateforme" className="text-sm font-semibold text-primary">← Plateforme</Link>
          <h1 className="text-xl font-extrabold">Catalogue public commun</h1>
        </div>
        <button type="button" className="btn-primary" onClick={() => setEdition({ ...FICHE_VIDE })}>+ Nouvelle fiche</button>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6">
        {/* Bandeau de publication : prochaine publication automatique + fiches en attente */}
        {publication && (
          <div className="card flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="font-bold">
                Prochaine publication automatique : {dateHeure(publication.prochaine_publication)}
              </p>
              <p className="text-sm text-gray-600">
                {publication.en_attente} fiche(s) prête(s) en attente. Les nouveaux modèles arrivent dans chaque boutique
                sans prix, invisibles sur son portail, avec le badge « Nouveau ».
              </p>
            </div>
            <button type="button" className="btn-outline" disabled={!publication.en_attente} onClick={publierMaintenant}>
              Publier maintenant
            </button>
          </div>
        )}

        {/* Filtres */}
        <div className="flex flex-wrap gap-3">
          <input className="input max-w-xs" placeholder="Rechercher (nom, marque, référence)…" value={filtres.q}
            onChange={(e) => setFiltres({ ...filtres, q: e.target.value })} />
          <select className="input max-w-[12rem] bg-white" value={filtres.type_produit} onChange={(e) => setFiltres({ ...filtres, type_produit: e.target.value })}>
            <option value="">Tous les types</option>
            {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="input max-w-[14rem] bg-white" value={filtres.statut} onChange={(e) => setFiltres({ ...filtres, statut: e.target.value })}>
            <option value="">Toutes les fiches</option>
            <option value="BROUILLON">Brouillons</option>
            <option value="PRET">Prêtes</option>
            <option value="EN_ATTENTE">En attente de publication</option>
          </select>
        </div>

        {/* Liste des fiches */}
        {!fiches ? <Chargement /> : (
          <div className="card overflow-x-auto p-0">
            <table className="table">
              <thead><tr><th /><th>Modèle</th><th className="hidden sm:table-cell">Référence</th><th className="hidden md:table-cell">Type</th><th>État</th><th className="hidden md:table-cell">Mise à jour</th></tr></thead>
              <tbody>
                {fiches.map((f) => {
                  const etat = etatFiche(f);
                  return (
                    <tr key={f.id} className="cursor-pointer hover:bg-gray-50" onClick={() => setEdition(versFormulaire(f))}>
                      <td className="w-14">
                        {f.photo_url ? <img src={f.photo_url} alt="" className="h-10 w-10 rounded-lg object-contain" /> : <span className="text-2xl">📱</span>}
                      </td>
                      <td>
                        <span className="font-semibold">{f.marque} {f.nom}</span>{f.annee_sortie ? <span className="text-gray-500"> · {f.annee_sortie}</span> : null}
                        {/* Sur téléphone, les colonnes Référence et Type sont masquées : on les rappelle ici */}
                        <span className="block font-mono text-xs text-gray-500 sm:hidden">{f.reference} · {TYPES[f.type_produit]}</span>
                      </td>
                      <td className="hidden font-mono text-xs sm:table-cell">{f.reference}</td>
                      <td className="hidden md:table-cell">{TYPES[f.type_produit]}</td>
                      <td><span className={`badge ${etat.classe}`}>{etat.libelle}</span></td>
                      <td className="hidden text-xs text-gray-500 md:table-cell">{dateHeure(f.updated_at)}</td>
                    </tr>
                  );
                })}
                {fiches.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-gray-500">Aucune fiche.</td></tr>}
              </tbody>
            </table>
          </div>
        )}

        {/* Historique des publications */}
        {publication?.historique?.length > 0 && (
          <div className="card">
            <h2 className="mb-2 font-bold">Dernières publications</h2>
            <ul className="space-y-1 text-sm text-gray-600">
              {publication.historique.map((h) => (
                <li key={h.id}>
                  {dateHeure(h.date)} — {h.declencheur === "manuel" ? "manuelle" : "automatique"} :
                  {" "}{h.nouveaux} nouveauté(s), {h.mises_a_jour} mise(s) à jour, {h.boutiques} boutique(s)
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>

      <EditeurFiche
        fiche={edition} telephones={telephones}
        onFermer={() => setEdition(null)}
        onEnregistre={(f) => { setEdition(f ? versFormulaire(f) : null); charger(); }}
      />
    </div>
  );
}

/** Fiche de l'API -> valeurs du formulaire (listes transformées en texte, une ligne par élément) */
function versFormulaire(f) {
  return {
    ...FICHE_VIDE, ...f,
    annee_sortie: f.annee_sortie || "",
    caracteristiques: (f.caracteristiques || []).join("\n"),
    sources: (f.sources || []).join("\n"),
    photo_url: f.photo_url || "",
    modeles_compatibles: f.modeles_compatibles || [],
  };
}

/** Valeurs du formulaire -> corps de requête de l'API */
function versApi(f) {
  const lignes = (t) => t.split("\n").map((x) => x.trim()).filter(Boolean);
  return {
    type_produit: f.type_produit, marque: f.marque.trim(), nom: f.nom.trim(), reference: f.reference.trim(),
    annee_sortie: f.annee_sortie ? Number(f.annee_sortie) : null, description: f.description,
    caracteristiques: lignes(f.caracteristiques), photo_url: f.photo_url || null,
    modeles_compatibles: f.type_produit === "TEL" ? [] : f.modeles_compatibles,
    sources: lignes(f.sources), statut: f.statut,
  };
}

// ---------------------------------------------------------------------------
// Éditeur d'une fiche + assistant de recherche
// ---------------------------------------------------------------------------
function EditeurFiche({ fiche, telephones, onFermer, onEnregistre }) {
  const toast = useToast();
  const [f, setF] = useState(fiche);
  const [envoi, setEnvoi] = useState(false);
  const [recherche, setRecherche] = useState({ enCours: false, resultat: null });
  const [piecesChoisies, setPiecesChoisies] = useState([]);
  const [filtreTel, setFiltreTel] = useState("");

  // Recharge le formulaire à chaque ouverture d'une autre fiche
  useEffect(() => {
    setF(fiche);
    setRecherche({ enCours: false, resultat: null });
    setPiecesChoisies([]);
  }, [fiche]);

  if (!fiche || !f) return null;
  const maj = (champ) => (e) => setF({ ...f, [champ]: e.target.value });

  // Enregistrement (création ou modification) ; renvoie la fiche enregistrée
  async function enregistrer(e) {
    e?.preventDefault();
    setEnvoi(true);
    try {
      const { data } = f.id
        ? await apiClient.put(`/plateforme/catalogue/${f.id}`, versApi(f))
        : await apiClient.post("/plateforme/catalogue", versApi(f));
      toast.succes(f.statut === "PRET" ? "Fiche enregistrée — elle sera publiée ce soir." : "Brouillon enregistré.");
      onEnregistre(data);
      return data;
    } catch (err) {
      toast.erreur(messageErreur(err, "Enregistrement impossible : vérifiez les champs obligatoires"));
      return null;
    } finally {
      setEnvoi(false);
    }
  }

  // Assistant : recherche de la fiche technique sur les sites des fabricants
  async function lancerRecherche() {
    if (!f.marque || !f.nom) {
      toast.info("Indiquez d'abord la marque et le nom du modèle.");
      return;
    }
    setRecherche({ enCours: true, resultat: null });
    try {
      const { data } = await apiClient.post("/plateforme/catalogue/recherche", { marque: f.marque, modele: f.nom }, { timeout: 180000 });
      setRecherche({ enCours: false, resultat: data });
      setPiecesChoisies(data.pieces_detachees || []);
    } catch (err) {
      setRecherche({ enCours: false, resultat: null });
      toast.erreur(messageErreur(err, "La recherche n'a pas abouti"));
    }
  }

  // Recopie la proposition de l'assistant dans le formulaire (à relire ensuite)
  function appliquerProposition() {
    const r = recherche.resultat;
    setF({
      ...f,
      marque: r.marque || f.marque, nom: r.nom || f.nom,
      reference: f.reference || (r.reference_fabricant || "").toUpperCase(),
      annee_sortie: r.annee_sortie || f.annee_sortie, description: r.description || f.description,
      caracteristiques: (r.caracteristiques || []).join("\n") || f.caracteristiques,
      sources: (r.sources || []).join("\n") || f.sources,
    });
    toast.info("Proposition recopiée : relisez-la avant d'enregistrer.");
  }

  // Importe la photo proposée dans notre stockage (la fiche doit être enregistrée)
  async function importerPhoto(url) {
    const enregistree = f.id ? f : await enregistrer();
    if (!enregistree) return;
    try {
      const { data } = await apiClient.post(`/plateforme/catalogue/${enregistree.id}/photo-depuis-url`, { url });
      setF(versFormulaire(data));
      toast.succes("Photo importée.");
    } catch (err) {
      toast.erreur(messageErreur(err, "Import de la photo impossible"));
    }
  }

  // Envoi d'une photo depuis l'ordinateur
  async function envoyerPhoto(e) {
    const fichier = e.target.files?.[0];
    if (!fichier) return;
    const enregistree = f.id ? f : await enregistrer();
    if (!enregistree) return;
    const donnees = new FormData();
    donnees.append("fichier", fichier);
    try {
      const { data } = await apiClient.post(`/plateforme/catalogue/${enregistree.id}/photo`, donnees);
      setF(versFormulaire(data));
      toast.succes("Photo enregistrée.");
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi de la photo impossible"));
    }
  }

  // Crée les pièces détachées cochées (brouillons compatibles avec ce téléphone)
  async function creerPieces() {
    const tel = f.id ? f : await enregistrer();
    if (!tel) return;
    let n = 0;
    for (const nomPiece of piecesChoisies) {
      const reference = `PIE-${tel.reference}-${n + 1}`.toUpperCase().replace(/[^A-Z0-9-]/g, "").slice(0, 60);
      try {
        await apiClient.post("/plateforme/catalogue", {
          type_produit: "PIE", marque: tel.marque, nom: `${nomPiece} — ${tel.marque} ${tel.nom}`.slice(0, 150),
          reference, caracteristiques: [], modeles_compatibles: [tel.id], sources: [], statut: "BROUILLON",
        });
        n += 1;
      } catch (err) {
        toast.erreur(`${nomPiece} : ${messageErreur(err, "création impossible")}`);
      }
    }
    if (n) toast.succes(`${n} pièce(s) créée(s) en brouillon, compatibles avec ce téléphone.`);
    onEnregistre(tel);
  }

  const telFiltres = telephones.filter((t) => t.id !== f.id && `${t.marque} ${t.nom}`.toLowerCase().includes(filtreTel.toLowerCase()));

  return (
    <Modal ouvert titre={f.id ? `${f.marque} ${f.nom}` : "Nouvelle fiche du catalogue public"} onFermer={onFermer} large>
      <form onSubmit={enregistrer} className="space-y-4">
        {/* Identification du modèle */}
        <div className="grid gap-3 sm:grid-cols-3">
          <div><label className="label">Type</label>
            <select className="input" value={f.type_produit} onChange={maj("type_produit")}>
              {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></div>
          <div><label className="label">Marque</label><input className="input" required value={f.marque} onChange={maj("marque")} placeholder="Samsung" /></div>
          <div><label className="label">Nom du modèle</label><input className="input" required value={f.nom} onChange={maj("nom")} placeholder="Galaxy A15 128 Go" /></div>
          <div><label className="label">Référence</label><input className="input font-mono" required value={f.reference} onChange={maj("reference")} placeholder="SM-A155F" /></div>
          <div><label className="label">Année de sortie</label><input className="input" type="number" value={f.annee_sortie} onChange={maj("annee_sortie")} /></div>
          <div><label className="label">État</label>
            <select className="input" value={f.statut} onChange={maj("statut")}>
              <option value="BROUILLON">Brouillon (pas publié)</option>
              <option value="PRET">Prête : publier ce soir</option>
            </select></div>
        </div>

        {/* Assistant de recherche (téléphones) */}
        {f.type_produit === "TEL" && (
          <div className="rounded-2xl border border-primary/30 bg-primary/5 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm"><b>Assistant de recherche</b> : cherche la fiche technique sur les sites des fabricants
                (Apple, Samsung, Google, Tecno, Infinix…) à partir de la marque et du nom.</p>
              <button type="button" className="btn-primary btn-sm" disabled={recherche.enCours} onClick={lancerRecherche}>
                {recherche.enCours ? "Recherche en cours (1 à 2 min)…" : "🔎 Rechercher"}
              </button>
            </div>
            {recherche.resultat && <Proposition r={recherche.resultat} piecesChoisies={piecesChoisies} setPiecesChoisies={setPiecesChoisies}
              onAppliquer={appliquerProposition} onImporterPhoto={importerPhoto} onCreerPieces={creerPieces} />}
          </div>
        )}

        <div><label className="label">Description</label>
          <textarea className="input" rows={3} value={f.description} onChange={maj("description")} /></div>
        <div><label className="label">Caractéristiques (une par ligne, « Libellé : valeur »)</label>
          <textarea className="input font-mono text-sm" rows={8} value={f.caracteristiques} onChange={maj("caracteristiques")}
            placeholder={"Écran : 6,5 pouces\nStockage : 128 Go"} /></div>

        {/* Photo */}
        <div className="flex flex-wrap items-center gap-4">
          {f.photo_url ? <img src={f.photo_url} alt="" className="h-24 w-24 rounded-xl border object-contain" /> : <span className="flex h-24 w-24 items-center justify-center rounded-xl bg-gray-100 text-3xl">📱</span>}
          <label className="btn-outline btn-sm cursor-pointer">
            Envoyer une photo<input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={envoyerPhoto} />
          </label>
        </div>

        {/* Compatibilités (pièces et accessoires) */}
        {f.type_produit !== "TEL" && (
          <div>
            <label className="label">Téléphones compatibles ({f.modeles_compatibles.length})</label>
            <input className="input mb-2" placeholder="Filtrer les téléphones…" value={filtreTel} onChange={(e) => setFiltreTel(e.target.value)} />
            <div className="max-h-48 overflow-y-auto rounded-xl border border-gray-200 p-2">
              {telFiltres.map((t) => (
                <label key={t.id} className="flex items-center gap-2 py-0.5 text-sm">
                  <input type="checkbox" checked={f.modeles_compatibles.includes(t.id)}
                    onChange={(e) => setF({ ...f, modeles_compatibles: e.target.checked
                      ? [...f.modeles_compatibles, t.id] : f.modeles_compatibles.filter((x) => x !== t.id) })} />
                  {t.marque} {t.nom}
                </label>
              ))}
              {telFiltres.length === 0 && <p className="text-sm text-gray-500">Aucun téléphone.</p>}
            </div>
          </div>
        )}

        <div><label className="label">Sources (adresses des pages, une par ligne)</label>
          <textarea className="input text-sm" rows={2} value={f.sources} onChange={maj("sources")} /></div>

        <div className="flex justify-end gap-2">
          <button type="button" className="btn-outline" onClick={onFermer}>Fermer</button>
          <button className="btn-primary" disabled={envoi}>{envoi ? "Enregistrement…" : "Enregistrer"}</button>
        </div>
      </form>
    </Modal>
  );
}

// Nom du site d'une adresse (« www.samsung.com »), sans planter si l'adresse est mal formée
function nomDeSite(adresse) {
  try {
    return new URL(adresse).hostname;
  } catch {
    return adresse;
  }
}

// Proposition renvoyée par l'assistant, à relire avant de l'appliquer
function Proposition({ r, piecesChoisies, setPiecesChoisies, onAppliquer, onImporterPhoto, onCreerPieces }) {
  if (!r.trouve) {
    return <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Modèle non trouvé ou ambigu. {r.remarques}</p>;
  }
  return (
    <div className="mt-3 space-y-3 rounded-xl bg-white p-3 text-sm">
      <p className="font-semibold">{r.marque} {r.nom} {r.reference_fabricant && `(${r.reference_fabricant})`} {r.annee_sortie ? `· ${r.annee_sortie}` : ""}</p>
      <ul className="list-inside list-disc text-gray-700">{(r.caracteristiques || []).map((c) => <li key={c}>{c}</li>)}</ul>
      {r.remarques && <p className="text-amber-800">⚠ {r.remarques}</p>}
      {r.photo_url && (
        <div className="flex items-center gap-3">
          <img src={r.photo_url} alt="" className="h-20 w-20 rounded-lg border object-contain" />
          <button type="button" className="btn-outline btn-sm" onClick={() => onImporterPhoto(r.photo_url)}>Importer cette photo</button>
        </div>
      )}
      {r.sources?.length > 0 && (
        <p className="text-xs text-gray-500">Sources : {r.sources.map((s) => <a key={s} href={s} target="_blank" rel="noreferrer" className="mr-2 underline">{nomDeSite(s)}</a>)}</p>
      )}
      <button type="button" className="btn-primary btn-sm" onClick={onAppliquer}>Recopier dans la fiche</button>
      {r.pieces_detachees?.length > 0 && (
        <div className="border-t pt-3">
          <p className="mb-1 font-semibold">Pièces détachées courantes</p>
          {r.pieces_detachees.map((p) => (
            <label key={p} className="flex items-center gap-2">
              <input type="checkbox" checked={piecesChoisies.includes(p)}
                onChange={(e) => setPiecesChoisies(e.target.checked ? [...piecesChoisies, p] : piecesChoisies.filter((x) => x !== p))} />
              {p}
            </label>
          ))}
          <button type="button" className="btn-outline btn-sm mt-2" disabled={!piecesChoisies.length} onClick={onCreerPieces}>
            Créer ces pièces (brouillons compatibles)
          </button>
        </div>
      )}
    </div>
  );
}
