import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api";
import { Champ } from "../_atelier/communs";

// Fiche technique vide (mêmes champs que FicheTechnique dans backend/fiche_technique.py)
export const FICHE_VIDE = {
  fabricant: "", modele: "", systeme: "", version_systeme: "", batterie_mah: "", ecran_pouces: "",
  stockage_go: "", ram_go: "", appareil_photo: "", reseau: "", options: [], couleur: "", etat: "NEUF",
  annee_sortie: "",
};

/** Fiche venue du serveur -> valeurs du formulaire (null remplacé par "" pour des champs contrôlés). */
export function ficheVersFormulaire(fiche) {
  const f = { ...FICHE_VIDE };
  Object.entries(fiche || {}).forEach(([cle, valeur]) => { if (valeur !== null && valeur !== undefined) f[cle] = valeur; });
  return f;
}

/** Formulaire -> fiche envoyée au serveur : textes nettoyés, nombres convertis, vides -> null.
 *  Renvoie null si rien n'est rempli (le produit n'a alors pas de fiche technique). */
export function ficheVersApi(f) {
  const nombre = (v, entier) => {
    const n = entier ? parseInt(v, 10) : parseFloat(String(v).replace(",", "."));
    return Number.isFinite(n) ? n : null;
  };
  const fiche = {
    fabricant: f.fabricant.trim(), modele: f.modele.trim(), systeme: f.systeme || null,
    version_systeme: f.version_systeme.trim(), batterie_mah: nombre(f.batterie_mah, true),
    ecran_pouces: nombre(f.ecran_pouces), stockage_go: nombre(f.stockage_go, true), ram_go: nombre(f.ram_go),
    appareil_photo: f.appareil_photo.trim(), reseau: f.reseau || null,
    options: f.options.map((o) => o.trim()).filter(Boolean), couleur: f.couleur.trim(), etat: f.etat || "NEUF",
    annee_sortie: nombre(f.annee_sortie, true),
  };
  // Seul l'état « Neuf » (valeur par défaut) rempli : pas de fiche
  const remplie = Object.entries(fiche).some(([cle, v]) => cle !== "etat" && (Array.isArray(v) ? v.length : v))
    || fiche.etat !== "NEUF";
  return remplie ? fiche : null;
}

