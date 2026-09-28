import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure, prix } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import EnTetePage from "@/components/EnTetePage";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";

// Libellés et couleurs des statuts de campagne et d'envoi
const STATUTS = {
  EN_COURS: ["En cours", "bg-amber-100 text-amber-800"],
  TERMINEE: ["Terminée", "bg-green-100 text-green-800"],
  ENVOYE: ["Envoyé", "bg-green-100 text-green-800"],
  ECHEC: ["Échec", "bg-red-100 text-red-700"],
  NON_ENVOYE: ["Non envoyé", "bg-gray-100 text-gray-600"],
};
function Statut({ valeur }) {
  const [libelle, classe] = STATUTS[valeur] || [valeur, "bg-gray-100 text-gray-600"];
  return <span className={`badge ${classe}`}>{libelle}</span>;
}

// ---------------------------------------------------------------------------
// Page « Carrousel WhatsApp » : la boutique choisit 2 à 10 produits (photo, nom,
// prix), écrit un message d'introduction, coche ses clients qui ont ACCEPTÉ les
// offres WhatsApp, voit l'aperçu du message et l'envoie. Historique en bas.
// ---------------------------------------------------------------------------
export default function Carrousel() {
  const toast = useToast();
  const { boutique } = useAuth();

  // Données du serveur
  const [etat, setEtat] = useState(null); // {configure, cartes_min, cartes_max, nb_consentants, mois_envoyes...}
  const [produits, setProduits] = useState([]); // produits en vente avec photo
  const [clients, setClients] = useState([]); // clients ayant donné leur accord
  const [campagnes, setCampagnes] = useState([]); // historique des envois

  // Saisie de l'utilisateur
  const [choix, setChoix] = useState([]); // ids des produits choisis, DANS L'ORDRE des cartes
  const [message, setMessage] = useState("");
  const [destinataires, setDestinataires] = useState(new Set()); // ids des clients cochés
  const [filtreProduit, setFiltreProduit] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [detail, setDetail] = useState(null); // campagne ouverte dans l'historique

  // Chargement de toutes les données de l'écran
  const charger = useCallback(async () => {
    try {
      const [e, p, c, h] = await Promise.all([
        apiClient.get("/boutique/carrousel"), apiClient.get("/boutique/carrousel/produits"),
        apiClient.get("/boutique/carrousel/destinataires"), apiClient.get("/boutique/carrousel/campagnes"),
      ]);
      setEtat(e.data); setProduits(p.data); setClients(c.data); setCampagnes(h.data);
    } catch (err) {
      toast.erreur(messageErreur(err, "Impossible de charger le carrousel"));
    }
  }, [toast]);
  useEffect(() => { charger(); }, [charger]);

  // Produits choisis, dans l'ordre des cartes (pour l'aperçu)
  const cartes = useMemo(() => choix.map((id) => produits.find((p) => p.id === id)).filter(Boolean), [choix, produits]);
  const produitsFiltres = produits.filter((p) => `${p.nom} ${p.marque}`.toLowerCase().includes(filtreProduit.toLowerCase()));

  if (!etat) return <Chargement />;
  const { configure, cartes_min: min, cartes_max: max, destinataires_max: maxDest } = etat;

  // Coche / décoche un produit (au plus « max » cartes)
  function basculerProduit(id) {
    setChoix((c) => {
      if (c.includes(id)) return c.filter((x) => x !== id);
      if (c.length >= max) { toast.erreur(`${max} produits au maximum dans un carrousel`); return c; }
      return [...c, id];
    });
  }
  // Déplace une carte vers la gauche (-1) ou la droite (+1) dans le carrousel
  function deplacer(index, sens) {
    setChoix((c) => {
      const j = index + sens;
      if (j < 0 || j >= c.length) return c;
      const copie = [...c];
      [copie[index], copie[j]] = [copie[j], copie[index]];
      return copie;
    });
  }
  // Coche / décoche un destinataire, ou tous d'un coup
  function basculerClient(id) {
    setDestinataires((d) => {
      const n = new Set(d);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }
  const tousCoches = clients.length > 0 && destinataires.size === Math.min(clients.length, maxDest);
  function toutCocher() {
    setDestinataires(tousCoches ? new Set() : new Set(clients.slice(0, maxDest).map((c) => c.id)));
  }

  // Conditions pour pouvoir envoyer
  const pret = configure && cartes.length >= min && message.trim().length >= 3 && destinataires.size > 0;

  async function envoyer() {
    if (!window.confirm(`Envoyer ce carrousel de ${cartes.length} produits à ${destinataires.size} client(s) par WhatsApp ?`)) return;
    setEnvoi(true);
    try {
      const { data } = await apiClient.post("/boutique/carrousel/envoyer", {
        produit_ids: choix, message: message.trim(), client_ids: [...destinataires],
      });
      toast.succes(`Envoi lancé vers ${data.nb_destinataires} client(s). Le résultat apparaît dans l'historique.`);
      setChoix([]); setMessage(""); setDestinataires(new Set());
      // L'envoi se fait en arrière-plan : on recharge l'historique quelques secondes plus tard
      setTimeout(charger, 4000);
      charger();
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi impossible"));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <div className="space-y-6">
      <EnTetePage titre="Carrousel WhatsApp" sousTitre="Envoyez vos produits en carrousel photo à vos clients sur WhatsApp">
        <span className="puce text-gray-500">{etat.mois_envoyes} message(s) envoyé(s) ce mois</span>
      </EnTetePage>

      {/* Service pas encore activé : l'écran reste utilisable en préparation, mais l'envoi est grisé */}
      {!configure && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <b>Bientôt disponible.</b> Vous pouvez déjà préparer votre carrousel et recueillir l'accord de vos clients :
          l'envoi sera activé dès que le service WhatsApp de la plateforme adLyn sera ouvert.
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          {/* ---------- Étape 1 : choix des produits ---------- */}
          <section className="card space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="surtitre">Étape 1</p>
                <h2 className="text-lg font-bold">Produits du carrousel <span className="text-sm font-normal text-gray-500">({choix.length}/{max}, minimum {min})</span></h2>
              </div>
              <input className="input max-w-xs" placeholder="🔍 Rechercher un produit" value={filtreProduit} onChange={(e) => setFiltreProduit(e.target.value)} />
            </div>
            {produits.length === 0 ? (
              <p className="text-sm text-gray-500">
                Aucun produit utilisable : il faut des produits <b>visibles sur la vitrine, avec un prix et une photo</b>.
                Ajoutez des photos depuis le <Link to="/gestion/produits" className="font-semibold text-primary">catalogue</Link>.
              </p>
            ) : (
              <div className="grid max-h-[26rem] grid-cols-2 gap-3 overflow-y-auto pr-1 sm:grid-cols-3 lg:grid-cols-4">
                {produitsFiltres.map((p) => {
                  const rang = choix.indexOf(p.id);
                  return (
                    <button key={p.id} type="button" onClick={() => basculerProduit(p.id)}
                      className={`relative overflow-hidden rounded-xl border-2 bg-white text-left transition ${rang >= 0 ? "border-primary shadow-md" : "border-gray-200 hover:border-gray-300"}`}>
                      {/* Numéro de la carte dans le carrousel */}
                      {rang >= 0 && <span className="absolute left-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">{rang + 1}</span>}
                      <img src={p.image_url} alt="" className="aspect-square w-full bg-gray-50 object-contain" />
                      <div className="p-2">
                        <p className="truncate text-sm font-semibold">{p.nom}</p>
                        <p className="text-xs font-semibold text-accent">{prix(p.prix_vente, boutique?.devise)}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {/* ---------- Étape 2 : message d'introduction ---------- */}
          <section className="card space-y-2">
            <p className="surtitre">Étape 2</p>
            <h2 className="text-lg font-bold">Message d'introduction</h2>
            <textarea className="input" rows={3} maxLength={500} placeholder="Ex. : Découvrez nos nouveautés de la semaine, livraison offerte à Ouagadougou !"
              value={message} onChange={(e) => setMessage(e.target.value)} />
            <p className="text-right text-xs text-gray-400">{message.length}/500</p>
          </section>

          {/* ---------- Étape 3 : destinataires (clients ayant accepté) ---------- */}
          <section className="card space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="surtitre">Étape 3</p>
                <h2 className="text-lg font-bold">Destinataires <span className="text-sm font-normal text-gray-500">({destinataires.size} sur {clients.length})</span></h2>
              </div>
              {clients.length > 0 && <button type="button" className="btn-outline btn-sm" onClick={toutCocher}>{tousCoches ? "Tout décocher" : "Tout cocher"}</button>}
            </div>
            <p className="text-xs text-gray-500">
              Seuls les clients ayant <b>accepté</b> de recevoir vos offres par WhatsApp apparaissent (case cochée sur leur fiche,
              ou lors d'une commande sur votre vitrine). {maxDest} destinataires au plus par envoi.
            </p>
            {clients.length === 0 ? (
              <p className="rounded-lg bg-gray-50 p-3 text-sm text-gray-600">
                Aucun client n'a encore donné son accord. Cochez « accepte de recevoir nos offres par WhatsApp » sur la
                <Link to="/gestion/clients" className="font-semibold text-primary"> fiche de vos clients</Link> quand ils vous le confirment.
              </p>
            ) : (
              <ul className="max-h-72 divide-y divide-gray-100 overflow-y-auto rounded-lg border border-gray-200">
                {clients.map((c) => (
                  <li key={c.id}>
                    <label className="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-gray-50">
                      <input type="checkbox" checked={destinataires.has(c.id)} onChange={() => basculerClient(c.id)} />
                      <span className="flex-1 truncate text-sm font-medium">{c.nom}</span>
                      <span className="font-mono text-xs text-gray-500">{c.telephone}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        {/* ---------- Aperçu façon téléphone + bouton d'envoi ---------- */}
        <aside className="space-y-4 xl:sticky xl:top-20 xl:h-fit">
          <div className="rounded-3xl border-8 border-nuit-900 bg-[#efe7dd] p-3 shadow-xl">
            <p className="mb-2 text-center text-[11px] font-semibold text-gray-500">Aperçu WhatsApp</p>
            {/* Bulle du message */}
            <div className="rounded-lg rounded-tl-none bg-white p-3 text-sm shadow-sm">
              <p className="font-semibold">{boutique?.nom}</p>
              <p className="mt-1 whitespace-pre-line text-gray-700">{message.trim() || "Votre message d'introduction…"}</p>
            </div>
            {/* Cartes du carrousel (défilement horizontal) */}
            <div className="mt-2 flex snap-x gap-2 overflow-x-auto pb-2">
              {cartes.length === 0 && <p className="w-full py-8 text-center text-xs text-gray-500">Choisissez au moins {min} produits</p>}
              {cartes.map((p, i) => (
                <div key={p.id} className="w-44 shrink-0 snap-start overflow-hidden rounded-lg bg-white shadow-sm">
                  <img src={p.image_url} alt="" className="aspect-square w-full object-cover" />
                  <div className="p-2 text-xs">
                    <p className="truncate font-semibold">{p.nom}</p>
                    <p className="text-gray-600">{prix(p.prix_vente, boutique?.devise)}</p>
                  </div>
                  <p className="border-t border-gray-100 py-1.5 text-center text-xs font-semibold text-[#128c7e]">↗ Voir le produit</p>
                  {/* Réordonner les cartes */}
                  <div className="flex justify-between border-t border-gray-100 px-2 py-1 text-xs text-gray-400">
                    <button type="button" disabled={i === 0} onClick={() => deplacer(i, -1)} className="disabled:opacity-30" aria-label="Carte précédente">◀</button>
                    <span>{i + 1}/{cartes.length}</span>
                    <button type="button" disabled={i === cartes.length - 1} onClick={() => deplacer(i, 1)} className="disabled:opacity-30" aria-label="Carte suivante">▶</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <button type="button" className="btn-primary w-full py-3" disabled={!pret || envoi} onClick={envoyer}
            title={configure ? "" : "Bientôt disponible"}>
            {envoi ? "Envoi…" : configure ? `📤 Envoyer à ${destinataires.size} client(s)` : "📤 Envoi bientôt disponible"}
          </button>
          <p className="text-center text-xs text-gray-500">Le bouton « Voir le produit » ouvre la fiche sur votre vitrine adLyn, où le client commande et paie.</p>
        </aside>
      </div>

      {/* ---------- Historique des envois ---------- */}
      <section className="card">
        <h2 className="mb-3 text-lg font-bold">Historique des envois</h2>
        {campagnes.length === 0 ? <p className="text-sm text-gray-500">Aucun carrousel envoyé pour l'instant.</p> : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead><tr><th>Date</th><th>Message</th><th>Produits</th><th>Destinataires</th><th>Envoyés</th><th>Échecs</th><th>Statut</th><th /></tr></thead>
              <tbody>
                {campagnes.map((c) => (
                  <tr key={c.id}>
                    <td className="whitespace-nowrap">{dateHeure(c.date)}</td>
                    <td className="max-w-xs truncate">{c.message}</td>
                    <td>{c.cartes?.length}</td>
                    <td>{c.nb_destinataires}</td>
                    <td className="font-semibold text-green-700">{c.envoyes}</td>
                    <td className={c.echecs ? "font-semibold text-red-600" : ""}>{c.echecs}</td>
                    <td><Statut valeur={c.statut} /></td>
                    <td><button type="button" className="text-sm font-semibold text-primary" onClick={() => setDetail(detail?.id === c.id ? null : c)}>{detail?.id === c.id ? "Fermer" : "Détail"}</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {/* Détail d'une campagne : résultat par destinataire */}
        {detail && (
          <div className="mt-4 rounded-lg border border-gray-200 p-3">
            <p className="mb-2 text-sm font-semibold">Détail de l'envoi du {dateHeure(detail.date)} · par {detail.auteur || "—"}</p>
            <ul className="divide-y divide-gray-100 text-sm">
              {(detail.resultats || []).map((r) => (
                <li key={r.client_id} className="flex flex-wrap items-center gap-2 py-1.5">
                  <span className="flex-1">{r.nom} <span className="font-mono text-xs text-gray-500">{r.telephone}</span></span>
                  <Statut valeur={r.statut} />
                  {r.erreur && <span className="w-full text-xs text-red-600">{r.erreur}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}
