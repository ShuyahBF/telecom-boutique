import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { aLeRole, useAuth } from "@/context/AuthContext";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import { STATUTS_CONVERSATION } from "@/lib/statuts";
import Badge from "@/components/Badge";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";
import { BoutonsContact } from "./_ventes/outils";

// Filtres de la boîte de réception : [statut envoyé au serveur, libellé]
const FILTRES = [["", "Toutes"], ["ATTENTE", "En attente"], ["REPONDU", "Répondu"], ["CLOS", "Clos"]];

// Centre de messagerie : demandes de conseil envoyées depuis la vitrine.
// Grand écran : liste à gauche, fil de discussion à droite.
// Téléphone : la liste, puis le fil (une seule colonne, bouton « Retour »).
// La conversation ouverte est gardée dans l'adresse (?c=<id>).
export default function Messagerie() {
  const { user, boutique } = useAuth();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const selection = params.get("c");

  const [filtre, setFiltre] = useState("");
  const [conversations, setConversations] = useState(null);
  const [conv, setConv] = useState(null); // conversation ouverte (avec ses messages)
  const [texte, setTexte] = useState(""); // réponse en cours de saisie
  const [enCours, setEnCours] = useState(false);
  const finDuFil = useRef(null);

  // Chargement de la liste des conversations (selon le filtre)
  const chargerListe = useCallback(() => {
    return apiClient.get("/conversations", { params: { statut: filtre } })
      .then(({ data }) => setConversations(data))
      .catch((err) => { setConversations([]); toast.erreur(messageErreur(err, "Impossible de charger la messagerie")); });
    // toast est recréé à chaque affichage : on ne le met pas en dépendance
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtre]);

  // Au changement de filtre, puis toutes les minutes (nouvelles demandes)
  useEffect(() => {
    chargerListe();
    const t = setInterval(chargerListe, 60000);
    return () => clearInterval(t);
  }, [chargerListe]);

  // Ouverture d'une conversation : GET /conversations/{id} (marque les messages du client comme lus)
  useEffect(() => {
    if (!selection) {
      setConv(null);
      return;
    }
    let annule = false;
    setConv(null);
    apiClient.get(`/conversations/${selection}`)
      .then(({ data }) => {
        if (annule) return;
        setConv(data);
        // Dans la liste, cette conversation n'a plus de message non lu
        setConversations((liste) => liste?.map((c) => (c.id === data.id ? { ...c, non_lus: 0 } : c)));
      })
      .catch((err) => { if (!annule) toast.erreur(messageErreur(err, "Conversation introuvable")); });
    return () => { annule = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection]);

  // Défilement automatique vers le dernier message
  useEffect(() => {
    finDuFil.current?.scrollIntoView({ block: "end" });
  }, [conv?.messages?.length]);

  const ouvrir = (id) => setParams(id ? { c: id } : {});

  // Envoi d'une réponse : POST /conversations/{id}/repondre
  async function repondre(e) {
    e?.preventDefault();
    if (!texte.trim()) return;
    setEnCours(true);
    try {
      const { data } = await apiClient.post(`/conversations/${conv.id}/repondre`, { texte: texte.trim() });
      setConv(data);
      setTexte("");
      toast.succes(data.email ? "Réponse envoyée (le client est prévenu par e-mail)" : "Réponse enregistrée");
      chargerListe();
    } catch (err) {
      toast.erreur(messageErreur(err, "Envoi impossible"));
    } finally {
      setEnCours(false);
    }
  }

  // Clore / rouvrir : POST /conversations/{id}/statut
  async function changerStatut(statut) {
    setEnCours(true);
    try {
      const { data } = await apiClient.post(`/conversations/${conv.id}/statut`, { statut });
      setConv(data);
      toast.succes(statut === "CLOS" ? "Conversation close" : "Conversation rouverte");
      chargerListe();
    } catch (err) {
      toast.erreur(messageErreur(err, "Action impossible"));
    } finally {
      setEnCours(false);
    }
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-extrabold">Messagerie</h1>
          <p className="text-sm text-gray-500">Demandes de conseil reçues depuis votre vitrine</p>
        </div>
        {aLeRole(user, "gerant") && (
          <Link to="/gestion/parametres" className="text-sm text-gray-500 hover:text-primary">
            ⚙️ Envoi des e-mails : <span className="font-semibold underline">Paramètres &gt; Messagerie</span>
          </Link>
        )}
      </div>

      <div className="grid overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm md:h-[calc(100vh-12rem)] md:min-h-[480px] md:grid-cols-[20rem_minmax(0,1fr)]">
        {/* Colonne de gauche : filtres + liste des conversations (cachée sur téléphone quand un fil est ouvert) */}
        <aside className={`flex min-h-0 flex-col border-gray-200 md:border-r ${selection ? "hidden md:flex" : "flex"}`}>
          <div className="grid grid-cols-4 gap-1 border-b border-gray-100 p-2">
            {FILTRES.map(([v, l]) => (
              <button key={l} type="button" onClick={() => setFiltre(v)}
                className={`whitespace-nowrap rounded-lg px-1 py-1.5 text-[13px] font-semibold ${filtre === v ? "bg-primary text-white" : "text-gray-600 hover:bg-gray-100"}`}>
                {l}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {!conversations ? <Chargement /> : conversations.length === 0 ? (
              <p className="p-6 text-center text-sm text-gray-500">Aucune conversation.</p>
            ) : conversations.map((c) => (
              <button key={c.id} type="button" onClick={() => ouvrir(c.id)}
                className={`block w-full border-b border-gray-100 px-4 py-3 text-left hover:bg-gray-50 ${c.id === selection ? "bg-primary/5 ring-1 ring-inset ring-primary/30" : ""}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className={`truncate ${c.non_lus > 0 ? "font-extrabold" : "font-semibold"}`}>{c.nom}</span>
                  <span className="shrink-0 text-[11px] text-gray-500">{dateHeure(c.date_maj)}</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-gray-700">{c.sujet}</span>
                  {c.non_lus > 0 && <span className="shrink-0 rounded-full bg-accent px-2 text-xs font-bold text-white">{c.non_lus}</span>}
                </div>
                <p className="truncate text-xs text-gray-500">{c.dernier_message}</p>
                <Badge table={STATUTS_CONVERSATION} statut={c.statut} className="mt-1" />
              </button>
            ))}
          </div>
        </aside>

        {/* Colonne de droite : fil de discussion */}
        <section className={`min-h-0 flex-col ${selection ? "flex" : "hidden md:flex"}`}>
          {!selection ? (
            <div className="flex flex-1 items-center justify-center p-10 text-center text-gray-500">
              <p>💬<br />Choisissez une conversation dans la liste.</p>
            </div>
          ) : !conv ? <Chargement /> : (
            <>
              {/* En-tête du fil : demandeur, coordonnées, produit concerné, actions */}
              <div className="space-y-2 border-b border-gray-100 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <button type="button" className="mb-1 text-sm font-semibold text-primary md:hidden" onClick={() => ouvrir(null)}>← Toutes les conversations</button>
                    <h2 className="text-lg font-bold">{conv.sujet}</h2>
                    <p className="text-sm text-gray-600">
                      {conv.nom} · {conv.telephone}{conv.email ? ` · ${conv.email}` : ""}
                      {conv.client_id && <> · <Link to={`/gestion/clients/${conv.client_id}`} className="font-semibold text-primary">fiche client</Link></>}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge table={STATUTS_CONVERSATION} statut={conv.statut} />
                    {conv.statut === "CLOS"
                      ? <button type="button" className="btn-outline btn-sm" disabled={enCours} onClick={() => changerStatut("ATTENTE")}>Rouvrir</button>
                      : <button type="button" className="btn-outline btn-sm" disabled={enCours} onClick={() => changerStatut("CLOS")}>Clore</button>}
                  </div>
                </div>
                <BoutonsContact telephone={conv.telephone} email={conv.email} />
                {conv.produit && (
                  <p className="rounded-lg bg-gray-50 px-3 py-2 text-sm">
                    📱 Produit concerné : <Link to={`/gestion/produits/${conv.produit.id}`} className="font-semibold text-primary">{conv.produit.nom}</Link>
                    {boutique?.slug && conv.produit.slug && (
                      <a href={`/b/${boutique.slug}/produit/${conv.produit.slug}`} target="_blank" rel="noreferrer" className="ml-2 text-xs text-gray-500 underline">voir sur la vitrine ↗</a>
                    )}
                  </p>
                )}
              </div>

              {/* Messages : client à gauche (gris), équipe à droite (bleu) */}
              <div className="min-h-[300px] flex-1 space-y-3 overflow-y-auto bg-gray-50 p-4">
                {conv.messages.map((m) => {
                  const equipe = m.auteur_type === "EQUIPE";
                  return (
                    <div key={m.id || m.date} className={`flex ${equipe ? "justify-end" : "justify-start"}`}>
                      <div className={`max-w-[85%] rounded-2xl px-4 py-2 shadow-sm ${equipe ? "rounded-br-sm bg-primary text-white" : "rounded-bl-sm bg-white text-ink"}`}>
                        <p className="whitespace-pre-line break-words text-sm">{m.texte}</p>
                        <p className={`mt-1 text-[11px] ${equipe ? "text-white/75" : "text-gray-500"}`}>{m.auteur_nom} · {dateHeure(m.date)}</p>
                      </div>
                    </div>
                  );
                })}
                <div ref={finDuFil} />
              </div>

              {/* Zone de réponse (Ctrl + Entrée pour envoyer) */}
              <form onSubmit={repondre} className="flex flex-col gap-2 border-t border-gray-100 p-3 sm:flex-row sm:items-end">
                <textarea className="input min-h-[3rem] flex-1 resize-y" rows={2} maxLength={5000} value={texte}
                  placeholder={conv.statut === "CLOS" ? "Conversation close : répondre la rouvre…" : "Votre réponse… (Ctrl + Entrée pour envoyer)"}
                  onChange={(e) => setTexte(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) repondre(e); }} />
                <button className="btn-primary" disabled={enCours || !texte.trim()}>{enCours ? "Envoi…" : "Envoyer"}</button>
              </form>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
