import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";
import { apiClient, messageErreur } from "@/lib/api";

// Libellés des visibilités proposées par TikTok (entre parenthèses : terme TikTok)
const VISIBILITES = {
  PUBLIC_TO_EVERYONE: "Tout le monde (Everyone)",
  MUTUAL_FOLLOW_FRIENDS: "Amis (Friends)",
  FOLLOWER_OF_CREATOR: "Abonnés (Followers)",
  SELF_ONLY: "Moi uniquement (Only me)",
};
const STATUTS = {
  PROCESSING_DOWNLOAD: "TikTok récupère la photo…",
  PROCESSING_UPLOAD: "TikTok traite la publication…",
  SEND_TO_USER_INBOX: "Envoyée dans votre boîte TikTok",
  PUBLISH_COMPLETE: "✅ Publiée sur TikTok",
  FAILED: "❌ Échec de la publication",
};
const LIEN_MUSIQUE = "https://www.tiktok.com/legal/page/global/music-usage-confirmation/en";
const LIEN_BRANDED = "https://www.tiktok.com/legal/page/global/bc-policy/en";

// Fenêtre « Publier sur TikTok » d'un produit, conforme aux règles de TikTok
// (Content Sharing Guidelines) :
//  - nom et photo du compte TikTok affichés, infos relues à chaque ouverture ;
//  - visibilité choisie dans la liste fournie par TikTok, SANS valeur par défaut ;
//  - commentaires décochés par défaut (grisés si le créateur les a désactivés) ;
//  - divulgation du contenu commercial (désactivée par défaut) ;
//  - déclaration TikTok affichée avant le bouton ; aucune image modifiée ;
//  - suivi de l'état de la publication.
export default function PublicationTikTok({ ouvert, onFermer, produit }) {
  const toast = useToast();
  const [etat, setEtat] = useState(null); // compte connecté ou non
  const [createur, setCreateur] = useState(null); // infos TikTok du créateur
  const [erreur, setErreur] = useState("");
  const [form, setForm] = useState(null);
  const [envoi, setEnvoi] = useState(false);
  const [publication, setPublication] = useState(null);
  const minuterie = useRef(null); // suivi de l'état de la publication

  // Arrêt du suivi à la fermeture de la fenêtre
  useEffect(() => {
    if (!ouvert) clearInterval(minuterie.current);
    return () => clearInterval(minuterie.current);
  }, [ouvert]);

  // À chaque ouverture : état du compte + infos du créateur (exigé par TikTok)
  useEffect(() => {
    if (!ouvert) return;
    setErreur("");
    setCreateur(null);
    setPublication(null);
    setForm({ titre: (produit.nom || "").slice(0, 90), description: "", visibilite: "", commentaires: false,
      commercial: false, maMarque: false, sponsorise: false });
    apiClient.get("/tiktok/etat").then(({ data }) => {
      setEtat(data);
      if (data.configure && data.connecte) {
        apiClient.get("/tiktok/createur").then(({ data: c }) => setCreateur(c))
          .catch((err) => setErreur(messageErreur(err, "Infos du compte TikTok indisponibles")));
      }
    }).catch((err) => setErreur(messageErreur(err, "TikTok indisponible")));
  }, [ouvert, produit.nom]);

  // Suivi de l'état de la publication (toutes les 5 secondes, 2 minutes au plus)
  const suivre = useCallback((id) => {
    let essais = 0;
    clearInterval(minuterie.current);
    minuterie.current = setInterval(async () => {
      essais += 1;
      try {
        const { data } = await apiClient.get(`/tiktok/publications/${id}/statut`);
        setPublication(data);
        if (["PUBLISH_COMPLETE", "FAILED"].includes(data.statut) || essais >= 24) clearInterval(minuterie.current);
      } catch {
        clearInterval(minuterie.current);
      }
    }, 5000);
  }, []);

  const maj = (cle, valeur) => setForm((f) => ({ ...f, [cle]: valeur }));
  const options = createur?.privacy_level_options || [];
  const commentairesBloques = !!createur?.comment_disabled;
  // Publier est possible si : visibilité choisie, et en cas de contenu commercial, au moins une case cochée
  const peutPublier = form && form.visibilite && form.titre.trim()
    && (!form.commercial || form.maMarque || form.sponsorise) && !envoi;

  const publier = async () => {
    setEnvoi(true);
    try {
      const { data } = await apiClient.post("/tiktok/publications", {
        produit_id: produit.id, titre: form.titre, description: form.description, visibilite: form.visibilite,
        autoriser_commentaires: form.commentaires && !commentairesBloques, contenu_commercial: form.commercial,
        ma_marque: form.maMarque, contenu_sponsorise: form.sponsorise, accord: true,
      });
      setPublication(data);
      toast.succes("Publication envoyée à TikTok");
      suivre(data.id);
    } catch (err) {
      toast.erreur(messageErreur(err, "Publication impossible"));
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <Modal ouvert={ouvert} titre="Publier sur TikTok" onFermer={onFermer}>
      {!etat || !form ? <p className="text-sm text-gray-500">Chargement…</p> : (
        <div className="space-y-4">
          {erreur && <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{erreur}</p>}

          {!etat.configure && <p className="text-sm text-gray-600">La publication sur TikTok n'est pas encore activée sur adLyn.</p>}
          {etat.configure && !etat.connecte && (
            <p className="text-sm text-gray-600">
              Aucun compte TikTok n'est connecté.{" "}
              <Link to="/gestion/parametres?onglet=reseaux" className="font-semibold text-primary">Connecter le compte de la boutique →</Link>
            </p>
          )}

          {etat.connecte && publication && (
            <div className="space-y-2 text-center">
              <p className="text-lg font-semibold">{STATUTS[publication.statut] || publication.statut}</p>
              {publication.raison_echec && <p className="text-sm text-red-600">Motif : {publication.raison_echec}</p>}
              <p className="text-sm text-gray-500">TikTok peut mettre quelques minutes à publier le contenu.</p>
              <button type="button" className="btn-outline w-full" onClick={onFermer}>Fermer</button>
            </div>
          )}

          {etat.connecte && !publication && createur && (
            <>
              {/* Compte TikTok sur lequel le contenu sera publié */}
              <div className="flex items-center gap-3 rounded-xl bg-gray-50 p-3">
                {(createur.creator_avatar_url || etat.compte?.avatar_url) && (
                  <img src={createur.creator_avatar_url || etat.compte.avatar_url} alt="" className="h-10 w-10 rounded-full object-cover" />
                )}
                <p className="text-sm">Publication sur le compte <b>{createur.creator_nickname || etat.compte?.display_name}</b></p>
              </div>

              {/* Aperçu : la photo est publiée telle quelle, sans filigrane */}
              {produit.image_url && <img src={produit.image_url} alt="Aperçu" className="mx-auto max-h-48 rounded-xl object-contain" />}

              <div>
                <label className="label" htmlFor="tt-titre">Titre (Title)</label>
                <input id="tt-titre" className="input" maxLength={90} value={form.titre} onChange={(e) => maj("titre", e.target.value)} />
              </div>
              <div>
                <label className="label" htmlFor="tt-desc">Description <span className="font-normal text-gray-400">(facultatif, #hashtags possibles)</span></label>
                <textarea id="tt-desc" className="input min-h-[70px]" maxLength={4000} value={form.description}
                  onChange={(e) => maj("description", e.target.value)} />
              </div>

              <div>
                <label className="label" htmlFor="tt-vis">Qui peut voir cette publication ? (Who can view)</label>
                <select id="tt-vis" className="input" value={form.visibilite} onChange={(e) => maj("visibilite", e.target.value)}>
                  <option value="" disabled>Choisissez…</option>
                  {options.map((o) => (
                    <option key={o} value={o} disabled={o === "SELF_ONLY" && form.commercial && form.sponsorise}>
                      {VISIBILITES[o] || o}{o === "SELF_ONLY" && form.commercial && form.sponsorise ? " — impossible avec un contenu sponsorisé" : ""}
                    </option>
                  ))}
                </select>
              </div>

              <label className={`flex items-center gap-2 text-sm ${commentairesBloques ? "text-gray-400" : ""}`}>
                <input type="checkbox" checked={form.commentaires && !commentairesBloques} disabled={commentairesBloques}
                  onChange={(e) => maj("commentaires", e.target.checked)} />
                Autoriser les commentaires (Allow comment)
                {commentairesBloques && <span className="text-xs">— désactivés dans vos réglages TikTok</span>}
              </label>

              {/* Divulgation du contenu commercial (exigée par TikTok) */}
              <div className="space-y-2 rounded-xl border border-gray-200 p-3">
                <label className="flex items-center justify-between gap-2 text-sm font-semibold">
                  Contenu commercial (Disclose post content)
                  <input type="checkbox" checked={form.commercial}
                    onChange={(e) => setForm((f) => ({ ...f, commercial: e.target.checked, maMarque: false, sponsorise: false }))} />
                </label>
                {form.commercial && (
                  <>
                    <p className="text-xs text-gray-500">Indiquez si cette publication fait la promotion de votre marque ou d'un tiers.</p>
                    <label className="flex items-start gap-2 text-sm">
                      <input type="checkbox" className="mt-1" checked={form.maMarque} onChange={(e) => maj("maMarque", e.target.checked)} />
                      <span><b>Ma marque (Your brand)</b> — la publication sera étiquetée « Contenu promotionnel » (Promotional content).</span>
                    </label>
                    <label className={`flex items-start gap-2 text-sm ${form.visibilite === "SELF_ONLY" ? "text-gray-400" : ""}`}>
                      <input type="checkbox" className="mt-1" checked={form.sponsorise} disabled={form.visibilite === "SELF_ONLY"}
                        onChange={(e) => maj("sponsorise", e.target.checked)} />
                      <span><b>Contenu sponsorisé (Branded content)</b> — la publication sera étiquetée « Partenariat rémunéré » (Paid partnership).
                        {form.visibilite === "SELF_ONLY" && " Impossible en « Moi uniquement »."}</span>
                    </label>
                    {!form.maMarque && !form.sponsorise && <p className="text-xs text-orange-700">Cochez au moins une case pour publier.</p>}
                  </>
                )}
              </div>

              {/* Déclaration TikTok, affichée juste avant le bouton */}
              <p className="text-xs text-gray-600">
                En publiant, vous acceptez {form.commercial && form.sponsorise ? (
                  <>la <a href={LIEN_BRANDED} target="_blank" rel="noopener noreferrer" className="text-primary underline">Branded Content Policy</a> et </>
                ) : "la "}
                <a href={LIEN_MUSIQUE} target="_blank" rel="noopener noreferrer" className="text-primary underline">Music Usage Confirmation</a> de TikTok.
                {" "}(By posting, you agree to TikTok's {form.commercial && form.sponsorise ? "Branded Content Policy and " : ""}Music Usage Confirmation.)
              </p>
              <button type="button" className="btn-primary w-full" disabled={!peutPublier} onClick={publier}>
                {envoi ? "Envoi…" : "Publier sur TikTok"}
              </button>
            </>
          )}
        </div>
      )}
    </Modal>
  );
}