// Carte « Fiche technique » d'un téléphone créé par la boutique :
//  1. recherche du modèle dans le RÉFÉRENTIEL MONDIAL (liste Google Play + iPhone)
//     -> remplit fabricant, modèle, année et relie le produit à l'appareil ;
//  2. caractéristiques normalisées (système, batterie, écran, mémoire...) ;
//  3. options à cocher (+ options libres).
// Ces informations restent PRIVÉES à la boutique et s'affichent sur SA vitrine.
export default function FicheTechnique({ fiche, onFiche, referentiel, onReferentiel, nomProduit, onSuggestion, desactive }) {
  const [choix, setChoix] = useState(null); // listes de valeurs fournies par le serveur
  const [optionLibre, setOptionLibre] = useState("");

  // Listes de valeurs (systèmes, réseaux, options, états) : une seule fois
  useEffect(() => {
    apiClient.get("/produits-fiche-technique/choix").then(({ data }) => setChoix(data)).catch(() => {});
  }, []);

  const maj = (champ, valeur) => onFiche({ ...fiche, [champ]: valeur });

  // Case d'option cochée / décochée
  const basculerOption = (option) => maj("options", fiche.options.includes(option)
    ? fiche.options.filter((o) => o !== option) : [...fiche.options, option]);

  // Ajout d'une option absente de la liste (ex. « Projecteur »)
  function ajouterOptionLibre() {
    const o = optionLibre.trim();
    if (o && !fiche.options.includes(o)) maj("options", [...fiche.options, o]);
    setOptionLibre("");
  }

  // Appareil choisi dans le référentiel : on reprend son identité
  function choisirAppareil(a) {
    onReferentiel(a);
    onFiche({
      ...fiche, fabricant: a.marque, modele: a.codes_modele?.[0] || a.nom,
      annee_sortie: a.annee_sortie || fiche.annee_sortie,
      systeme: fiche.systeme || (a.marque === "Apple" ? "iOS" : "Android"),
    });
    // Nom et marque du produit proposés s'ils sont encore vides
    onSuggestion?.({ nom: `${a.marque} ${a.nom}`, marque: a.marque });
  }

  const optionsListe = choix?.options || [];
  const optionsLibres = fiche.options.filter((o) => !optionsListe.includes(o));

  return (
    <fieldset disabled={desactive} className="card space-y-4">
      <div>
        <h2 className="font-bold">📱 Fiche technique</h2>
        <p className="text-xs text-gray-500">Informations propres à votre boutique, affichées sur votre vitrine. Laissez vide ce que vous ne connaissez pas.</p>
      </div>

      {/* 1) Modèle dans le référentiel mondial */}
      <RechercheReferentiel referentiel={referentiel} nomProduit={nomProduit} onChoisir={choisirAppareil}
        onRetirer={() => onReferentiel(null)} desactive={desactive} />

      {/* 2) Caractéristiques normalisées */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Champ label="Fabricant"><input className="input" maxLength={80} value={fiche.fabricant} onChange={(e) => maj("fabricant", e.target.value)} placeholder="ex. Samsung" /></Champ>
        <Champ label="Modèle (code)"><input className="input" maxLength={80} value={fiche.modele} onChange={(e) => maj("modele", e.target.value)} placeholder="ex. SM-A155F" /></Champ>
        <Champ label="État">
          <select className="input" value={fiche.etat} onChange={(e) => maj("etat", e.target.value)}>
            {Object.entries(choix?.etats || { NEUF: "Neuf" }).map(([code, lib]) => <option key={code} value={code}>{lib}</option>)}
          </select>
        </Champ>
        <Champ label="Système d'exploitation">
          <select className="input" value={fiche.systeme} onChange={(e) => maj("systeme", e.target.value)}>
            <option value="">—</option>
            {(choix?.systemes || []).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </Champ>
        <Champ label="Version du système"><input className="input" maxLength={40} value={fiche.version_systeme} onChange={(e) => maj("version_systeme", e.target.value)} placeholder="ex. 14" /></Champ>
        <Champ label="Réseau">
          <select className="input" value={fiche.reseau} onChange={(e) => maj("reseau", e.target.value)}>
            <option value="">—</option>
            {(choix?.reseaux || []).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </Champ>
        <Champ label="Batterie (mAh)"><input className="input" type="number" min={100} max={30000} value={fiche.batterie_mah} onChange={(e) => maj("batterie_mah", e.target.value)} placeholder="ex. 5000" /></Champ>
        <Champ label="Écran (pouces)"><input className="input" type="number" min={1} max={20} step="0.01" value={fiche.ecran_pouces} onChange={(e) => maj("ecran_pouces", e.target.value)} placeholder="ex. 6.5" /></Champ>
        <Champ label="Appareil photo"><input className="input" maxLength={80} value={fiche.appareil_photo} onChange={(e) => maj("appareil_photo", e.target.value)} placeholder="ex. 50 Mpx + 2 Mpx" /></Champ>
        <Champ label="Stockage (Go)"><input className="input" type="number" min={0} max={4096} value={fiche.stockage_go} onChange={(e) => maj("stockage_go", e.target.value)} placeholder="ex. 128" /></Champ>
        <Champ label="Mémoire vive / RAM (Go)"><input className="input" type="number" min={0} max={64} step="0.5" value={fiche.ram_go} onChange={(e) => maj("ram_go", e.target.value)} placeholder="ex. 4" /></Champ>
        <Champ label="Couleur"><input className="input" maxLength={40} value={fiche.couleur} onChange={(e) => maj("couleur", e.target.value)} placeholder="ex. Noir" /></Champ>
        <Champ label="Année de sortie"><input className="input" type="number" min={1990} max={2100} value={fiche.annee_sortie} onChange={(e) => maj("annee_sortie", e.target.value)} placeholder="ex. 2024" /></Champ>
      </div>

      {/* 3) Options : cases à cocher + options libres */}
      <div>
        <p className="label">Options</p>
        <div className="flex flex-wrap gap-2">
          {optionsListe.map((o) => {
            const coche = fiche.options.includes(o);
            return (
              <button key={o} type="button" onClick={() => basculerOption(o)} aria-pressed={coche}
                className={`rounded-full border px-3 py-1 text-sm transition ${coche ? "border-primary bg-primary text-white" : "border-gray-300 bg-white text-gray-700 hover:border-primary"}`}>
                {coche ? "✓ " : ""}{o}
              </button>
            );
          })}
          {/* Options saisies librement : cliquer les retire */}
          {optionsLibres.map((o) => (
            <button key={o} type="button" onClick={() => basculerOption(o)} title="Retirer"
              className="rounded-full border border-primary bg-primary px-3 py-1 text-sm text-white">✓ {o} ✕</button>
          ))}
        </div>
        {!desactive && (
          <div className="mt-2 flex max-w-sm gap-2">
            <input className="input" maxLength={40} value={optionLibre} placeholder="Autre option…"
              onChange={(e) => setOptionLibre(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); ajouterOptionLibre(); } }} />
            <button type="button" className="btn-outline btn-sm shrink-0" onClick={ajouterOptionLibre}>+ Ajouter</button>
          </div>
        )}
      </div>
    </fieldset>
  );
}

// Recherche du modèle dans le référentiel mondial, avec liste de suggestions.
// referentiel = appareil choisi ({ cle, marque, nom, ... }) ou null.
function RechercheReferentiel({ referentiel, nomProduit, onChoisir, onRetirer, desactive }) {
  const [q, setQ] = useState("");
  const [resultats, setResultats] = useState([]);
  const [ouvert, setOuvert] = useState(false);
  const zone = useRef(null);

  // Recherche avec un petit délai pendant la frappe (au moins 2 caractères)
  useEffect(() => {
    if (q.trim().length < 2) { setResultats([]); return undefined; }
    const t = setTimeout(() => {
      apiClient.get("/referentiel", { params: { q } })
        .then(({ data }) => { setResultats(data.appareils.slice(0, 8)); setOuvert(true); })
        .catch(() => setResultats([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  // Fermeture de la liste au clic en dehors
  useEffect(() => {
    const fermer = (e) => { if (zone.current && !zone.current.contains(e.target)) setOuvert(false); };
    document.addEventListener("mousedown", fermer);
    return () => document.removeEventListener("mousedown", fermer);
  }, []);

  // Appareil déjà relié : on l'affiche avec un bouton pour le retirer
  if (referentiel) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-xl bg-green-50 px-3 py-2 text-sm text-green-900">
        <span>🌍 Relié au référentiel mondial : <b>{referentiel.marque} {referentiel.nom}</b>
          {referentiel.codes_modele?.length ? <span className="font-mono text-xs text-green-800"> ({referentiel.codes_modele.slice(0, 3).join(", ")})</span> : null}</span>
        {!desactive && <button type="button" className="ml-auto text-xs font-semibold underline" onClick={onRetirer}>Retirer le lien</button>}
      </div>
    );
  }

  return (
    <div ref={zone} className="relative">
      <Champ label="Rechercher le modèle dans la liste mondiale des appareils"
        aide="Nom ou code modèle (ex. Galaxy A15, SM-A155F, Spark 20). Le fabricant, le modèle et l'année sont remplis pour vous.">
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => resultats.length && setOuvert(true)}
          placeholder={nomProduit ? `ex. ${nomProduit}` : "Tapez au moins 2 caractères…"} autoComplete="off" />
      </Champ>
      {ouvert && q.trim().length >= 2 && (
        <ul className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-gray-200 bg-white shadow-lg">
          {resultats.length === 0 && <li className="px-3 py-2 text-sm text-gray-500">Aucun appareil trouvé : remplissez la fiche à la main.</li>}
          {resultats.map((a) => (
            <li key={a.cle}>
              <button type="button" className="w-full px-3 py-2 text-left hover:bg-gray-50"
                onClick={() => { onChoisir(a); setQ(""); setOuvert(false); }}>
                <span className="block text-sm font-semibold">{a.marque} {a.nom}{a.annee_sortie ? <span className="font-normal text-gray-500"> · {a.annee_sortie}</span> : null}</span>
                <span className="block truncate font-mono text-xs text-gray-500">{a.codes_modele?.join(" · ") || "—"}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
