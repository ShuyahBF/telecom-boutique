import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { dateHeure } from "@/lib/format";
import { STATUTS_CONVERSATION } from "@/lib/statuts";
import Badge from "@/components/Badge";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";

const RAFRAICHISSEMENT = 20000; // on relit la conversation toutes les 20 secondes

// CONVERSATION de conseil (/b/:slug/conseil/:jeton) : page privée, accessible
// par son lien secret. Bulles du client à droite, de l'équipe à gauche.
export default function Conversation() {
  const { boutique } = useOutletContext();
  const { jeton } = useParams();
  const [params] = useSearchParams();
  const toast = useToast();

  // La conversation : { sujet, statut, produit, nom, messages: [...] } ; null = chargement
  const [conv, setConv] = useState(null);
  const [erreur, setErreur] = useState("");
  // Réponse en cours de saisie et envoi en cours
  const [texte, setTexte] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const finRef = useRef(null); // repère en bas de la liste, pour y faire défiler
  const nbMessages = useRef(0); // nombre de messages déjà affichés

  // Lecture de la conversation depuis l'API
  const charger = useCallback(async () => {
    try {
      const { data } = await apiClient.get(`/public/b/${boutique.slug}/conseils/${jeton}`);
      setConv(data);
      setErreur("");
    } catch (err) {
      // Si on a déjà la conversation, une erreur réseau passagère ne l'efface pas
      if (err?.response?.status === 404) setErreur(messageErreur(err, "Conversation introuvable"));
    }
  }, [boutique.slug, jeton]);

  // Premier chargement, puis rafraîchissement automatique toutes les 20 s
  useEffect(() => {
    charger();
    const minuterie = setInterval(charger, RAFRAICHISSEMENT);
    return () => clearInterval(minuterie);
  }, [charger]);

  // Défilement vers le dernier message quand un nouveau message arrive
  useEffect(() => {
    const n = conv?.messages.length || 0;
    if (n > nbMessages.current && nbMessages.current > 0) finRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    nbMessages.current = n;
  }, [conv]);

  // Envoi d'une réponse du client
  const repondre = async (e) => {
    e.preventDefault();
    if (!texte.trim()) return;
    setEnvoi(true);
    try {
      const { data } = await apiClient.post(`/public/b/${boutique.slug}/conseils/${jeton}`, { texte: texte.trim() });
      setConv(data);
      setTexte("");
    } catch (err) {
      toast.erreur(messageErreur(err, "Message non envoyé, réessayez"));
    } finally {
      setEnvoi(false);
    }
  };

  // Copie du lien de la page dans le presse-papiers
  const copierLien = async () => {
    const lien = `${window.location.origin}/b/${boutique.slug}/conseil/${jeton}`;
    try {
      await navigator.clipboard.writeText(lien);
      toast.succes("Lien copié : gardez-le pour revenir à la conversation");
    } catch {
      toast.erreur("Copie impossible : ajoutez cette page à vos favoris.");
    }
  };

  // Conversation introuvable (lien erroné)
  if (erreur) {
    return (
      <div className="card mx-auto max-w-md py-10 text-center">
        <p className="text-4xl">🔒</p>
        <p className="mt-2 font-semibold">{erreur}</p>
        <p className="mt-1 text-sm text-gray-500">Vérifiez le lien reçu, ou posez une nouvelle question.</p>
        <Link to={`/b/${boutique.slug}/conseil`} className="btn-boutique mt-4">Nouvelle question</Link>
      </div>
    );
  }
  if (!conv) return <Chargement />;

  const close = conv.statut === "CLOS";

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      {/* Rappel après la création : garder le lien */}
      {params.get("nouveau") && (
        <div className="rounded-2xl border border-green-200 bg-green-50 p-4 text-sm text-green-900">
          ✅ <b>Question envoyée !</b> Cette page est privée : gardez son lien (favori ou bouton ci-dessous) pour lire la réponse de la boutique.
        </div>
      )}

      {/* ---------- En-tête : sujet, statut, produit, copie du lien ---------- */}
      <div className="card space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h1 className="text-xl font-extrabold leading-tight">{conv.sujet}</h1>
          <Badge table={STATUTS_CONVERSATION} statut={conv.statut} />
        </div>
        {conv.produit && (
          <p className="text-sm text-gray-600">
            📱 Produit :{" "}
            <Link to={`/b/${boutique.slug}/produit/${conv.produit.slug}`} className="font-semibold text-boutique">{conv.produit.nom}</Link>
          </p>
        )}
        <button type="button" className="btn-outline btn-sm" onClick={copierLien}>🔗 Copier le lien de cette conversation</button>
      </div>

      {/* ---------- Fil des messages ---------- */}
      <div className="space-y-3 rounded-2xl bg-gray-100 p-3 sm:p-4">
        {conv.messages.map((m, i) => {
          const client = m.auteur_type === "CLIENT";
          return (
            <div key={`${m.date}-${i}`} className={`flex ${client ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 shadow-sm ${client ? "rounded-br-sm bg-boutique text-white" : "rounded-bl-sm bg-white text-ink"}`}>
                {/* Auteur : le client ou l'équipe (nom de la boutique) */}
                <p className={`text-xs font-bold ${client ? "text-white/80" : "text-boutique"}`}>
                  {client ? "Vous" : `${boutique.nom}${m.auteur_nom ? ` · ${m.auteur_nom}` : ""}`}
                </p>
                <p className="whitespace-pre-line break-words">{m.texte}</p>
                <p className={`mt-1 text-right text-[11px] ${client ? "text-white/70" : "text-gray-400"}`}>{dateHeure(m.date)}</p>
              </div>
            </div>
          );
        })}
        {/* Message d'attente tant que l'équipe n'a pas répondu */}
        {conv.statut === "ATTENTE" && (
          <p className="text-center text-xs text-gray-500">⏳ L'équipe de {boutique.nom} va vous répondre. Cette page se met à jour toute seule.</p>
        )}
        <div ref={finRef} />
      </div>

      {/* ---------- Zone de réponse (désactivée si la conversation est close) ---------- */}
      {close ? (
        <p className="rounded-xl bg-gray-100 p-3 text-center text-sm text-gray-600">
          Cette conversation est close. <Link to={`/b/${boutique.slug}/conseil`} className="font-semibold text-boutique">Poser une nouvelle question</Link>
        </p>
      ) : (
        <form onSubmit={repondre} className="flex items-end gap-2">
          <textarea
            className="input min-h-[48px] flex-1 resize-y"
            rows={2}
            maxLength={5000}
            placeholder="Écrire un message…"
            value={texte}
            onChange={(e) => setTexte(e.target.value)}
            aria-label="Votre message"
          />
          <button type="submit" className="btn-boutique h-12" disabled={envoi || !texte.trim()}>{envoi ? "…" : "Envoyer"}</button>
        </form>
      )}
    </div>
  );
}
