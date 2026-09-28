import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { aLeRole, useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { date, dateHeure, montant, prix } from "@/lib/format";
import { STATUTS_COMMANDE, STATUTS_SAV } from "@/lib/statuts";
import Badge from "@/components/Badge";
import Chargement from "@/components/Chargement";
import EnTetePage from "@/components/EnTetePage";

// Page d'accueil du back-office : indicateurs clés, ventes des 30 derniers
// jours et listes de ce qui attend une action.
export default function TableauDeBord() {
  const { user, boutique } = useAuth();
  const [donnees, setDonnees] = useState(null);
  const [erreur, setErreur] = useState("");

  // Le technicien ne voit que l'atelier (réparations) et les alertes de stock
  const vendeur = aLeRole(user, "gerant", "vendeur");
  const devise = boutique?.devise || "FCFA";

  // Chargement de tous les indicateurs en une seule requête
  useEffect(() => {
    apiClient.get("/tableau-de-bord")
      .then(({ data }) => setDonnees(data))
      .catch((err) => setErreur(messageErreur(err, "Impossible de charger le tableau de bord")));
  }, []);

  if (erreur) return <p className="card text-red-600">{erreur}</p>;
  if (!donnees) return <Chargement plein />;

  // Tuiles d'indicateurs : libellé, valeur, précision, lien, mise en avant
  const tuiles = vendeur
    ? [
      { libelle: "CA HT du mois", valeur: prix(donnees.ca_mois_ht, devise), detail: `${donnees.nb_factures_mois} facture(s) validée(s)`, lien: "/gestion/documents?type=FAC&statut=VALIDE", couleur: "text-primary" },
      { libelle: "Encaissé ce mois", valeur: prix(donnees.encaisse_mois, devise), detail: "règlements des factures du mois", lien: "/gestion/documents?type=FAC&statut=VALIDE", couleur: "text-green-700" },
      { libelle: "Factures validées (mois)", valeur: donnees.nb_factures_mois, detail: "depuis le 1er du mois", lien: "/gestion/documents?type=FAC&statut=VALIDE" },
      { libelle: "Factures en brouillon", valeur: donnees.brouillons, detail: "à valider", lien: "/gestion/documents?type=FAC&statut=BROUILLON", alerte: donnees.brouillons > 0 },
      { libelle: "Commandes à traiter", valeur: donnees.nb_commandes_a_traiter, detail: "reçues, confirmées ou en préparation", lien: "/gestion/commandes", alerte: donnees.nb_commandes_a_traiter > 0 },
      { libelle: "Réparations en cours", valeur: donnees.nb_dossiers_en_cours, detail: donnees.nb_dossiers_en_retard ? `dont ${donnees.nb_dossiers_en_retard} en retard` : "aucune en retard", lien: "/gestion/maintenance", alerte: donnees.nb_dossiers_en_retard > 0 },
      { libelle: "Produits en alerte", valeur: donnees.nb_produits_alerte, detail: "stock au seuil ou en dessous", lien: "/gestion/stock", alerte: donnees.nb_produits_alerte > 0 },
      { libelle: "Demandes de conseil", valeur: donnees.conversations_attente, detail: "en attente de réponse", lien: "/gestion/messagerie", alerte: donnees.conversations_attente > 0 },
    ]
    : [
      { libelle: "Réparations en cours", valeur: donnees.nb_dossiers_en_cours, detail: "dossiers non restitués", lien: "/gestion/maintenance" },
      { libelle: "Réparations en retard", valeur: donnees.nb_dossiers_en_retard, detail: "date prévue dépassée", lien: "/gestion/maintenance", alerte: donnees.nb_dossiers_en_retard > 0 },
      { libelle: "Produits en alerte", valeur: donnees.nb_produits_alerte, detail: "stock au seuil ou en dessous", lien: "/gestion/produits", alerte: donnees.nb_produits_alerte > 0 },
    ];

  return (
    <div>
      {/* En-tête avec les raccourcis vers les saisies les plus fréquentes */}
      <EnTetePage titre={`Bonjour ${user?.nom || ""}`}
        sousTitre={`${boutique?.nom} · ${new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}`}>
        {vendeur && <Link to="/gestion/documents/nouveau?type=FAC" className="btn-primary btn-sm">+ Nouvelle facture</Link>}
        {vendeur && <Link to="/gestion/documents/nouveau?type=PRO" className="btn-outline btn-sm">+ Nouvelle proforma</Link>}
        <Link to="/gestion/maintenance/nouveau" className="btn-accent btn-sm">🔧 Dépôt SAV</Link>
        {vendeur && <Link to="/gestion/stock/bons/nouveau" className="btn-outline btn-sm">🚚 Réception fournisseur</Link>}
      </EnTetePage>

      {/* Tuiles d'indicateurs (2 colonnes sur téléphone, 4 sur grand écran) */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tuiles.map((t) => (
          <Link key={t.libelle} to={t.lien}
            className={`card flex flex-col gap-1 p-4 transition hover:border-primary hover:shadow-md ${t.alerte ? "border-amber-300 bg-amber-50" : ""}`}>
            <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">{t.libelle}</span>
            <span className={`text-lg font-extrabold sm:text-2xl ${t.couleur || (t.alerte ? "text-amber-700" : "text-ink")}`}>{t.valeur}</span>
            <span className="text-xs text-gray-500">{t.detail}</span>
          </Link>
        ))}
      </div>

      {/* Graphique des ventes (réservé à la vente) */}
      {vendeur && (
        <section className="card mt-6">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-bold">Ventes des 30 derniers jours <span className="text-sm font-normal text-gray-500">(factures validées, HT)</span></h2>
            <span className="text-sm text-gray-600">Total : <b>{prix(donnees.ventes_30_jours.reduce((s, j) => s + j.total_ht, 0), devise)}</b></span>
          </div>
          <GraphiqueVentes jours={donnees.ventes_30_jours} devise={devise} />
        </section>
      )}

      {/* Listes cliquables de ce qui attend une action */}
      <div className={`mt-6 grid gap-6 lg:grid-cols-2 ${vendeur ? "2xl:grid-cols-3" : ""}`}>
        {vendeur && (
          <Bloc titre="Commandes à traiter" lien="/gestion/commandes" nombre={donnees.nb_commandes_a_traiter}
            vide="Aucune commande en attente." elements={donnees.commandes_a_traiter}>
            {(c) => (
              <Link key={c.id} to={`/gestion/commandes/${c.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{c.numero} <span className="font-normal text-gray-500">· {c.client?.nom}</span></p>
                  <p className="text-xs text-gray-500">{dateHeure(c.date)} · {prix(c.total, devise)}</p>
                </div>
                <Badge table={STATUTS_COMMANDE} statut={c.statut} className="shrink-0" />
              </Link>
            )}
          </Bloc>
        )}

        <Bloc titre="Réparations en cours" lien="/gestion/maintenance" nombre={donnees.nb_dossiers_en_cours}
          vide="Aucune réparation en cours." elements={donnees.dossiers_en_cours}>
          {(d) => {
            // En retard : date prévue dépassée et appareil pas encore prêt
            const retard = d.date_prevue && d.date_prevue < new Date().toISOString().slice(0, 10) && !["PRET", "IRREPARABLE"].includes(d.statut);
            return (
              <Link key={d.id} to={`/gestion/maintenance/${d.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{d.numero} <span className="font-normal text-gray-500">· {d.marque} {d.modele}</span></p>
                  <p className={`text-xs ${retard ? "font-semibold text-red-600" : "text-gray-500"}`}>
                    {d.client?.nom}{d.date_prevue ? ` · prévu le ${date(d.date_prevue)}` : ""}{retard ? " — en retard" : ""}
                  </p>
                </div>
                <Badge table={STATUTS_SAV} statut={d.statut} className="shrink-0" />
              </Link>
            );
          }}
        </Bloc>

        <Bloc titre="Stock en alerte" lien={vendeur ? "/gestion/stock" : "/gestion/produits"} nombre={donnees.nb_produits_alerte}
          vide="Aucun produit en alerte. 👍" elements={donnees.produits_alerte}>
          {(p) => (
            <Link key={p.id} to={`/gestion/produits/${p.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50">
              <div className="min-w-0">
                <p className="truncate font-semibold">{p.nom}</p>
                <p className="text-xs text-gray-500">{p.reference} · seuil {p.stock_alerte}</p>
              </div>
              <span className={`badge shrink-0 ${p.stock <= 0 ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-800"}`}>{p.stock <= 0 ? "Épuisé" : `${p.stock} en stock`}</span>
            </Link>
          )}
        </Bloc>
      </div>
    </div>
  );
}

// Carte contenant une liste (elements), avec un lien « Tout voir ».
// children est une fonction qui dessine une ligne à partir d'un élément.
function Bloc({ titre, lien, nombre, vide, elements, children }) {
  return (
    <section className="card overflow-hidden p-0">
      <div className="flex items-center justify-between gap-2 border-b border-gray-100 px-4 py-3">
        <h2 className="flex min-w-0 items-center gap-2 font-bold">
          <span className="truncate">{titre}</span>
          <span className="shrink-0 rounded-full bg-gray-100 px-2 text-xs text-gray-600">{nombre}</span>
        </h2>
        <Link to={lien} className="shrink-0 whitespace-nowrap text-sm font-semibold text-primary">Tout voir →</Link>
      </div>
      {elements.length
        ? <div className="divide-y divide-gray-100">{elements.map(children)}</div>
        : <p className="px-4 py-6 text-center text-sm text-gray-500">{vide}</p>}
    </section>
  );
}

// Graphique en barres dessiné en SVG (sans bibliothèque).
// Une barre par jour ; survoler une barre affiche la date et le montant (infobulle).
function GraphiqueVentes({ jours, devise }) {
  // Dimensions du dessin (le SVG s'étire ensuite à la largeur de l'écran)
  const largeur = 720;
  const hauteur = 200;
  const marge = { haut: 8, bas: 2, gauche: 4, droite: 4 };
  const zoneH = hauteur - marge.haut - marge.bas;
  const pas = (largeur - marge.gauche - marge.droite) / Math.max(jours.length, 1);
  const largeurBarre = Math.max(pas - 4, 2); // 4 unités d'espace entre deux barres

  // Échelle verticale : la meilleure journée occupe toute la hauteur
  const maximum = Math.max(...jours.map((j) => j.total_ht), 0);
  const echelle = (v) => (maximum > 0 ? (v / maximum) * zoneH : 0);
  const aujourdhuiIso = jours.length ? jours[jours.length - 1].date : "";

  if (maximum === 0) {
    return <p className="rounded-xl bg-gray-50 py-10 text-center text-sm text-gray-500">Aucune facture validée sur les 30 derniers jours.</p>;
  }

  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-gray-500">
        <span>Meilleur jour : {prix(maximum, devise)}</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-accent" /> aujourd'hui</span>
      </div>
      <svg viewBox={`0 0 ${largeur} ${hauteur}`} className="h-44 w-full sm:h-56" preserveAspectRatio="none" role="img" aria-label="Ventes par jour sur 30 jours">
        {/* Lignes de repère discrètes (moitié et maximum) */}
        {[0.5, 1].map((r) => (
          <line key={r} x1={marge.gauche} x2={largeur - marge.droite} y1={marge.haut + zoneH * (1 - r)} y2={marge.haut + zoneH * (1 - r)}
            stroke="#e5e7eb" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
        ))}
        {/* Ligne de base */}
        <line x1={marge.gauche} x2={largeur - marge.droite} y1={marge.haut + zoneH} y2={marge.haut + zoneH} stroke="#d1d5db" vectorEffect="non-scaling-stroke" />
        {jours.map((j, i) => {
          const h = echelle(j.total_ht);
          const x = marge.gauche + i * pas + (pas - largeurBarre) / 2;
          const y = marge.haut + zoneH - h;
          const estAujourdhui = j.date === aujourdhuiIso;
          return (
            <g key={j.date} className="group">
              <title>{`${date(j.date)} : ${montant(j.total_ht)} ${devise} HT`}</title>
              {/* Zone de survol pleine hauteur (plus facile à viser que la barre) */}
              <rect x={marge.gauche + i * pas} y={marge.haut} width={pas} height={zoneH} className="fill-transparent group-hover:fill-gray-100" />
              {h > 0 && (
                <path d={cheminBarre(x, y, largeurBarre, h, Math.min(4, largeurBarre / 2, h))}
                  className={estAujourdhui ? "fill-accent" : "fill-primary group-hover:fill-primary-dark"} />
              )}
            </g>
          );
        })}
      </svg>
      {/* Dates sous le graphique (en HTML pour ne pas être déformées) : une tous les 5 jours */}
      <div className="relative mt-1 h-4 text-[11px] text-gray-500">
        {jours.map((j, i) => (i % 5 === 0 || i === jours.length - 1) && (
          <span key={j.date} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${((i + 0.5) / jours.length) * 100}%` }}>
            {i === jours.length - 1 ? "Auj." : `${j.date.slice(8, 10)}/${j.date.slice(5, 7)}`}
          </span>
        ))}
      </div>
    </div>
  );
}

// Tracé d'une barre au sommet arrondi (rayon r), posée sur la ligne de base.
function cheminBarre(x, y, l, h, r) {
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + l - r} Q${x + l},${y} ${x + l},${y + r} V${y + h} Z`;
}
