import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient, EN_ARRIERE_PLAN, messageErreur } from "@/lib/api";
import { useToast } from "@/components/Toast";
import Modal from "@/components/Modal";
import Patientez from "@/components/Patientez";
import { EnTetePlateforme } from "./_plateforme/composants";

// ============================================================================
// ONGLET « USAGE » DE LA PLATEFORME (lot 25) — super-administrateur uniquement
// ============================================================================
// Historique de TOUTES les connexions (personnel des boutiques et administrateur) :
//   - pastille de présence en tête de ligne (verte / orange / rouge), rafraîchie
//     toutes les 30 s par une requête de FOND (en-tête X-Adlyn-Fond : elle ne
//     compte pas comme une activité de l'administrateur) ;
//   - date/heure (Ouagadougou), adresse IP, compte et sa boutique, rôle, état de
//     l'abonnement de la boutique, méthode et appareil, état de l'IP ;
//   - boutons Bloquer / Autoriser sur chaque ligne ;
// puis la liste « Blocages en cours », le contact affiché sur la page « Accès
// momentanément suspendu » et le journal des actions.
// Les règles côté serveur sont décrites dans backend/blocages_acces.py.
// ============================================================================

const RAFRAICHISSEMENT_PRESENCE_MS = 30_000;

// Couleurs des pastilles (mêmes règles que SAWALI)
const PASTILLES = {
  vert: { classe: "bg-green-500", texte: "Connecté et actif (activité dans les 5 dernières minutes)" },
  orange: { classe: "bg-amber-500", texte: "Connecté, sans activité depuis 5 à 10 min" },
  rouge: { classe: "bg-red-500", texte: "Plus de 10 min sans activité, ou déconnecté" },
};

// Couleur du badge « état de l'abonnement »
const COULEURS_ABONNEMENT = {
  actif: "bg-green-100 text-green-800",
  grace: "bg-amber-100 text-amber-800",
  expire: "bg-red-100 text-red-700",
  aucun: "bg-gray-100 text-gray-600",
};

const ETATS_IP = {
  autorisee: { texte: "Autorisée", classe: "bg-green-100 text-green-800" },
  bloquee_tous: { texte: "Bloquée (tous les comptes)", classe: "bg-red-100 text-red-700" },
  bloquee_compte: { texte: "Bloquée (ce compte)", classe: "bg-red-100 text-red-700" },
};

// Date ISO -> « JJ/MM/AAAA HH:MM » à l'heure de Ouagadougou
function dateHeure(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("fr-FR", {
      timeZone: "Africa/Ouagadougou", day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).formatToParts(d).map((x) => [x.type, x.value]),
  );
  return `${p.day}/${p.month}/${p.year} ${p.hour}:${p.minute}`;
}

// Pastille ronde de présence (avec info-bulle)
function Pastille({ presence }) {
  const p = PASTILLES[presence?.couleur] || PASTILLES.rouge;
  const titre = presence?.libelle || p.texte;
  return <span className={`inline-block h-3 w-3 rounded-full ${p.classe}`} title={titre} aria-label={titre} role="img" />;
}

const FILTRES_VIDES = { q: "", boutique: "", du: "", au: "", abonnement: "", etat: "" };

