import ProduitSelect from "@/components/ProduitSelect";
import { montant } from "@/lib/format";
import { nombre } from "./calculs";

// Grille des colonnes du tableau de lignes (très grand écran) :
// Désignation | Qté | P.U. | Remise % | TVA % | Total | (supprimer)
const COLONNES = "xl:grid-cols-[minmax(0,1fr)_4.5rem_7rem_5rem_5rem_7rem_2.5rem]";

let compteur = 0;
/** Identifiant local d'une ligne (sert seulement à React pour suivre les lignes). */
export function nouvelleCle() {
  compteur += 1;
  return `l${Date.now()}-${compteur}`;
}

/** Ligne vide (« ligne libre ») ou ligne issue d'un produit du catalogue. */
export function ligneDepuisProduit(p) {
  if (!p) return { cle: nouvelleCle(), produit_id: null, reference: "", designation: "", quantite: "1", prix_unitaire: "", remise_pct: "", taux_tva: "", nouvelle: true };
  return {
    cle: nouvelleCle(), produit_id: p.id, reference: p.reference || "", designation: p.nom, quantite: "1",
    prix_unitaire: String(p.prix_vente ?? 0), remise_pct: "", taux_tva: "",
    stock: p.stock, stockable: p.type_produit !== "SER",
  };
}

