/*
  « Maintenance des équipements » : matériel confié pour diagnostic et réparation
  (ordinateur, imprimante, onduleur…). Chaque dépôt est une fiche : numéro automatique
  (MNT-<CODE>-<AAAA>-0001), client, date de réception, type de matériel (liste
  extensible), état (mauvais, moyen, bon), motif, diagnostic, remplacement de pièces,
  dates d'entrée et de sortie, statut (reçu -> rendu), prix du diagnostic (10 000 FCFA
  par défaut) et équipe. Bon de dépôt / de restitution imprimable ; photos annotées,
  envoi WhatsApp, lien de paiement et facturation (components/MaintenanceActions.jsx).

  Même écran pour les deux espaces (prop « espace ») :
    - « boutique »   : clients = fichier Clients de la boutique (ou saisie libre) ;
    - « plateforme » : super-admin adLyn, clients = boutiques (téléphone = celui qui
                       reçoit les messages de la plateforme).
  API : /maintenance-equipements ou /plateforme/maintenance-equipements
  (backend/routes/maintenance_equipements.py).
*/
import { useCallback, useEffect, useState } from "react";
import { apiClient, messageErreur } from "@/lib/api";
import { aujourdhui, date, prix } from "@/lib/format";
import { baseApi, ETATS, lienImpression, STATUTS } from "@/lib/maintenanceEquipements";
import Chargement from "@/components/Chargement";
import EnTetePage from "@/components/EnTetePage";
import MaintenanceActions from "@/components/MaintenanceActions";
import { useToast } from "@/components/Toast";

// Fiche vierge (prix du diagnostic : valeur de la plateforme, reçue avec les types)
const vide = (prixDefaut) => ({
  boutique_client_id: "", client_id: "", client_nom: "", client_telephone: "", date_reception: aujourdhui(),
  type_materiel: "", marque_modele: "", numero_serie: "", etat_materiel: "moyen", motif: "", diagnostic: "",
  remplacement_pieces: false, pieces: "", observations: "", date_entree: aujourdhui(), date_sortie: "",
  statut: "recu", prix_diagnostic: prixDefaut, equipe: "",
});

// Champ de formulaire : libellé + contrôle
function Champ({ label, aide, className = "", children }) {
  return (
    <label className={`block ${className}`}>
      <span className="label">{label}</span>
      {children}
      {aide && <span className="mt-1 block text-xs text-gray-500">{aide}</span>}
    </label>
  );
}