export default function Usage() {
  const toast = useToast();

  // --- Historique des connexions ---
  const [filtres, setFiltres] = useState(FILTRES_VIDES);    // saisie en cours
  const [appliques, setAppliques] = useState(FILTRES_VIDES); // filtres de la dernière recherche
  const [page, setPage] = useState(1);
  const [donnees, setDonnees] = useState({ items: [], total: 0, pages: 1 });
  const [chargement, setChargement] = useState(true);       // « Patientez… »
  const [selection, setSelection] = useState(null);         // id de la ligne cliquée
  const [presence, setPresence] = useState({});             // sid -> pastille rafraîchie

  // --- Blocages, journal, contact ---
  const [blocages, setBlocages] = useState([]);
  const [journal, setJournal] = useState([]);
  const [contact, setContact] = useState({ email: "", whatsapp: "" });
  const [dialogue, setDialogue] = useState(null);           // ligne en cours de blocage

  // Chargement de la page d'historique demandée (filtres appliqués)
  const chargerConnexions = useCallback(() => {
    const params = { page };
    Object.entries(appliques).forEach(([k, v]) => { if (v) params[k] = v; });
    return apiClient.get("/plateforme/usage/connexions", { params })
      .then(({ data }) => { setDonnees(data); setPresence({}); })
      .catch((err) => toast.erreur(messageErreur(err, "Historique indisponible")))
      .finally(() => setChargement(false));
  }, [appliques, page, toast]);

  // Blocages en cours + journal des actions
  const chargerBlocages = useCallback(() => {
    apiClient.get("/plateforme/usage/blocages").then(({ data }) => setBlocages(data.blocages)).catch(() => {});
    apiClient.get("/plateforme/usage/journal").then(({ data }) => setJournal(data.actions)).catch(() => {});
  }, []);

  useEffect(() => { chargerConnexions(); }, [chargerConnexions]);
  useEffect(() => {
    chargerBlocages();
    apiClient.get("/plateforme/usage/contact").then(({ data }) => setContact(data)).catch(() => {});
  }, [chargerBlocages]);

  // Rafraîchissement des pastilles toutes les 30 s (requête de FOND : pas une activité)
  const sidsRef = useRef("");
  useEffect(() => {
    sidsRef.current = donnees.items.map((l) => l.sid).filter(Boolean).join(",");
  }, [donnees]);
  useEffect(() => {
    const minuteur = setInterval(() => {
      if (!sidsRef.current) return;
      apiClient.get("/plateforme/usage/presence", { params: { sids: sidsRef.current }, ...EN_ARRIERE_PLAN })
        .then(({ data }) => setPresence(data.presence)).catch(() => {});
    }, RAFRAICHISSEMENT_PRESENCE_MS);
    return () => clearInterval(minuteur);
  }, []);

  // Action (bloquer, autoriser, lever, contact) puis rechargement des listes
  const agir = async (appel, message) => {
    try {
      await appel();
      toast.succes(message);
      chargerBlocages();
      chargerConnexions();
      return true;
    } catch (err) {
      toast.erreur(messageErreur(err, "Action impossible"));
      return false;
    }
  };

  // Nouvelle recherche / autre page : « Patientez… » pendant le chargement
  const appliquer = (nouveaux) => { setChargement(true); setPage(1); setAppliques({ ...nouveaux }); };
  const allerPage = (n) => { setChargement(true); setPage(n); };
  const maj = (champ, valeur) => setFiltres((f) => ({ ...f, [champ]: valeur }));

  return (
    <div className="min-h-screen bg-papier">
      <EnTetePlateforme />
      <Patientez actif={chargement} />
      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
        <div>
          <h1 className="text-2xl font-extrabold">📈 Usage — historique des connexions</h1>
          <p className="text-sm text-gray-500">
            Toutes les connexions (réussies et refusées), les plus récentes en haut. Heures de Ouagadougou.
            Conservation automatique : 180 jours.
          </p>
        </div>

        {/* ---------------- Filtres ---------------- */}
        <form className="card grid gap-3 sm:grid-cols-2 lg:grid-cols-6"
          onSubmit={(e) => { e.preventDefault(); appliquer(filtres); }}>
          <label className="lg:col-span-2"><span className="label">Compte ou adresse IP</span>
            <input className="input" placeholder="Nom, e-mail, téléphone ou IP" value={filtres.q} onChange={(e) => maj("q", e.target.value)} /></label>
          <label className="lg:col-span-2"><span className="label">Boutique</span>
            <input className="input" placeholder="Nom ou ID boutique" value={filtres.boutique} onChange={(e) => maj("boutique", e.target.value)} /></label>
          <label><span className="label">Du</span>
            <input type="date" className="input" value={filtres.du} onChange={(e) => maj("du", e.target.value)} /></label>
          <label><span className="label">Au</span>
            <input type="date" className="input" value={filtres.au} onChange={(e) => maj("au", e.target.value)} /></label>
          <label><span className="label">Abonnement</span>
            <select className="input" value={filtres.abonnement} onChange={(e) => maj("abonnement", e.target.value)}>
              <option value="">Tous</option>
              <option value="actif">Actif</option>
              <option value="grace">Période de grâce</option>
              <option value="expire">Expiré ou suspendu</option>
              <option value="aucun">Aucun</option>
            </select></label>
          <label><span className="label">Connexions</span>
            <select className="input" value={filtres.etat} onChange={(e) => maj("etat", e.target.value)}>
              <option value="">Toutes</option>
              <option value="reussie">Réussies</option>
              <option value="refusee">Refusées</option>
            </select></label>
          <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-4">
            <button className="btn-primary">Rechercher</button>
            <button type="button" className="btn-outline"
              onClick={() => { setFiltres(FILTRES_VIDES); appliquer(FILTRES_VIDES); }}>Effacer les filtres</button>
          </div>
        </form>

        {/* ---------------- Légende des pastilles ---------------- */}
        <div className="flex flex-wrap gap-x-5 gap-y-1 rounded-xl border border-gray-200 bg-white p-3 text-xs text-gray-600">
          {Object.entries(PASTILLES).map(([cle, p]) => (
            <span key={cle} className="flex items-center gap-1.5">
              <span className={`inline-block h-3 w-3 rounded-full ${p.classe}`} aria-hidden="true" /> {p.texte}
            </span>
          ))}
          <span className="text-gray-400">Présence rafraîchie toutes les 30 s.</span>
        </div>

        {/* ---------------- Tableau des connexions ---------------- */}
        <section className="space-y-2">
          <p className="text-sm text-gray-500">{donnees.total} connexion(s)</p>
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-3 py-2" aria-label="Présence" />
                  <th className="px-3 py-2">Date / heure</th>
                  <th className="px-3 py-2">Adresse IP</th>
                  <th className="px-3 py-2">Compte et boutique</th>
                  <th className="px-3 py-2">Rôle</th>
                  <th className="px-3 py-2">Abonnement</th>
                  <th className="px-3 py-2">Méthode / appareil</th>
                  <th className="px-3 py-2">État de l'IP</th>
                  <th className="px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {!chargement && donnees.items.length === 0 && (
                  <tr><td colSpan={9} className="px-3 py-6 text-center text-gray-400">Aucune connexion.</td></tr>
                )}
                {donnees.items.map((l) => {
                  const ipEtat = ETATS_IP[l.ip_etat] || ETATS_IP.autorisee;
                  return (
                    <tr key={l.id} aria-selected={selection === l.id} onClick={() => setSelection(l.id)} className="cursor-pointer align-top">
                      <td className="px-3 py-3"><Pastille presence={(l.sid && presence[l.sid]) || l.presence} /></td>
                      <td className="whitespace-nowrap px-3 py-2">
                        {dateHeure(l.date)}
                        {l.etat === "refusee" && (
                          <span className="badge mt-1 block w-fit bg-red-100 text-red-700">
                            Refusée ({l.motif === "compte" ? "compte bloqué" : "IP bloquée"})
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{l.ip || "—"}</td>
                      <td className="px-3 py-2">
                        {l.compte ? (
                          <>
                            <span className="font-semibold">{l.compte.nom || "Sans nom"}</span>
                            <span className="block text-xs opacity-70">{l.compte.identifiant}</span>
                          </>
                        ) : (
                          <span className="opacity-70">{l.identifiant || "Compte inconnu"}</span>
                        )}
                        {l.boutique
                          ? <span className="block text-xs">🏪 {l.boutique.nom} <span className="font-mono opacity-70">({l.boutique.code})</span></span>
                          : l.compte?.super_admin && <span className="block text-xs opacity-70">Plateforme</span>}
                        {l.compte_bloque && <span className="badge mt-1 block w-fit bg-red-100 text-red-700">Compte bloqué</span>}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2">{l.role_libelle}</td>
                      <td className="px-3 py-2">
                        <span className={`badge ${COULEURS_ABONNEMENT[l.abonnement.statut] || COULEURS_ABONNEMENT.aucun}`}>{l.abonnement.libelle}</span>
                        {l.abonnement.formule && <span className="mt-1 block text-xs opacity-70">{l.abonnement.formule}</span>}
                      </td>
                      <td className="px-3 py-2">
                        {l.methode_libelle}
                        {l.appareil && <span className="block text-xs opacity-70">{l.appareil}</span>}
                      </td>
                      <td className="px-3 py-2"><span className={`badge whitespace-nowrap ${ipEtat.classe}`}>{ipEtat.texte}</span></td>
                      <td className="px-3 py-2">
                        {/* Le super-administrateur ne peut pas être bloqué : pas de bouton sur ses lignes */}
                        {!l.compte?.super_admin && (
                          <div className="flex flex-col gap-1">
                            <button type="button" className="btn-danger btn-sm"
                              onClick={(e) => { e.stopPropagation(); setSelection(l.id); setDialogue(l); }}>
                              Bloquer…
                            </button>
                            {l.ip_etat !== "autorisee" && (
                              <button type="button" className="btn btn-sm bg-green-600 text-white hover:bg-green-700"
                                onClick={(e) => { e.stopPropagation(); agir(() => apiClient.post("/plateforme/usage/autoriser", { type: "ip", ip: l.ip, user_id: l.compte?.id }), "Adresse IP autorisée."); }}>
                                Autoriser l'IP
                              </button>
                            )}
                            {l.compte_bloque && (
                              <button type="button" className="btn btn-sm bg-green-600 text-white hover:bg-green-700"
                                onClick={(e) => { e.stopPropagation(); agir(() => apiClient.post("/plateforme/usage/autoriser", { type: "compte", user_id: l.compte?.id }), "Compte autorisé."); }}>
                                Autoriser le compte
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination : 50 lignes par page */}
          <div className="flex items-center justify-between text-sm">
            <button type="button" disabled={page <= 1} onClick={() => allerPage(page - 1)} className="font-semibold text-gray-600 disabled:opacity-40">← Plus récentes</button>
            <span className="text-gray-500">Page {page} / {donnees.pages}</span>
            <button type="button" disabled={page >= donnees.pages} onClick={() => allerPage(page + 1)} className="font-semibold text-gray-600 disabled:opacity-40">Plus anciennes →</button>
          </div>
        </section>

        {/* ---------------- Blocages en cours ---------------- */}
        <section className="space-y-2">
          <h2 className="text-lg font-bold">🚫 Blocages en cours ({blocages.length})</h2>
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-3 py-2">Depuis le</th>
                  <th className="px-3 py-2">Blocage</th>
                  <th className="px-3 py-2">Compte / boutique</th>
                  <th className="px-3 py-2">Site / motif interne</th>
                  <th className="px-3 py-2">Par</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {blocages.length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-4 text-center text-gray-400">Aucun blocage en cours.</td></tr>
                )}
                {blocages.map((b) => (
                  <tr key={b.id}>
                    <td className="whitespace-nowrap px-3 py-2">{dateHeure(b.cree_le)}</td>
                    <td className="px-3 py-2">
                      {b.type === "compte" ? "Compte" : (
                        <><span className="font-mono text-xs">{b.ip}</span><span className="block text-xs opacity-70">{b.portee === "tous" ? "pour tous les comptes" : "pour ce compte seulement"}</span></>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {b.user_id ? (
                        <>{b.compte_nom || b.compte_identifiant || "Compte"}
                          {b.boutique_nom && <span className="block text-xs opacity-70">🏪 {b.boutique_nom}</span>}</>
                      ) : "—"}
                    </td>
                    <td className="px-3 py-2">{[b.libelle, b.motif].filter(Boolean).join(" · ") || "—"}</td>
                    <td className="px-3 py-2 text-xs">{b.cree_par || "—"}</td>
                    <td className="px-3 py-2 text-right">
                      <button type="button" className="btn btn-sm bg-green-600 text-white hover:bg-green-700"
                        onClick={() => agir(() => apiClient.post(`/plateforme/usage/blocages/${b.id}/lever`), "Blocage levé : accès autorisé.")}>
                        Lever le blocage
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* ---------------- Contact de la page de blocage ---------------- */}
        <section className="card space-y-3">
          <h2 className="text-lg font-bold">📮 Contact affiché sur la page « Accès momentanément suspendu »</h2>
          <p className="text-sm text-gray-500">
            Laissez vide pour afficher le contact officiel des pages légales. La personne bloquée ne voit ni l'adresse IP ni le motif.
          </p>
          <form className="grid gap-3 sm:grid-cols-3"
            onSubmit={(e) => { e.preventDefault(); agir(() => apiClient.put("/plateforme/usage/contact", contact).then(({ data }) => setContact(data)), "Contact enregistré."); }}>
            <input className="input" type="email" placeholder="E-mail de contact" value={contact.email}
              onChange={(e) => setContact({ ...contact, email: e.target.value })} />
            <input className="input" placeholder="WhatsApp (ex. +226 70 00 00 00)" value={contact.whatsapp}
              onChange={(e) => setContact({ ...contact, whatsapp: e.target.value })} />
            <button className="btn-primary">Enregistrer</button>
          </form>
        </section>

        {/* ---------------- Journal des actions ---------------- */}
        <section className="space-y-2">
          <h2 className="text-lg font-bold">🧾 Journal des actions</h2>
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-3 py-2">Date / heure</th>
                  <th className="px-3 py-2">Action</th>
                  <th className="px-3 py-2">Détails</th>
                  <th className="px-3 py-2">Par</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {journal.length === 0 && (
                  <tr><td colSpan={4} className="px-3 py-4 text-center text-gray-400">Aucune action.</td></tr>
                )}
                {journal.map((a) => (
                  <tr key={a.id}>
                    <td className="whitespace-nowrap px-3 py-2">{dateHeure(a.date)}</td>
                    <td className="px-3 py-2 font-semibold">{a.action}</td>
                    <td className="px-3 py-2 text-xs">
                      {[a.details?.ip && `IP ${a.details.ip}`, a.details?.compte, a.details?.boutique && `🏪 ${a.details.boutique}`,
                        a.details?.libelle, a.details?.motif,
                        a.details?.email !== undefined && `E-mail : ${a.details.email || "—"}`,
                        a.details?.whatsapp !== undefined && `WhatsApp : ${a.details.whatsapp || "—"}`,
                        a.details?.sessions_fermees ? `${a.details.sessions_fermees} session(s) fermée(s)` : null]
                        .filter(Boolean).join(" · ") || "—"}
                    </td>
                    <td className="px-3 py-2 text-xs">{a.par || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      {dialogue && (
        <DialogueBlocage ligne={dialogue} onFermer={() => setDialogue(null)}
          onValider={(corps) => agir(() => apiClient.post("/plateforme/usage/blocages", corps), "Blocage enregistré : sessions concernées fermées.")
            .then((ok) => { if (ok) setDialogue(null); })} />
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------
// Fenêtre « Bloquer » : l'adresse IP (pour tous les comptes — case cochée par
// défaut, comme sur SAWALI — ou pour ce compte seulement) ou le compte lui-même.
// ----------------------------------------------------------------------------
function DialogueBlocage({ ligne, onFermer, onValider }) {
  const [cible, setCible] = useState(ligne.ip ? "ip" : "compte"); // « ip » ou « compte »
  const [tousComptes, setTousComptes] = useState(true);
  const [libelle, setLibelle] = useState("");
  const [motif, setMotif] = useState("");
  const [envoi, setEnvoi] = useState(false);

  const valider = async (e) => {
    e.preventDefault();
    setEnvoi(true);
    await onValider({
      type: cible, ip: cible === "ip" ? ligne.ip : null, user_id: ligne.compte?.id || null,
      tous_comptes: cible === "ip" ? tousComptes : false, libelle: libelle || null, motif: motif || null,
    });
    setEnvoi(false);
  };

  return (
    <Modal ouvert titre="Bloquer l'accès" onFermer={onFermer}>
      <form onSubmit={valider} className="space-y-3 text-sm">
        <p className="text-gray-500">
          {ligne.compte ? <>Compte <b>{ligne.compte.nom}</b> ({ligne.compte.identifiant})</> : "Compte inconnu"}
          {ligne.boutique && <> · 🏪 {ligne.boutique.nom}</>}
          {ligne.ip && <> · IP <span className="font-mono">{ligne.ip}</span></>}
        </p>

        {ligne.ip && (
          <label className="flex items-start gap-2">
            <input type="radio" name="cible" checked={cible === "ip"} onChange={() => setCible("ip")} className="mt-1" />
            <span>Bloquer l'adresse IP <span className="font-mono">{ligne.ip}</span></span>
          </label>
        )}
        {cible === "ip" && (
          <div className="ml-6 space-y-2">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={tousComptes} onChange={(e) => setTousComptes(e.target.checked)} disabled={!ligne.compte} />
              Pour tous les comptes
            </label>
            {!tousComptes && <p className="text-xs text-gray-500">Seul ce compte sera refusé depuis cette adresse.</p>}
            <input className="input" placeholder="Nom du site (facultatif, ex. Cybercafé du marché)" maxLength={120}
              value={libelle} onChange={(e) => setLibelle(e.target.value)} />
          </div>
        )}
        {ligne.compte && (
          <label className="flex items-start gap-2">
            <input type="radio" name="cible" checked={cible === "compte"} onChange={() => setCible("compte")} className="mt-1" />
            <span>Bloquer le compte lui-même (depuis n'importe quelle adresse)</span>
          </label>
        )}
        <input className="input" placeholder="Motif interne (facultatif, jamais montré à la personne)" maxLength={300}
          value={motif} onChange={(e) => setMotif(e.target.value)} />
        <p className="text-xs text-gray-500">
          Effet immédiat : les sessions concernées sont fermées et la personne voit la page « Accès momentanément suspendu ».
        </p>
        <div className="flex gap-2">
          <button type="button" onClick={onFermer} className="btn-outline flex-1">Annuler</button>
          <button disabled={envoi} className="btn-danger flex-1">
            {envoi ? "Patientez…" : "Bloquer"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
