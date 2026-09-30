import { Link } from "react-router-dom";
import PageLegale, { Section } from "@/components/PageLegale";

// Contact officiel de SAWALI SMART SYSTEMS (e-mail et téléphone)
const CONTACT = "contact@sawalismartsystems.com";
const TELEPHONE = "+226 25 65 81 65";

// Politique de confidentialité d'adLyn (adresses /confidentialite, /privacy, /privacy-policy).
// Elle décrit ce que la plateforme fait réellement des données : à mettre à jour
// à chaque nouvelle fonction qui touche aux données personnelles.
export default function Confidentialite() {
  return (
    <PageLegale
      titreOnglet="adLyn Privacy Policy"
      titre="adLyn Privacy Policy"
      sousTitre="Politique de confidentialité"
      miseAJour="29 septembre 2026"
    >
      <Section titre="1. Qui sommes-nous ?">
        <p>
          adLyn (<a className="text-primary hover:underline" href="https://adlynservice.com">adlynservice.com</a>) est
          une plateforme en ligne pour les boutiques de téléphonie : vitrine en ligne, commandes, suivi des réparations
          et gestion de la boutique. adLyn est un produit de <b>SAWALI SMART SYSTEMS</b>, société basée à Ouagadougou
          (Burkina Faso), qui l'édite, l'exploite et en est le responsable de traitement.
        </p>
        <p>
          Chaque boutique présente sur adLyn vend ses propres produits et services. Pour les commandes, réparations et
          demandes de conseil passées auprès d'une boutique, cette boutique utilise aussi vos données pour vous servir.
        </p>
      </Section>

      <Section titre="2. Données que nous collectons">
        <p><b>Clients des boutiques</b> (sans compte) :</p>
        <ul className="list-disc space-y-1 pl-6">
          <li>commande : nom complet, téléphone, e-mail (facultatif), adresse de livraison, message pour la boutique, produits commandés ;</li>
          <li>paiement Mobile Money : numéro Mobile Money et état du paiement (le code secret Mobile Money n'est jamais demandé ni connu d'adLyn) ;</li>
          <li>demande de conseil et suivi de réparation : nom, téléphone, e-mail (facultatif), messages échangés, appareil déposé et état de la réparation ;</li>
          <li>accord facultatif pour recevoir les offres d'une boutique par WhatsApp.</li>
        </ul>
        <p><b>Personnel des boutiques</b> (comptes) : nom, e-mail, téléphone, rôle, mot de passe (enregistré uniquement sous forme chiffrée irréversible), journal des connexions (date, adresse IP, identifiant de l'appareil).</p>
        <p><b>Boutiques</b> : informations de la boutique (nom, adresse, position GPS, contacts, logo) et dossier d'identification (pièce d'identité du dirigeant, IFU, RCCM, CNSS), rangé dans un espace de stockage privé.</p>
        <p>
          <b>Comptes de réseaux sociaux</b> : si une boutique connecte son compte TikTok ou un autre réseau social pour
          publier ses produits, nous recevons, avec son accord, les informations de base de ce compte (identifiant,
          nom affiché, photo de profil) et un jeton d'accès. Ces données servent uniquement à publier les contenus
          que la boutique choisit, depuis son espace adLyn.
        </p>
      </Section>

      <Section titre="3. Pourquoi nous utilisons ces données">
        <ul className="list-disc space-y-1 pl-6">
          <li>traiter les commandes, paiements, réparations et demandes de conseil, et vous en informer (e-mail, SMS, WhatsApp) ;</li>
          <li>reverser aux boutiques les paiements encaissés pour elles ;</li>
          <li>vérifier l'identité des boutiques avant d'activer les paiements en ligne ;</li>
          <li>gérer les comptes du personnel, les abonnements et la facturation des boutiques ;</li>
          <li>sécuriser la plateforme (protection contre les accès frauduleux, journal des connexions) ;</li>
          <li>publier, à la demande d'une boutique, ses contenus sur ses propres comptes de réseaux sociaux.</li>
        </ul>
        <p>Nous ne vendons pas vos données, nous ne les louons pas et nous ne les utilisons pas pour de la publicité ciblée.</p>
      </Section>

      <Section titre="4. Prestataires qui traitent des données pour nous">
        <ul className="list-disc space-y-1 pl-6">
          <li>Render (hébergement du site et de l'API) ;</li>
          <li>MongoDB Atlas (base de données) ;</li>
          <li>Cloudflare R2 (stockage des photos, logos et documents, dont un espace privé pour les dossiers d'identification) ;</li>
          <li>PawaPay (paiement Mobile Money) ;</li>
          <li>Orange, OVH et WhatsApp (Meta) pour les SMS et messages ;</li>
          <li>Google Drive (sauvegardes chiffrées) ;</li>
          <li>TikTok et les autres réseaux sociaux qu'une boutique choisit de connecter, pour publier ses contenus.</li>
        </ul>
        <p>
          L'assistant de recherche du catalogue (Anthropic) ne lit que les fiches techniques publiques des fabricants,
          jamais les données des clients ou des boutiques.
        </p>
      </Section>

      <Section titre="5. Cookies et stockage dans le navigateur">
        <p>adLyn n'utilise aucun cookie publicitaire ni outil de suivi. Seuls sont utilisés :</p>
        <ul className="list-disc space-y-1 pl-6">
          <li>le cookie de session du personnel (sécurisé, illisible par le site, 30 jours) ;</li>
          <li>un cookie qui retient l'ID de la boutique sur l'écran de connexion (1 an) ;</li>
          <li>le panier d'achat, gardé dans votre navigateur ;</li>
          <li>un identifiant d'appareil, pour la sécurité des connexions du personnel.</li>
        </ul>
      </Section>

      <Section titre="6. Durée de conservation">
        <p>
          Les données sont gardées tant que la boutique utilise adLyn, puis le temps imposé par la loi : notamment
          10 ans pour les factures et pièces comptables (droit OHADA). Le journal des connexions est gardé le temps
          nécessaire à la sécurité. Les jetons d'accès aux réseaux sociaux sont supprimés dès que la boutique
          déconnecte son compte.
        </p>
      </Section>

      <Section titre="7. Sécurité">
        <p>
          Connexions chiffrées (HTTPS), mots de passe chiffrés de façon irréversible, blocage après plusieurs échecs de
          connexion, règles d'accès par adresse IP ou appareil, cloisonnement strict des données entre boutiques,
          dossiers d'identification en stockage privé, jetons d'accès chiffrés, sauvegardes chiffrées.
        </p>
      </Section>

      <Section titre="8. Vos droits">
        <p>
          Conformément à la loi burkinabè n° 001-2021/AN sur la protection des données à caractère personnel, vous
          pouvez demander l'accès à vos données, leur correction, leur suppression, ou vous opposer à leur
          utilisation. Écrivez à <a className="text-primary hover:underline" href={`mailto:${CONTACT}`}>{CONTACT}</a>.
          Vous pouvez aussi saisir la Commission de l'Informatique et des Libertés (CIL) du Burkina Faso.
        </p>
        <p>
          Une boutique peut à tout moment déconnecter son compte TikTok depuis adLyn ; elle peut aussi retirer l'accès
          depuis les paramètres de son compte TikTok.
        </p>
      </Section>

      <Section titre="9. Mineurs">
        <p>Les comptes adLyn sont réservés aux adultes (18 ans ou plus) qui travaillent pour une boutique.</p>
      </Section>

      <Section titre="10. Modifications et contact">
        <p>
          Nous pouvons modifier cette politique ; la date en haut de la page indique la dernière version. Pour toute
          question : <a className="text-primary hover:underline" href={`mailto:${CONTACT}`}>{CONTACT}</a> ·{" "}
          <a className="text-primary hover:underline" href="tel:+22625658165">{TELEPHONE}</a> — SAWALI SMART SYSTEMS,
          Ouagadougou, Burkina Faso. Voir aussi nos{" "}
          <Link className="text-primary hover:underline" to="/conditions">Conditions d'utilisation</Link>.
        </p>
      </Section>

      {/* Résumé en anglais pour les lecteurs non francophones (revues d'applications) */}
      <Section titre="Summary in English">
        <p>
          adLyn is operated by SAWALI SMART SYSTEMS (Ouagadougou, Burkina Faso). We collect only what is needed to
          process orders, payments, repairs and shop accounts. If a shop connects its TikTok account, we receive its
          basic profile information (open ID, display name, avatar) and an access token, used solely to publish the
          content the shop chooses; the token is encrypted and deleted when the shop disconnects. We do not sell
          personal data or use it for targeted advertising. Contact: {CONTACT}, {TELEPHONE}.
        </p>
      </Section>
    </PageLegale>
  );
}
