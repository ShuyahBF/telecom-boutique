import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import Chargement from "@/components/Chargement";
import { useToast } from "@/components/Toast";

// État de la fiche du catalogue public d'un modèle : libellé + couleur du badge
function etatFiche(fiche) {
  if (!fiche) return { code: "A_CREER", libelle: "Pas encore de fiche", couleur: "bg-orange-100 text-orange-800" };
  if (fiche.publie) return { code: "PUBLIEE", libelle: "✅ Fiche publiée", couleur: "bg-green-100 text-green-800" };
  if (fiche.statut === "PRET") return { code: "PRETE", libelle: "🕚 Prête, publiée ce soir", couleur: "bg-blue-100 text-blue-800" };
  return { code: "BROUILLON", libelle: "📝 Fiche en brouillon", couleur: "bg-gray-100 text-gray-700" };
}

// Filtres proposés au-dessus de la liste
const FILTRES = [
  ["", "Tous"], ["A_CREER", "Sans fiche"], ["BROUILLON", "En brouillon"], ["PRETE", "Prêtes"], ["PUBLIEE", "Publiées"],
];

// « Modèles vendus dans mes boutiques » (super-admin) : les téléphones que les
// boutiques ont créés elles-mêmes, regroupés par modèle et classés par nombre
// de boutiques qui les vendent. Sert à choisir PAR OÙ COMMENCER le catalogue
// public : les modèles les plus vendus sans fiche d'abord.
// Seule l'identité des modèles est montrée : jamais les prix ni les documents
// privés des boutiques.
export default function ModelesVendus() {
  const toast = useToast();
  const navigate = useNavigate();
  const [modeles, setModeles] = useState(null);
  const [q, setQ] = useState("");
  const [filtre, setFiltre] = useState("");
  const [creation, setCreation] = useState(""); // clé du modèle dont la fiche est en cours de création

  // Chargement de la liste (calculée par le serveur à chaque appel)
  useEffect(() => {
    apiClient.get("/plateforme/referentiel/demande")
      .then(({ data }) => setModeles(data))
      .catch((err) => { toast.erreur(messageErreur(err, "Liste indisponible")); setModeles([]); });
  }, [toast]);

  // Création de la fiche du catalogue public pour ce modèle, puis ouverture pour relecture
  async function creerFiche(m, avecAssistant) {
    setCreation(m.cle);
    try {
      const { data } = await apiClient.post("/plateforme/referentiel/demande/fiche", {
        marque: m.marque, nom: m.nom, codes_modele: m.codes_modele, referentiel_cle: m.referentiel_cle,
        avec_assistant: avecAssistant,
      }, { timeout: 240000 });
      if (data.existante) toast.info("Une fiche existait déjà sous ce code modèle : elle est maintenant reliée.");
      else if (avecAssistant && data.proposition && !data.proposition.trouve) {
        toast.info(`Fiche créée, mais l'assistant n'a pas trouvé le modèle : ${data.proposition.remarques || ""}`);
      } else toast.succes("Fiche créée en brouillon : relisez-la puis passez-la en « Prête » pour la publier ce soir.");
      navigate(`/plateforme/catalogue?fiche=${data.fiche.id}`);
    } catch (err) {
      toast.erreur(messageErreur(err, "Création de la fiche impossible"));
    } finally {
      setCreation("");
    }
  }

  if (!modeles) return <Chargement />;

  // Compteurs par état + filtrage (texte et état)
  const avecEtat = modeles.map((m) => ({ ...m, etat: etatFiche(m.fiche) }));
  const compte = (code) => avecEtat.filter((m) => m.etat.code === code).length;
  const texte = q.trim().toLowerCase();
  const affiches = avecEtat.filter((m) => (!filtre || m.etat.code === filtre)
    && (!texte || [m.marque, m.nom, ...m.codes_modele].some((v) => (v || "").toLowerCase().includes(texte))));

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">
        Téléphones créés par les boutiques elles-mêmes, classés par nombre de boutiques qui les vendent.
        Créez d'abord les fiches des plus vendus : à la publication, les boutiques qui les ont déjà sont reliées
        à la fiche (sans doublon, prix inchangés) et les autres la reçoivent.
      </p>

      {/* Chiffres clés */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[["Modèles vendus", modeles.length], ["Sans fiche", compte("A_CREER")],
          ["En préparation", compte("BROUILLON") + compte("PRETE")], ["Publiés", compte("PUBLIEE")]].map(([libelle, n]) => (
          <div key={libelle} className="card p-3">
            <p className="text-xs text-gray-500">{libelle}</p>
            <p className="text-2xl font-extrabold">{n}</p>
          </div>
        ))}
      </div>

      {/* Recherche + filtre par état */}
      <div className="flex flex-wrap items-center gap-3">
        <input className="input max-w-sm" placeholder="Marque, nom ou code modèle…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="flex flex-wrap gap-1">
          {FILTRES.map(([code, libelle]) => (
            <button key={code} type="button" onClick={() => setFiltre(code)}
              className={`rounded-full px-3 py-1 text-sm font-semibold ${filtre === code ? "bg-primary text-white" : "bg-white text-gray-600 ring-1 ring-gray-200"}`}>
              {libelle}
            </button>
          ))}
        </div>
      </div>

      {/* Liste des modèles */}
      {affiches.length === 0 ? (
        <div className="card text-center text-gray-600">
          {modeles.length === 0 ? "Aucune boutique n'a encore créé ses propres téléphones." : "Aucun modèle ne correspond."}
        </div>
      ) : (
        <div className="card divide-y divide-gray-100 p-0">
          {affiches.map((m) => (
            <div key={m.cle} className="flex flex-wrap items-center gap-3 px-4 py-3">
              {/* Nombre de boutiques qui vendent ce modèle */}
              <span className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-xl bg-primary/10 text-primary" title="Boutiques qui le vendent">
                <span className="text-lg font-extrabold leading-none">{m.nb_boutiques}</span>
                <span className="text-[10px]">boutique{m.nb_boutiques > 1 ? "s" : ""}</span>
              </span>
              <div className="min-w-0 flex-1">
                {/* La marque n'est pas répétée si le nom la contient déjà (« itel A70 ») */}
                <p className="font-semibold">{m.nom.toLowerCase().startsWith(m.marque.toLowerCase()) ? m.nom : `${m.marque} ${m.nom}`}</p>
                <p className="truncate font-mono text-xs text-gray-500">{m.codes_modele.join(" · ") || "code modèle non renseigné"}</p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  <span className={`badge ${m.etat.couleur}`}>{m.etat.libelle}</span>
                  {m.referentiel_cle
                    ? <span className="badge bg-green-50 text-green-800">🌍 Référentiel mondial</span>
                    : <span className="badge bg-gray-50 text-gray-500" title="La boutique n'a pas choisi le modèle dans la liste mondiale">Saisie libre</span>}
                </div>
              </div>
              {m.fiche ? (
                <button type="button" className="btn-outline btn-sm" onClick={() => navigate(`/plateforme/catalogue?fiche=${m.fiche.id}`)}>
                  Ouvrir la fiche →
                </button>
              ) : (
                <div className="flex w-full gap-2 sm:w-auto">
                  <button type="button" className="btn-outline btn-sm flex-1" disabled={!!creation} onClick={() => creerFiche(m, false)}>Créer la fiche</button>
                  <button type="button" className="btn-primary btn-sm flex-1" disabled={!!creation} onClick={() => creerFiche(m, true)}>
                    {creation === m.cle ? "Recherche…" : "🔎 Créer + rechercher"}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