// ---- Formulaire d'une fiche (création ou modification) ------------------------------------
function FormulaireFiche({ espace, fiche, types, clients, prixDefaut, services, onAjoutType, onFermer, onEnregistre, onRafraichir }) {
  const toast = useToast();
  const base = baseApi(espace);
  const [f, setF] = useState(() => (fiche ? {
    ...vide(prixDefaut), ...fiche,
    boutique_client_id: fiche.boutique_client_id || "", client_id: fiche.client_id || "",
    marque_modele: fiche.marque_modele || "", numero_serie: fiche.numero_serie || "", diagnostic: fiche.diagnostic || "",
    pieces: fiche.pieces || "", observations: fiche.observations || "", equipe: fiche.equipe || "",
    date_entree: fiche.date_entree || "", date_sortie: fiche.date_sortie || "",
  } : vide(prixDefaut)));
  const [occupe, setOccupe] = useState(false);
  const maj = (x) => setF((p) => ({ ...p, ...x }));
  const choisi = f.boutique_client_id || f.client_id;

  // Enregistrement : seuls les champs de saisie sont envoyés
  const enregistrer = async (e) => {
    e.preventDefault();
    setOccupe(true);
    const corps = {
      boutique_client_id: f.boutique_client_id || null, client_id: f.client_id || null,
      client_nom: f.client_nom, client_telephone: f.client_telephone, date_reception: f.date_reception || null,
      type_materiel: f.type_materiel, marque_modele: f.marque_modele, numero_serie: f.numero_serie,
      etat_materiel: f.etat_materiel, motif: f.motif, diagnostic: f.diagnostic, remplacement_pieces: f.remplacement_pieces,
      pieces: f.pieces, observations: f.observations, date_entree: f.date_entree || null, date_sortie: f.date_sortie || null,
      statut: f.statut === "rendu" ? "pret" : f.statut, prix_diagnostic: Number(f.prix_diagnostic) || 0, equipe: f.equipe,
    };
    try {
      const { data } = fiche ? await apiClient.put(`${base}/${fiche.id}`, corps) : await apiClient.post(base, corps);
      toast.succes(fiche ? "Fiche mise à jour" : `Fiche ${data.numero} créée`);
      onEnregistre(data);
    } catch (err) { toast.erreur(messageErreur(err, "Enregistrement impossible")); }
    finally { setOccupe(false); }
  };

  return (
    <div className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">{fiche ? `Fiche ${fiche.numero}` : "Nouvelle fiche de dépôt"}</h2>
        <div className="flex gap-2">
          {fiche && <a href={lienImpression(espace, fiche.id)} target="_blank" rel="noreferrer" className="btn-outline btn-sm">🖨️ {fiche.date_sortie ? "Bon de restitution" : "Bon de dépôt"}</a>}
          <button type="button" className="btn-outline btn-sm" onClick={onFermer}>← Retour à la liste</button>
        </div>
      </div>

      <form onSubmit={enregistrer} className="grid gap-3 sm:grid-cols-2">
        {/* Client : boutique (plateforme) ou client de la boutique ; téléphone repris, modifiable */}
        <Champ label={espace === "plateforme" ? "Client (boutique adLyn)" : "Client (fichier clients)"}>
          <select className="input bg-white" value={choisi || ""}
            onChange={(e) => {
              const c = clients.items.find((x) => x.id === e.target.value);
              maj(espace === "plateforme"
                ? { boutique_client_id: c?.id || "", client_telephone: c?.telephone || "", client_nom: c ? c.nom : f.client_nom }
                : { client_id: c?.id || "", client_telephone: c?.telephone || "", client_nom: c ? c.nom : f.client_nom });
            }}>
            <option value="">— Saisir le client à la main —</option>
            {clients.items.map((c) => <option key={c.id} value={c.id}>{c.nom}{c.code ? ` · ${c.code}` : ""}</option>)}
          </select>
        </Champ>
        {!choisi && (
          <Champ label="Nom du client *"><input className="input" value={f.client_nom} maxLength={160} onChange={(e) => maj({ client_nom: e.target.value })} /></Champ>
        )}
        <Champ label="Téléphone (WhatsApp)" aide={f.boutique_client_id ? "Numéro qui reçoit les messages d'adLyn (DG de la boutique)." : ""}>
          <input className="input" value={f.client_telephone} maxLength={40} onChange={(e) => maj({ client_telephone: e.target.value })} />
        </Champ>
        <Champ label="Date de réception"><input type="date" className="input" value={f.date_reception} onChange={(e) => maj({ date_reception: e.target.value })} /></Champ>

        <Champ label="Type de matériel *">
          <div className="flex gap-1">
            <select className="input bg-white" value={f.type_materiel} onChange={(e) => maj({ type_materiel: e.target.value })} required>
              <option value="">— Choisir —</option>
              {types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <button type="button" title="Ajouter un type de matériel" className="btn-outline px-3"
              onClick={async () => { const t = await onAjoutType(); if (t) maj({ type_materiel: t }); }}>＋</button>
          </div>
        </Champ>
        <Champ label="Marque / modèle"><input className="input" value={f.marque_modele} maxLength={160} onChange={(e) => maj({ marque_modele: e.target.value })} /></Champ>
        <Champ label="N° de série"><input className="input" value={f.numero_serie} maxLength={80} onChange={(e) => maj({ numero_serie: e.target.value })} /></Champ>
        <div>
          <span className="label">État du matériel</span>
          <div className="flex gap-2">
            {Object.entries(ETATS).map(([k, [l, cls]]) => (
              <label key={k} className={`flex cursor-pointer items-center gap-1 rounded-lg border px-3 py-2 text-sm ${f.etat_materiel === k ? "border-primary bg-primary/5" : "border-gray-200"}`}>
                <input type="radio" name="etat" checked={f.etat_materiel === k} onChange={() => maj({ etat_materiel: k })} />
                <span className={cls}>{l}</span>
              </label>
            ))}
          </div>
        </div>
        <Champ label="Motif du dépôt *" className="sm:col-span-2">
          <textarea className="input" rows={2} required maxLength={2000} value={f.motif} onChange={(e) => maj({ motif: e.target.value })} />
        </Champ>
        <Champ label="Diagnostic" className="sm:col-span-2">
          <textarea className="input" rows={3} maxLength={4000} value={f.diagnostic} onChange={(e) => maj({ diagnostic: e.target.value })} />
        </Champ>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={!!f.remplacement_pieces} onChange={(e) => maj({ remplacement_pieces: e.target.checked })} />
          Nécessite le remplacement de pièces
        </label>
        {f.remplacement_pieces ? (
          <Champ label="Pièces à remplacer"><input className="input" value={f.pieces} maxLength={2000} onChange={(e) => maj({ pieces: e.target.value })} /></Champ>
        ) : <span className="hidden sm:block" />}
        <Champ label="Date d'entrée en atelier"><input type="date" className="input" value={f.date_entree} onChange={(e) => maj({ date_entree: e.target.value })} /></Champ>
        <Champ label="Date de sortie (restitution)" aide="Une date de sortie passe la fiche au statut « Rendu »."><input type="date" className="input" value={f.date_sortie} onChange={(e) => maj({ date_sortie: e.target.value })} /></Champ>
        <Champ label="Statut">
          <select className="input bg-white" value={f.date_sortie ? "rendu" : (f.statut === "rendu" ? "pret" : f.statut)} disabled={!!f.date_sortie} onChange={(e) => maj({ statut: e.target.value })}>
            {Object.entries(STATUTS).filter(([k]) => k !== "rendu" || f.date_sortie).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </Champ>
        <Champ label="Prix du diagnostic (FCFA)">
          <input type="number" min={0} step={500} className="input" value={f.prix_diagnostic} onChange={(e) => maj({ prix_diagnostic: e.target.value })} />
        </Champ>
        <Champ label="Équipe (noms)"><input className="input" value={f.equipe} maxLength={300} placeholder="ex. Issa, Awa" onChange={(e) => maj({ equipe: e.target.value })} /></Champ>
        <Champ label="Observations" className="sm:col-span-2">
          <textarea className="input" rows={2} maxLength={2000} value={f.observations} onChange={(e) => maj({ observations: e.target.value })} />
        </Champ>
        <div className="flex justify-end gap-2 sm:col-span-2">
          <button type="button" className="btn-outline" onClick={onFermer}>Annuler</button>
          <button className="btn-primary" disabled={occupe || !f.type_materiel || !f.motif.trim() || (!choisi && !f.client_nom.trim())}>
            {occupe ? "Enregistrement…" : "Enregistrer"}
          </button>
        </div>
      </form>

      {/* Photos, WhatsApp, lien de paiement, facturation : fiche déjà enregistrée */}
      {fiche?.id
        ? <MaintenanceActions fiche={fiche} espace={espace} services={services} onChange={onRafraichir} />
        : <p className="text-xs text-gray-500">Enregistrez la fiche pour ajouter des photos, l'envoyer par WhatsApp, créer un lien de paiement ou la facturer.</p>}
    </div>
  );
}

// ---- Écran principal : liste des fiches ----------------------------------------------------
export default function MaintenanceEquipements({ espace = "boutique" }) {
  const toast = useToast();
  const base = baseApi(espace);
  const [donnees, setDonnees] = useState(null);
  const [refus, setRefus] = useState("");
  const [types, setTypes] = useState([]);
  const [prixDefaut, setPrixDefaut] = useState(10000);
  const [clients, setClients] = useState({ type: "client", items: [] });
  const [services, setServices] = useState({});
  const [q, setQ] = useState("");
  const [statut, setStatut] = useState("");
  const [type, setType] = useState("");
  const [edition, setEdition] = useState(null); // null | "nouvelle" | fiche

  // Liste des fiches (recherche différée de 250 ms pendant la frappe)
  const charger = useCallback(async () => {
    try {
      const { data } = await apiClient.get(base, { params: { q: q || undefined, statut: statut || undefined, type_materiel: type || undefined } });
      setDonnees(data);
    } catch (err) { setRefus(messageErreur(err, "Module indisponible")); }
  }, [base, q, statut, type]);
  useEffect(() => { const t = setTimeout(charger, 250); return () => clearTimeout(t); }, [charger]);

  // Types de matériel, clients proposés, services disponibles (WhatsApp, paiement…)
  const chargerTypes = useCallback(() => apiClient.get(`${base}/types`).then(({ data }) => {
    setTypes(data.tous || []);
    setPrixDefaut(data.prix_diagnostic_defaut ?? 10000);
  }).catch(() => {}), [base]);
  useEffect(() => {
    chargerTypes();
    apiClient.get(`${base}/clients`).then(({ data }) => setClients(data)).catch(() => {});
    apiClient.get(`${base}/services`).then(({ data }) => setServices(data)).catch(() => {});
  }, [base, chargerTypes]);

  const ajouterType = async () => {
    const libelle = window.prompt("Nouveau type de matériel :");
    if (!libelle?.trim()) return null;
    try { await apiClient.post(`${base}/types`, { libelle: libelle.trim() }); await chargerTypes(); return libelle.trim(); }
    catch (err) { toast.erreur(messageErreur(err, "Type refusé")); return null; }
  };
  const supprimer = async (f) => {
    if (!window.confirm(`Supprimer la fiche ${f.numero} ?`)) return;
    try { await apiClient.delete(`${base}/${f.id}`); toast.succes("Fiche supprimée"); charger(); }
    catch (err) { toast.erreur(messageErreur(err, "Suppression impossible")); }
  };
  // Fiche ouverte relue après une action (photo, lien de paiement, facture, envoi)
  const rafraichirFiche = async () => {
    if (!edition?.id) return;
    try { setEdition((await apiClient.get(`${base}/${edition.id}`)).data); } catch { /* fiche supprimée */ }
    charger();
  };

  if (refus) return <div className="card border-amber-200 bg-amber-50 text-amber-900">{refus}</div>;
  const compte = donnees?.compte || {};

  return (
    <div className="space-y-4">
      <EnTetePage titre="🛠️ Maintenance des équipements"
        sousTitre={espace === "plateforme" ? "Matériel confié par les boutiques adLyn" : "Ordinateurs, imprimantes, onduleurs… confiés par vos clients"}>
        {!edition && <button type="button" className="btn-primary" onClick={() => setEdition("nouvelle")}>+ Nouvelle fiche</button>}
      </EnTetePage>

      {edition ? (
        <FormulaireFiche key={edition === "nouvelle" ? "nouvelle" : edition.id} espace={espace}
          fiche={edition === "nouvelle" ? null : edition} types={types} clients={clients} prixDefaut={prixDefaut}
          services={services} onAjoutType={ajouterType} onRafraichir={rafraichirFiche} onFermer={() => { setEdition(null); charger(); }}
          onEnregistre={(f) => {
            charger();
            // La fiche reste ouverte : photos, bon de dépôt, envoi WhatsApp, paiement…
            setEdition(f);
          }} />
      ) : (
        <>
          {/* Filtres par statut (avec les nombres de fiches) */}
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => setStatut("")} className={`badge px-3 py-1 ring-1 ${!statut ? "bg-ink text-white ring-ink" : "bg-white ring-gray-300"}`}>Toutes</button>
            {Object.entries(STATUTS).map(([k, [l, cls]]) => (
              <button key={k} type="button" onClick={() => setStatut(statut === k ? "" : k)}
                className={`badge px-3 py-1 ${statut === k ? "ring-2 ring-primary" : ""} ${cls}`}>
                {l} ({compte[k] ?? 0})
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <input className="input min-w-[200px] flex-1" placeholder="🔍 N°, client, téléphone, modèle, n° de série…" value={q} onChange={(e) => setQ(e.target.value)} />
            <select className="input w-auto bg-white" value={type} onChange={(e) => setType(e.target.value)} aria-label="Type de matériel">
              <option value="">Tous les matériels</option>
              {types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div className="card overflow-x-auto p-0">
            <table className="table">
              <thead>
                <tr><th>N°</th><th>Client</th><th>Matériel</th><th>État</th><th>Reçu</th><th>Entrée → sortie</th><th>Pièces</th><th>Statut</th><th /></tr>
              </thead>
              <tbody>
                {!donnees && <tr><td colSpan={9}><Chargement /></td></tr>}
                {donnees?.fiches.length === 0 && <tr><td colSpan={9} className="py-8 text-center text-gray-500">Aucune fiche.</td></tr>}
                {(donnees?.fiches || []).map((f) => (
                  <tr key={f.id} className="cursor-pointer hover:bg-gray-50" onClick={() => setEdition(f)}>
                    <td className="font-mono text-xs">{f.numero}</td>
                    <td>{f.client_nom}<span className="block text-xs text-gray-500">{f.client_telephone}</span></td>
                    <td>{f.type_materiel}<span className="block text-xs text-gray-500">{f.marque_modele}</span></td>
                    <td className={ETATS[f.etat_materiel]?.[1] || ""}>{ETATS[f.etat_materiel]?.[0]}</td>
                    <td className="whitespace-nowrap">{date(f.date_reception)}</td>
                    <td className="whitespace-nowrap text-xs">{date(f.date_entree)} → {date(f.date_sortie)}</td>
                    <td className="text-xs">{f.remplacement_pieces ? <span className="text-amber-700">Oui{f.pieces ? ` : ${f.pieces}` : ""}</span> : "Non"}</td>
                    <td>
                      <span className={`badge ${STATUTS[f.statut]?.[1]}`}>{STATUTS[f.statut]?.[0]}</span>
                      {/* Paiement et facture */}
                      {f.lien_paiement && <span className={`block text-[11px] ${f.lien_paiement.paye ? "text-emerald-700" : "text-amber-700"}`}>{f.lien_paiement.paye ? "Payé" : "Paiement en attente"} · {prix(f.lien_paiement.montant)}</span>}
                      {f.facture && <span className="block text-[11px] text-indigo-700">{f.facture.numero || "Facture (brouillon)"}</span>}
                    </td>
                    <td className="whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <a href={lienImpression(espace, f.id)} target="_blank" rel="noreferrer" title="Bon de dépôt / de restitution" className="px-1">🖨️</a>
                      {services.suppression && <button type="button" title="Supprimer" onClick={() => supprimer(f)} className="px-1 text-red-500">🗑</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
