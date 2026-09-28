import { useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { prix } from "@/lib/format";
import { lirePanier, viderPanier } from "@/lib/panier";

// COMMANDE (/b/:slug/commander) : coordonnées du client, mode de réception,
// mode de paiement, puis envoi de la commande à la boutique.
export default function Commander() {
  const { boutique } = useOutletContext();
  const navigate = useNavigate();

  // Le panier est lu une seule fois à l'ouverture de la page
  const [panier] = useState(() => lirePanier(boutique.slug));
  const lignes = Object.values(panier);
  const total = lignes.reduce((s, l) => s + l.produit.prix_vente * l.quantite, 0);

  // Champs du formulaire
  const [form, setForm] = useState({
    nom: "", telephone: "", email: "",
    mode_livraison: "RETRAIT", adresse_livraison: "", message_client: "",
    mode_paiement: "A_LA_LIVRAISON", numero_mobile_money: "",
  });
  const [envoi, setEnvoi] = useState(false); // vrai pendant l'envoi (bouton désactivé)
  const [erreur, setErreur] = useState(""); // message d'erreur renvoyé par l'API

  // Met à jour un champ du formulaire
  const champ = (cle) => (e) => setForm({ ...form, [cle]: e.target.value });

  // Panier vide (ex. page rechargée après commande) : retour au catalogue
  if (lignes.length === 0) {
    return (
      <div className="card mx-auto max-w-md py-12 text-center">
        <p className="text-5xl">🛒</p>
        <h1 className="mt-3 text-xl font-bold">Votre panier est vide</h1>
        <Link to={`/b/${boutique.slug}`} className="btn-boutique mt-5">Voir le catalogue</Link>
      </div>
    );
  }

  // Envoi de la commande à l'API
  const envoyer = async (e) => {
    e.preventDefault();
    setErreur("");
    setEnvoi(true);
    try {
      const { data } = await apiClient.post(`/public/b/${boutique.slug}/commandes`, {
        nom: form.nom.trim(),
        telephone: form.telephone.trim(),
        email: form.email.trim() || null,
        mode_livraison: form.mode_livraison,
        adresse_livraison: form.mode_livraison === "LIVRAISON" ? form.adresse_livraison.trim() : "",
        message_client: form.message_client.trim(),
        mode_paiement: form.mode_paiement,
        // Numéro Mobile Money : par défaut le téléphone du client
        numero_mobile_money: form.mode_paiement === "MOBILE_MONEY" ? (form.numero_mobile_money.trim() || form.telephone.trim()) : "",
        lignes: lignes.map((l) => ({ produit_id: l.produit.id, quantite: l.quantite })),
      });
      // Commande enregistrée : on vide le panier
      viderPanier(boutique.slug);
      if (data.redirect_url) {
        // Paiement Mobile Money : on part sur la page de paiement sécurisée PawaPay
        window.location.href = data.redirect_url;
        return;
      }
      // Paiement à la réception : page de remerciement avec le numéro de commande
      navigate(`/b/${boutique.slug}/merci?numero=${encodeURIComponent(data.numero)}&telephone=${encodeURIComponent(data.telephone)}`);
    } catch (err) {
      // Stock insuffisant, téléphone invalide, adresse manquante...
      setErreur(messageErreur(err, "La commande n'a pas pu être enregistrée. Vérifiez vos informations."));
      window.scrollTo({ top: 0, behavior: "smooth" });
      setEnvoi(false);
    }
  };

  const mobileMoney = Boolean(boutique.paiement_mobile_money);

  return (
    <div className="space-y-4">
      <Link to={`/b/${boutique.slug}/panier`} className="text-sm font-semibold text-boutique">← Retour au panier</Link>
      <h1 className="text-2xl font-extrabold">Finaliser ma commande</h1>

      {/* Message d'erreur de l'API (ex. stock insuffisant) */}
      {erreur && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700">⚠️ {erreur}</div>}

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <form onSubmit={envoyer} className="space-y-4">
          {/* ---------- 1. Coordonnées ---------- */}
          <section className="card space-y-3">
            <h2 className="text-lg font-bold">1. Vos coordonnées</h2>
            <div>
              <label className="label" htmlFor="nom">Nom complet *</label>
              <input id="nom" className="input" required minLength={2} autoComplete="name" value={form.nom} onChange={champ("nom")} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="telephone">Téléphone *</label>
                <input id="telephone" className="input" type="tel" required minLength={8} inputMode="tel" autoComplete="tel"
                  placeholder="70 00 00 00" value={form.telephone} onChange={champ("telephone")} />
              </div>
              <div>
                <label className="label" htmlFor="email">E-mail <span className="font-normal text-gray-400">(facultatif)</span></label>
                <input id="email" className="input" type="email" autoComplete="email" value={form.email} onChange={champ("email")} />
              </div>
            </div>
            <p className="text-xs text-gray-500">Votre téléphone vous servira à suivre votre commande. Avec un e-mail, vous serez prévenu à chaque étape.</p>
          </section>

          {/* ---------- 2. Mode de réception ---------- */}
          <section className="card space-y-3">
            <h2 className="text-lg font-bold">2. Réception</h2>
            <div className="grid gap-2 sm:grid-cols-2">
              <Choix nom="livraison" valeur="RETRAIT" actuel={form.mode_livraison} onChange={champ("mode_livraison")}
                titre="🏪 Retrait en boutique" texte={boutique.ville ? `À ${boutique.ville}` : "Dès que la commande est prête"} />
              <Choix nom="livraison" valeur="LIVRAISON" actuel={form.mode_livraison} onChange={champ("mode_livraison")}
                titre="🛵 Livraison" texte="À l'adresse de votre choix" />
            </div>
            {/* Adresse : obligatoire seulement pour une livraison */}
            {form.mode_livraison === "LIVRAISON" && (
              <div>
                <label className="label" htmlFor="adresse">Adresse de livraison *</label>
                <textarea id="adresse" className="input" rows={2} required placeholder="Quartier, rue, repère…"
                  value={form.adresse_livraison} onChange={champ("adresse_livraison")} />
              </div>
            )}
            <div>
              <label className="label" htmlFor="message">Message pour la boutique <span className="font-normal text-gray-400">(facultatif)</span></label>
              <textarea id="message" className="input" rows={2} placeholder="Couleur souhaitée, horaire de passage…"
                value={form.message_client} onChange={champ("message_client")} />
            </div>
          </section>

          {/* ---------- 3. Mode de paiement ---------- */}
          <section className="card space-y-3">
            <h2 className="text-lg font-bold">3. Paiement</h2>
            <div className="grid gap-2">
              <Choix nom="paiement" valeur="A_LA_LIVRAISON" actuel={form.mode_paiement} onChange={champ("mode_paiement")}
                titre={form.mode_livraison === "LIVRAISON" ? "💵 Payer à la livraison" : "💵 Payer au retrait"}
                texte="En espèces ou Mobile Money, à la réception de votre commande" />
              {/* Mobile Money : proposé seulement si la boutique l'accepte */}
              {mobileMoney && (
                <Choix nom="paiement" valeur="MOBILE_MONEY" actuel={form.mode_paiement} onChange={champ("mode_paiement")}
                  titre="📲 Payer maintenant par Mobile Money" texte="Orange Money, Moov Money… sur une page de paiement sécurisée" />
              )}
            </div>
            {form.mode_paiement === "MOBILE_MONEY" && (
              <div>
                <label className="label" htmlFor="numero_mm">Numéro Mobile Money <span className="font-normal text-gray-400">(facultatif)</span></label>
                <input id="numero_mm" className="input" type="tel" inputMode="tel" placeholder={form.telephone || "Par défaut : votre téléphone"}
                  value={form.numero_mobile_money} onChange={champ("numero_mobile_money")} />
                <p className="mt-1 text-xs text-gray-500">Vous validerez le paiement sur votre téléphone. Aucun code secret n'est demandé sur ce site.</p>
              </div>
            )}
          </section>

          {/* Bouton d'envoi (en bas du formulaire) */}
          <button type="submit" className="btn-boutique w-full py-3.5 text-base" disabled={envoi}>
            {envoi
              ? "Envoi en cours…"
              : form.mode_paiement === "MOBILE_MONEY"
                ? `Commander et payer ${prix(total, boutique.devise)}`
                : `Valider ma commande (${prix(total, boutique.devise)})`}
          </button>
        </form>

        {/* ---------- Récapitulatif du panier ---------- */}
        <aside className="card h-fit space-y-3 lg:sticky lg:top-24">
          <h2 className="font-bold">Récapitulatif</h2>
          <ul className="space-y-2 text-sm">
            {lignes.map(({ produit, quantite }) => (
              <li key={produit.id} className="flex justify-between gap-3">
                <span className="text-gray-700"><b>{quantite} ×</b> {produit.nom}</span>
                <span className="shrink-0 font-semibold">{prix(produit.prix_vente * quantite, boutique.devise)}</span>
              </li>
            ))}
          </ul>
          <div className="flex items-baseline justify-between border-t border-gray-100 pt-3">
            <span className="font-bold">Total</span>
            <span className="text-2xl font-extrabold text-accent">{prix(total, boutique.devise)}</span>
          </div>
        </aside>
      </div>
    </div>
  );
}

// Grande case à cocher « radio » cliquable (un choix parmi plusieurs)
function Choix({ nom, valeur, actuel, onChange, titre, texte }) {
  const coche = valeur === actuel;
  return (
    <label className={`flex cursor-pointer items-start gap-3 rounded-xl border-2 p-3 transition ${coche ? "border-boutique bg-gray-50" : "border-gray-200 hover:border-gray-300"}`}>
      <input type="radio" name={nom} value={valeur} checked={coche} onChange={onChange} className="mt-1 h-4 w-4 accent-[var(--couleur-boutique)]" />
      <span>
        <span className="block font-semibold">{titre}</span>
        <span className="block text-sm text-gray-500">{texte}</span>
      </span>
    </label>
  );
}