// Tableau des lignes d'une facture / proforma.
// - lignesCalculees : lignes avec leurs montants (aperçu calculé par la page) ;
// - lectureSeule : document validé ou annulé, on affiche sans champs de saisie ;
// - onChange(nouvellesLignes) : appelé à chaque modification.
export default function LignesDocument({ lignesCalculees, lectureSeule, prixTtc, tauxDefaut, estFacture, onChange }) {
  // Modifie un champ d'une ligne (les autres lignes ne changent pas)
  function modifier(cle, champ, valeur) {
    onChange(lignesCalculees.map((l) => (l.cle === cle ? { ...l, [champ]: valeur, nouvelle: false } : l)));
  }
  function supprimer(cle) {
    onChange(lignesCalculees.filter((l) => l.cle !== cle));
  }

  // Ajout d'un produit : s'il est déjà dans la liste au même prix, on augmente sa quantité
  function ajouterProduit(p) {
    // On retire le focus du champ de recherche : ProduitSelect ne rouvre sa liste
    // qu'en recevant le focus, un nouveau clic permet ainsi d'ajouter un autre produit
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    const existante = lignesCalculees.find((l) => l.produit_id === p.id && nombre(l.prix_unitaire) === p.prix_vente && !nombre(l.remise_pct));
    if (existante) {
      modifier(existante.cle, "quantite", String(nombre(existante.quantite, 0) + 1));
      return;
    }
    onChange([...lignesCalculees, ligneDepuisProduit(p)]);
  }

  // Montant affiché dans la colonne « Total » : TTC si les prix sont saisis TTC, sinon HT
  const totalLigne = (l) => (prixTtc ? l.montant_ttc : l.montant_ht);
  const entete = `Total ${prixTtc ? "TTC" : "HT"}`;

  return (
    <div>
      {/* En-têtes de colonnes (écran large seulement) */}
      <div className={`hidden gap-2 border-b border-gray-200 pb-2 text-xs font-semibold uppercase text-gray-500 xl:grid ${COLONNES}`}>
        <span>Désignation</span><span className="text-right">Qté</span><span className="text-right">P.U. {prixTtc ? "TTC" : "HT"}</span>
        <span className="text-right">Remise %</span><span className="text-right">TVA %</span><span className="text-right">{entete}</span><span />
      </div>

      {lignesCalculees.length === 0 && (
        <p className="py-8 text-center text-sm text-gray-500">
          {lectureSeule ? "Aucune ligne." : "Aucune ligne pour l'instant : ajoutez un produit du catalogue ou une ligne libre ci-dessous."}
        </p>
      )}

      {/* Une ligne = une rangée (écran large) ; sur tablette et téléphone,
          la désignation est au-dessus et les chiffres en dessous */}
      <div className="divide-y divide-gray-100">
        {lignesCalculees.map((l, index) => {
          // Alerte si la quantité dépasse le stock connu (produit ajouté pendant cette saisie)
          const stockInsuffisant = estFacture && !lectureSeule && l.stockable && l.stock !== undefined && nombre(l.quantite, 0) > l.stock;
          return (
            <div key={l.cle} className={`grid grid-cols-4 gap-2 py-3 sm:grid-cols-12 xl:items-start ${COLONNES}`}>
              {/* Désignation (+ référence du produit) */}
              <div className="col-span-4 sm:col-span-12 xl:col-span-1">
                <span className="mb-1 block text-xs font-semibold text-gray-500 xl:hidden">Ligne {index + 1}</span>
                {lectureSeule ? (
                  <p className="font-medium">{l.designation}</p>
                ) : (
                  <input className="input py-2" value={l.designation} placeholder={l.produit_id ? "Désignation" : "Désignation (ex. Frais de livraison)"} required
                    autoFocus={l.nouvelle} maxLength={255} onChange={(e) => modifier(l.cle, "designation", e.target.value)} aria-label="Désignation" />
                )}
                <p className="mt-0.5 text-xs text-gray-500">
                  {l.produit_id ? `Réf. ${l.reference || "—"}` : "Ligne libre"}
                  {stockInsuffisant && <span className="ml-2 font-semibold text-amber-700">⚠ stock disponible : {l.stock}</span>}
                </p>
              </div>

              <Champ libelle="Qté" lectureSeule={lectureSeule} valeur={l.quantite} texte={l.quantite}
                min={1} step={1} onChange={(v) => modifier(l.cle, "quantite", v)} />
              <Champ libelle={`P.U. ${prixTtc ? "TTC" : "HT"}`} large lectureSeule={lectureSeule} valeur={l.prix_unitaire} texte={montant(l.prix_unitaire)}
                min={0} step={1} onChange={(v) => modifier(l.cle, "prix_unitaire", v)} />
              <Champ libelle="Remise %" lectureSeule={lectureSeule} valeur={l.remise_pct} texte={nombre(l.remise_pct) ? `${l.remise_pct} %` : "—"}
                min={0} max={100} step="any" placeholder="0" onChange={(v) => modifier(l.cle, "remise_pct", v)} />
              <Champ libelle="TVA %" lectureSeule={lectureSeule} valeur={l.taux_tva} texte={`${l.taux_effectif} %`}
                min={0} max={100} step="any" placeholder={String(tauxDefaut)} onChange={(v) => modifier(l.cle, "taux_tva", v)} />

              {/* Total de la ligne, recalculé en direct */}
              <div className="col-span-2 text-right xl:col-span-1">
                <span className="block text-xs text-gray-500 xl:hidden">{entete}</span>
                <span className="block py-2 font-semibold">{montant(totalLigne(l))}</span>
              </div>

              {/* Suppression de la ligne */}
              <div className="flex items-end justify-end sm:col-span-1 xl:items-start">
                {!lectureSeule && (
                  <button type="button" onClick={() => supprimer(l.cle)} title="Supprimer la ligne" aria-label="Supprimer la ligne"
                    className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-600">🗑</button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Ajout de lignes : produit du catalogue ou ligne libre */}
      {!lectureSeule && (
        <div className="mt-3 flex flex-col gap-2 border-t border-gray-100 pt-3 sm:flex-row">
          <div className="flex-1"><ProduitSelect onChoisir={ajouterProduit} /></div>
          <button type="button" className="btn-outline" onClick={() => onChange([...lignesCalculees, ligneDepuisProduit(null)])}>+ Ligne libre</button>
        </div>
      )}
    </div>
  );
}

// Cellule numérique : champ de saisie, ou simple texte en lecture seule.
function Champ({ libelle, lectureSeule, valeur, texte, onChange, large = false, ...attributs }) {
  return (
    <div className={`${large ? "col-span-2 sm:col-span-3" : "col-span-1 sm:col-span-2"} xl:col-span-1`}>
      <span className="mb-1 block text-xs text-gray-500 xl:hidden">{libelle}</span>
      {lectureSeule ? (
        <span className="block py-2 text-right">{texte}</span>
      ) : (
        <input className="input px-2 py-2 text-right" type="number" inputMode="decimal" value={valeur ?? ""} aria-label={libelle}
          onChange={(e) => onChange(e.target.value)} {...attributs} />
      )}
    </div>
  );
}
