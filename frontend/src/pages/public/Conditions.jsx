import { Link } from "react-router-dom";
import PageLegale, { Section } from "@/components/PageLegale";

// Contact officiel de SAWALI SMART SYSTEMS (e-mail et téléphone)
const CONTACT = "contact@sawalismartsystems.com";
const TELEPHONE = "+226 25 65 81 65";

// Conditions d'utilisation d'adLyn (adresses /conditions, /terms, /terms-of-service).
export default function Conditions() {
  return (
    <PageLegale
      titreOnglet="adLyn Terms of Service"
      titre="adLyn Terms of Service"
      sousTitre="Conditions d'utilisation"
      miseAJour="29 septembre 2026"
    >
      <Section titre="1. Objet">
        <p>
          Ces conditions encadrent l'utilisation d'adLyn (<a className="text-primary hover:underline" href="https://adlynservice.com">adlynservice.com</a>),
          plateforme éditée et exploitée par <b>SAWALI SMART SYSTEMS</b> (Ouagadougou, Burkina Faso). En utilisant
          adLyn, vous acceptez ces conditions.
        </p>
      </Section>

      <Section titre="2. Le service">
        <p>
          adLyn fournit aux boutiques de téléphonie un outil de gestion (ventes, stock, réparations, clients) et une
          vitrine en ligne où leurs clients peuvent consulter le catalogue, commander, payer et suivre leurs commandes
          et réparations.
        </p>
        <p>
          <b>Chaque boutique est le vendeur</b> des produits et services qu'elle présente : elle fixe ses prix, assure
          la livraison, la garantie, les réparations et le service après-vente. adLyn fournit l'outil technique et
          n'est pas partie au contrat de vente entre la boutique et son client.
        </p>
      </Section>

      <Section titre="3. Commandes et paiements">
        <ul className="list-disc space-y-1 pl-6">
          <li>Les prix sont affichés en francs CFA par chaque boutique.</li>
          <li>Le paiement se fait à la livraison ou par Mobile Money via notre prestataire PawaPay.</li>
          <li>Les paiements Mobile Money sont encaissés par SAWALI SMART SYSTEMS pour le compte de la boutique, puis lui sont reversés.</li>
          <li>Les annulations, retours et remboursements se règlent avec la boutique, selon ses propres conditions et la loi applicable.</li>
        </ul>
      </Section>

      <Section titre="4. Comptes des boutiques">
        <ul className="list-disc space-y-1 pl-6">
          <li>Les boutiques sont créées par notre équipe ; leur dossier d'identification doit être validé avant l'activation des paiements en ligne.</li>
          <li>Chaque membre du personnel a son propre compte et garde son mot de passe confidentiel ; la boutique répond des actions faites avec ses comptes.</li>
          <li>L'accès est soumis à un abonnement, après une période d'essai ; les formules et prix sont indiqués dans l'espace de la boutique. Le service SMS est facturé à part.</li>
          <li>En cas d'impayé ou de manquement à ces conditions, nous pouvons suspendre l'accès de la boutique ou de certains services.</li>
        </ul>
      </Section>

      <Section titre="5. Publication sur les réseaux sociaux (TikTok…)">
        <p>
          Une boutique peut connecter son propre compte TikTok (ou d'autres réseaux sociaux) pour y publier les
          photos et vidéos de ses produits. Dans ce cas :
        </p>
        <ul className="list-disc space-y-1 pl-6">
          <li>rien n'est publié sans l'action et l'accord explicite de la boutique, qui choisit le contenu, la légende et la visibilité ;</li>
          <li>la boutique respecte les <a className="text-primary hover:underline" href="https://www.tiktok.com/legal/terms-of-service" target="_blank" rel="noopener noreferrer">Conditions d'utilisation</a> et les <a className="text-primary hover:underline" href="https://www.tiktok.com/community-guidelines" target="_blank" rel="noopener noreferrer">Règles communautaires</a> de TikTok, y compris l'obligation d'indiquer les contenus commerciaux ;</li>
          <li>la boutique ne publie que des contenus dont elle détient les droits ;</li>
          <li>la boutique peut déconnecter son compte à tout moment, depuis adLyn ou depuis TikTok.</li>
        </ul>
      </Section>

      <Section titre="6. Utilisations interdites">
        <ul className="list-disc space-y-1 pl-6">
          <li>vendre des produits illicites, contrefaits ou volés ;</li>
          <li>publier des informations fausses ou trompeuses ;</li>
          <li>tenter d'accéder aux données d'une autre boutique ou de contourner la sécurité de la plateforme ;</li>
          <li>envoyer des messages non sollicités (spam).</li>
        </ul>
      </Section>

      <Section titre="7. Propriété intellectuelle">
        <p>
          La plateforme adLyn, son nom, son logo et son code appartiennent à SAWALI SMART SYSTEMS. Chaque boutique
          reste propriétaire de ses contenus (logo, photos, textes) et nous autorise à les afficher sur adLyn.
        </p>
      </Section>

      <Section titre="8. Responsabilité">
        <p>
          Nous faisons le nécessaire pour qu'adLyn fonctionne en continu et en sécurité, sans pouvoir garantir
          l'absence totale d'interruption. Nous ne sommes pas responsables des produits vendus par les boutiques ni des
          services de tiers (opérateurs Mobile Money, réseaux sociaux).
        </p>
      </Section>

      <Section titre="9. Données personnelles">
        <p>
          L'utilisation de vos données est décrite dans notre{" "}
          <Link className="text-primary hover:underline" to="/confidentialite">Politique de confidentialité</Link>.
        </p>
      </Section>

      <Section titre="10. Droit applicable, modifications et contact">
        <p>
          Ces conditions sont régies par le droit du Burkina Faso ; à défaut d'accord amiable, les tribunaux de
          Ouagadougou sont compétents. Nous pouvons les modifier ; la date en haut de la page indique la dernière
          version. Contact : <a className="text-primary hover:underline" href={`mailto:${CONTACT}`}>{CONTACT}</a> ·{" "}
          <a className="text-primary hover:underline" href="tel:+22625658165">{TELEPHONE}</a>.
        </p>
      </Section>

      {/* Résumé en anglais pour les lecteurs non francophones (revues d'applications) */}
      <Section titre="Summary in English">
        <p>
          adLyn is a platform operated by SAWALI SMART SYSTEMS (Ouagadougou, Burkina Faso) that gives mobile phone
          shops a management tool and an online storefront. Each shop is the seller of its own products. A shop may
          connect its own TikTok account to publish its product photos and videos; nothing is posted without the
          shop's explicit action, and the shop must comply with TikTok's Terms of Service and Community Guidelines,
          including commercial content disclosure. Contact: {CONTACT}, {TELEPHONE}.
        </p>
      </Section>
    </PageLegale>
  );
}
