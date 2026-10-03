# adLyn — plateforme SaaS multi-boutiques de téléphonie

Plateforme en ligne pour des boutiques de téléphonie : vente de téléphones et d'accessoires, stock, réparations (SAV), factures et proformas, clients et fournisseurs, messagerie, portail public avec paiement Mobile Money. Chaque boutique (« tenant ») a ses données **strictement séparées** de celles des autres.

Même architecture que beauthentik.net (`ShuyahBF/site-meetafrican`) :

| Partie | Technologie | Hébergement |
|---|---|---|
| API | Python 3.11, FastAPI, Motor (MongoDB) | Render (service web) |
| Site | React 19, Vite, Tailwind CSS | Render (site statique) |
| Base de données | MongoDB Atlas (collections préfixées `tlb_`) | Atlas |
| Fichiers publics (photos, logos, documents) | Cloudflare R2, bucket public | Cloudflare |
| Fichiers privés (KYC, sauvegardes avant restauration) | Cloudflare R2, bucket privé | Cloudflare |
| Paiement en ligne | PawaPay (Orange Money, Moov Money, Telecel…) | — |
| Sauvegardes | Archives chiffrées AES-256 sur Google Drive | Drive du propriétaire |

## Fonctionnalités

### Pour le public (sans compte)
- **Page d'accueil** : carrousel glissant de toutes les boutiques, recherche par nom ou par **code marchand**, **scan du QR code** d'une boutique.
- **Vitrine de chaque boutique** (`/b/<boutique>`) :
  - catalogue avec recherche et filtres, fiche produit (caractéristiques, pièces compatibles, documents, conseils d'utilisation) ;
  - panier, commande avec paiement à la livraison ou **Mobile Money (PawaPay)** ;
  - **suivi de commande** (n° + téléphone), **suivi de réparation** (n° de dossier + téléphone ou code de suivi) ;
  - **demande de conseil** (fil de discussion privé avec la boutique).

### Pour chaque boutique (back-office `/gestion`)
- **Tableau de bord** : chiffre d'affaires, ventes des 30 derniers jours, commandes à traiter, réparations en retard, stock en alerte, nouveautés du catalogue.
- **Factures et proformas sur plusieurs lignes** :
  - remise et TVA par ligne, prix TTC ou HT ;
  - conversion proforma → facture ;
  - validation : numéro définitif sans trou + sortie de stock ;
  - annulation : le stock est réintégré ;
  - règlements partiels, montant en lettres, impression A4 / PDF.
- **Stock** : journal de toutes les entrées et sorties, bons de réception fournisseur sur plusieurs lignes, mouvements manuels. Le stock n'est jamais modifié à la main.
- **Maintenance (SAV)** :
  - numéro de dossier + code de suivi automatiques ;
  - bon de dépôt A5 avec QR code, historique des statuts ;
  - pièces utilisées (sortie de stock), facture de réparation.
- **Catalogue** : copie du catalogue public (prix, stock et visibilité propres à la boutique), téléphones propres à la boutique, documents privés (brochures, fiches techniques, manuels).
- **Clients, fournisseurs, commandes en ligne, messagerie** (demandes de conseil).
- **Historique des paiements** par période : PawaPay, espèces, Orange Money, Moov Money…, réussis, échoués, en attente ou annulés, avec export Excel.
- **Paramètres** :
  - fiche de la boutique, logo, couleur, géolocalisation ;
  - dossier **KYC** (pièce d'identité du DG, IFU, CNSS, RCCM) ;
  - QR code et affiche imprimable ;
  - e-mails (serveur SMTP, textes des messages, journal des envois) ;
  - équipe.

**Rôles** (droits définis dans une seule table, `PERMISSIONS` dans `backend/auth.py`) :

| Rôle | Droits |
|---|---|
| DG | Tout, y compris paramètres, équipe et KYC |
| Commercial | Catalogue, clients, proformas/factures, commandes, conseils, stock |
| Secrétaire | Accueil clients, dépôts SAV, commandes, messagerie |
| Comptable | Factures et règlements, historique des paiements, stock, fournisseurs |
| Technicien | SAV, pièces détachées, consultation du catalogue |

### Connexion du personnel
- Identifiants : **ID boutique** (code unique de 6 lettres ou chiffres, ex. `K7M2QD`, créé automatiquement) + **e-mail OU numéro de téléphone** (un seul champ « E-mail ou téléphone ») + **mot de passe personnel**. L'identifiant interne de la boutique n'est jamais montré.
- Un compte a au moins un identifiant : e-mail, téléphone, ou les deux. Chacun est **unique sur toute la plateforme**. Le téléphone est enregistré au format international (`70 12 34 56` devient `+22670123456` ; on peut le taper avec ou sans `+226`).
- L'ID boutique est retenu par le navigateur. La session reste ouverte **30 jours** dans un cookie sécurisé (HttpOnly, illisible par le JavaScript) : le site se reconnecte tout seul à son ouverture. **Le mot de passe n'est jamais enregistré sur l'appareil.**
- Un mot de passe **provisoire** (reçu par e-mail/SMS, ou donné par le DG) doit être changé à la première connexion. Changer son mot de passe déconnecte les autres appareils.
- Anti force brute : après 10 échecs en 15 minutes, le compte est bloqué 15 minutes.
- L'administrateur de la plateforme se connecte sans ID boutique (lien « Administrateur ? »).

### Mot de passe oublié, changement d'e-mail ou de téléphone
- **Mot de passe oublié** : lien « Mot de passe oublié ? » sur la page de connexion. Saisir l'ID boutique et son e-mail ou son téléphone : un **code à 6 chiffres** est envoyé **par WhatsApp en priorité**, par SMS si WhatsApp ne passe pas, ou par e-mail si le compte n'a qu'un e-mail. Saisir le code et le nouveau mot de passe : toutes les sessions ouvertes du compte sont fermées.
- **Sécurité du code** : jamais enregistré en clair ni affiché, valable **10 minutes**, **5 essais** puis blocage de **15 minutes** ; **1 envoi par minute et 5 par heure**, par compte et par adresse IP. La réponse est la même que le compte existe ou non.
- **Changer son e-mail ou son téléphone** : bouton 👤 « Mon compte » (en haut du back-office). Mot de passe actuel + nouvelle valeur : le code part **vers la nouvelle valeur** (WhatsApp/SMS pour un numéro, e-mail pour une adresse), puis on le saisit. Le bouton « Vérifier » confirme de la même façon un identifiant déjà présent. On peut **retirer** son e-mail si son téléphone est vérifié (et inversement), jamais les deux. L'ancien et le nouveau contact sont prévenus.
- **Par le DG** (Paramètres > Équipe) : créer un membre avec un téléphone seulement (l'e-mail est facultatif) ; ses accès provisoires lui sont envoyés par WhatsApp, sinon SMS, sinon e-mail, et le DG voit le résultat réel (si rien n'a pu partir, le mot de passe provisoire lui est affiché une fois, à remettre en main propre). Boutons « ✏️ Identifiants » (modifier l'e-mail / le téléphone d'un membre, sans code : le membre est prévenu sur l'ancien et le nouveau contact) et « 📲 Nouveau mot de passe » (mot de passe provisoire envoyé, anciennes sessions fermées). « 📜 Historique des identifiants » liste toutes ces actions.
- **Par l'administrateur** (`/plateforme`) : « 👤 Connexion du DG » modifie l'e-mail / le téléphone de connexion du DG ; « 📲 Renvoyer les identifiants » envoie un nouveau mot de passe provisoire par WhatsApp (SMS en repli) et par e-mail.
- **Traçabilité** : chaque demande de code, échec, blocage, réinitialisation, changement d'identifiant et envoi de mot de passe provisoire est noté (qui, pour quel compte, canal, résultat, adresse IP) dans la collection `tlb_journal_identifiants`, **sans aucun code ni mot de passe**.

### Abonnements (modèle SaaS)
- Chaque nouvelle boutique a **14 jours d'essai complet** à partir de sa création (les boutiques plus anciennes aussi, comptés depuis leur création).
- Ensuite, **abonnement** selon une formule : 1 mois (5 000 FCFA), 3 mois (14 000), 6 mois (27 000) ou 1 an (50 000). Les durées et les prix se modifient dans `/plateforme/abonnements` > Formules.
- Un paiement repousse l'échéance du nombre de mois de la formule, à partir de l'échéance en cours : aucun jour perdu, même payé pendant l'essai. Une boutique suspendue pour impayé repart du jour du paiement.
- Deux façons de payer :
  - le DG paie en ligne par Mobile Money (PawaPay) depuis sa page **Abonnement adLyn** ; l'argent arrive sur le compte de la plateforme ;
  - l'administrateur enregistre un paiement reçu autrement (espèces, transfert, virement).
- **Retards** : la liste montre les boutiques dont l'échéance est dépassée, avec les jours de retard et le montant attendu. L'administrateur coche celles dont il **suspend l'accès** (back-office et vitrine). Il n'y a **aucun blocage automatique**.
- Pendant la suspension, le DG garde l'accès à sa page Abonnement : son paiement **rend l'accès automatiquement**. Une suspension manuelle (autre motif) n'est levée que par l'administrateur.
- **Rappels** chaque jour à 9h, 3 jours avant l'échéance puis chaque jour tant qu'elle n'est pas réglée :
  - WhatsApp (même compte que beauthentik), avec le SMS en repli si WhatsApp échoue ;
  - e-mail au DG.
  Un journal des envois est disponible.

### Service SMS des boutiques (volet communication, facturé à part)
- **Configuration** par l'administrateur, une fois par boutique (`/plateforme/abonnements` > Service SMS) :
  - nom d'expéditeur OVH déclaré pour elle (3 à 11 lettres ou chiffres) ;
  - service OVH dédié (facultatif, sinon celui de la plateforme) ;
  - prix d'un SMS ;
  - SMS automatiques oui ou non.
  La boutique ne peut pas modifier ces réglages.
- **Envois** :
  - SMS automatiques aux clients (commande reçue ou changée, paiement, dépôt et suivi de réparation), en plus des e-mails ;
  - SMS écrits par le personnel (page **SMS** du back-office).
  Tous les envois sont listés **par contact**, côté boutique et côté administrateur.
- **Facturation** : une facture par boutique et par mois (SMS envoyés × prix ; un long message compte plusieurs SMS ; les échecs ne sont pas facturés).
  - Elle est créée automatiquement le 1er du mois, ou à la demande pour une période.
  - Elle se paie en ligne par le DG (page Abonnement) ou s'enregistre à la main par l'administrateur.
- **Retard** : liste des factures SMS impayées après leur échéance (10 jours). L'administrateur choisit les boutiques dont il **suspend le seul service SMS** ; le reste de la boutique continue. Le paiement des factures en retard rétablit le service automatiquement.

### Reversements PawaPay aux boutiques
- Les paiements Mobile Money des clients arrivent sur le compte PawaPay de la plateforme.
- L'administrateur (`/plateforme/reversements`) voit pour chaque boutique l'encaissé, le reversé, les frais retenus et ce qui reste à reverser. Il enregistre chaque reversement : paiements couverts, frais, mode, référence. Il peut annuler un reversement saisi par erreur.
- Chaque boutique (DG et comptable, page **Reversements PawaPay**) ne voit que ses propres paiements, avec pour chacun « reversé » ou « en attente », et ses reversements.

### Sécurité des connexions (par boutique)
- Dans **Paramètres > Sécurité & connexions**, le DG gère les adresses IP (avec `*`, ex. `196.28.*`) et les appareils à **autoriser** (liste blanche) ou à **interdire**.
  - L'interdiction l'emporte toujours.
  - Dès que la liste blanche contient une règle, seuls les adresses et appareils de la liste passent ; `*` y autorise tout le monde.
- Les règles s'appliquent à la connexion et à chaque action : une interdiction coupe aussi une session déjà ouverte. Le DG ne peut pas créer une règle qui le bloquerait lui-même. L'administrateur de la plateforme n'est jamais bloqué.
- Chaque tentative de connexion (réussie, mauvais mot de passe, refusée) est tracée dans le journal de la boutique et dans le journal du serveur (logs Render) : compte, adresse IP, appareil. Depuis chaque ligne, le DG autorise ou interdit cette adresse ou cet appareil pour l'avenir.
- Un appareil est reconnu par un identifiant posé dans le navigateur à la première connexion. Il est visible dans le journal.

### Boutiques de démonstration
- Une boutique de démonstration est visible de tous sur le portail, comme une vraie. Seul le drapeau interne `test` (en base) la distingue. Il n'apparaît que dans l'administration du super-administrateur (repère « 🧪 Démo »), jamais au public ni au personnel de la boutique.
- Chez elle :
  - pas de paiement Mobile Money en ligne (seulement le paiement à la livraison), pour qu'un vrai visiteur ne paie jamais une boutique fictive ;
  - aucun e-mail, SMS ni WhatsApp ;
  - ni sauvegarde Drive ni relance d'abonnement.
- `backend/outils/creer_boutiques_internes.py` crée une vingtaine de boutiques réalistes (Burkina Faso et pays voisins, catalogue aux prix du marché, clients, réparations). Il peut être relancé sans doublon.

### Maintenance des équipements confiés
- Matériel confié pour diagnostic et réparation (ordinateur, imprimante, onduleur…), distinct du SAV des téléphones. Chaque dépôt est une **fiche** numérotée `MNT-<CODE>-<AAAA>-0001` : client, type de matériel (liste extensible), état à la réception (mauvais, moyen, bon), motif, diagnostic, pièces à remplacer, dates d'entrée et de sortie, statut (reçu → rendu), équipe, prix du diagnostic (`MAINTENANCE_PRIX_DIAGNOSTIC`, 10 000 FCFA par défaut, modifiable sur chaque fiche).
- **Photos** annotées dans le navigateur (flèches, cercles, texte, flou), bon de dépôt / de restitution imprimable.
- **Envoi par WhatsApp** : modèle Meta approuvé (`WHATSAPP_MAINTENANCE_TEMPLATE`, et `WHATSAPP_MAINTENANCE_TEMPLATE_IMAGE` avec la 1re photo en en-tête), ou message libre + photos si le client a écrit au numéro adLyn dans les 24 h.
- **Lien de paiement Mobile Money** (PawaPay) et **Facturer**.
- Deux espaces :
  - **plateforme** (`/plateforme/maintenance-equipements`) : le client est une boutique ; son téléphone est celui qui reçoit les messages d'adLyn (DG). Paiement encaissé pour adLyn ; facture adLyn imprimable (`FMT-AAAA-00001`) ;
  - **boutique** (`/gestion/maintenance-equipements`) : option **activée boutique par boutique** par l'administrateur (fenêtre « Barre latérale & Caisse Aizenta »). Clients : fichier Clients ou saisie libre. Paiement réservé aux boutiques au dossier KYC validé, reversé comme les commandes ; facture ou proforma dans « Factures & proformas ».

### Options de la barre latérale (activées par boutique)
- « Tableau de bord » et « Caisse Aizenta » sont **toujours** actives. Toutes les autres entrées du menu sont **désactivées à la création** d'une boutique (création par l'administrateur, webhook, parrainage).
- L'administrateur les active dans `/plateforme` → carte de la boutique → **« 🧭 Barre latérale & Caisse Aizenta »** (un interrupteur par option, « Tout activer / Tout désactiver », journal des changements : qui, quand, avant / après).
- Une option désactivée disparaît du menu **et** ses routes d'API répondent 403 « Option non activée pour cette boutique » (adresse tapée à la main : retour au tableau de bord). Les droits par rôle s'appliquent en plus. Aucune donnée n'est supprimée.
- **Boutiques existantes** (créées avant cette fonction, sans le champ `options_sidebar`) : **tout reste activé** tant que l'administrateur n'a pas enregistré de réglage.
- Code : `backend/options_sidebar.py` (liste des options et table des routes protégées), `frontend/src/lib/options.js`.

### Caisse Aizenta (données envoyées par Loois)
- Loois lit les tables `RèglementCaisse` et `TypePaiementCaisse` du logiciel Aizenta et les envoie au webhook `POST /api/webhooks/caisse-aizenta` (jeton propre à chaque boutique, généré par l'administrateur, stocké haché).
- Écran `/gestion/caisse-aizenta` (DG, comptable, secrétariat) : situation par période (aujourd'hui, hier, 7 jours, mois, intervalle), totaux, ventilations par type / mode de paiement / caissier, arrêts de caisse, liste filtrable, export CSV, alerte si aucune réception depuis 24 h.
- Contrat JSON complet et mise en service : **[docs/caisse-aizenta.md](docs/caisse-aizenta.md)**.

### Pour l'administrateur de la plateforme (`/plateforme`)
- Création des boutiques avec pays, localisation, DG, IFU, CNSS, RCCM et le compte du DG. Chaque nouvelle boutique reçoit **tout le catalogue public**.
- **Création automatique par webhook** (voir plus bas) : les boutiques créées ainsi attendent la **validation** de l'administrateur avant d'apparaître sur le portail. Journal des appels (bouton « 🔗 Webhook ») et renvoi des identifiants au DG.
- Vérification des dossiers **KYC**, suspension des boutiques, mise en avant dans le carrousel.
- **Référentiel mondial des appareils** (`/plateforme/referentiel`) :
  - liste officielle Google Play de tous les appareils Android certifiés (environ 40 000 modèles de 3 800 marques, avec leurs codes modèle), plus les iPhone ;
  - bouton de mise à jour, qui télécharge la dernière liste Google ;
  - pour chaque appareil, « Créer la fiche » (avec ou sans assistant de recherche) crée sa fiche détaillée dans le catalogue public ;
  - les boutiques y cherchent n'importe quel appareil, par nom ou par code modèle.
- **Catalogue public commun** (`/plateforme/catalogue`) :
  - téléphones, accessoires et pièces détachées liées aux téléphones compatibles ;
  - **assistant de recherche** qui lit les sites des fabricants (API Claude + recherche web) ;
  - **publication automatique chaque soir à 23h** ; les ajouts arrivent dans chaque boutique avec le badge « Nouveau ».
- **Sauvegardes** (`/plateforme/sauvegardes`) :
  - archive **chiffrée** de chaque boutique chaque nuit à **00h**, envoyée sur **Google Drive** (un dossier par boutique) ;
  - téléchargement et **restauration** ;
  - **rapport de la nuit** envoyé par e-mail (sauvegardes + catalogue, succès et échecs).

## Démarrer en local (Windows)

Prérequis : Python 3.11, Node.js 20+.

```bash
# 1) API
cd backend
python -m venv .venv
.venv\Scripts\activate            # Linux/Mac : source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env            # Linux/Mac : cp .env.example .env
uvicorn server:app --reload       # http://localhost:8000/docs
```

Le fichier `.env` d'exemple utilise `MONGO_URL=mongomock://`, une base **en mémoire**, sans installation, vidée à chaque arrêt. Ajoutez `DEMO_AU_DEMARRAGE=true` pour créer la boutique de démonstration : `/b/demo-telecom`, DG `demo@demo-telecom.bf` / `demo-2026!`. Pour garder les données, mettez l'adresse de votre cluster MongoDB Atlas dans `MONGO_URL`.

```bash
# 2) Site (dans un second terminal)
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

Pages utiles :
- `/` : accueil public ;
- `/connexion` : personnel des boutiques et administrateur ;
- `/gestion` : back-office ;
- `/plateforme` : administration de la plateforme.

**Tests automatiques** (76 tests) : `cd backend && python -m pytest tests -q`. Ils couvrent notamment le cloisonnement entre boutiques, les droits des rôles, les factures, le stock, le catalogue public, le KYC, les sauvegardes, l'historique des paiements, le webhook, la connexion, les abonnements, le service SMS, les reversements et les règles d'accès.

## Déployer sur Render

1. Sur Render : **New > Blueprint**, choisir ce dépôt. `render.yaml` crée les deux services.
2. Renseigner les variables marquées « sync: false » (tableau de bord Render) :
   - `MONGO_URL` (Atlas) ;
   - `FRONTEND_ORIGIN` (adresse du site) ;
   - `VITE_API_BASE_URL` (adresse de l'API + `/api`) ;
   - `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD` ;
   - R2 (`R2_ACCOUNT_ID`, clés, `R2_PUBLIC_BASE_URL`) : créer deux buckets, `telecom-boutique-medias` (public) et `telecom-boutique-kyc` (**privé**) ;
   - PawaPay (mêmes jetons que beauthentik) ;
   - `ANTHROPIC_API_KEY` (assistant de recherche) ;
   - **sauvegardes** : `SAUVEGARDE_CLE`, Google Drive, SMTP de la plateforme (détails ci-dessous) ;
   - **webhook** : `WEBHOOK_BOUTIQUES_SECRET` ; **SMS** : `ORANGE_SMS_*` (et `OVH_SMS_*` en repli), mêmes comptes que beauthentik ;
   - **WhatsApp** : `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` (beauthentik) et `WHATSAPP_RAPPEL_TEMPLATE`. Faites approuver par Meta un modèle « Utility » en français à 3 variables, par exemple : « Bonjour, l'abonnement adLyn de {{1}} {{2}}. Montant à régler : {{3}}. Payez depuis votre espace boutique, page Abonnement. ». Sans modèle approuvé, WhatsApp n'accepte le message que si le DG a écrit au numéro dans les dernières 24 h : le SMS prend alors le relais.
   - **WhatsApp, codes et mots de passe provisoires** : `WHATSAPP_CODE_TEMPLATE` = nom d'un modèle de catégorie **Authentication** (langue : français), par exemple `adlyn_code_connexion`. Meta impose son texte (« *{{1}}* est votre code de vérification. ») : cochez la recommandation de sécurité, le pied « Ce code expire dans 10 minutes » et le bouton « Copier le code ». Facultatif : `WHATSAPP_IDENTIFIANTS_TEMPLATE`, modèle **Utility** à 4 variables envoyé avant un mot de passe provisoire, par exemple `adlyn_identifiants` : « Bonjour {{1}}, voici vos accès à l'espace de la boutique {{2}} sur adLyn : ID boutique {{3}}, identifiant {{4}}. Votre mot de passe provisoire suit dans un message séparé ; changez-le dès votre première connexion. ». Sans ces modèles, un code n'arrive par WhatsApp que si la personne a écrit au numéro adLyn dans les dernières 24 h : le SMS prend alors le relais.
3. Noms de domaine : décommenter les blocs `domains` de `render.yaml` et créer les CNAME chez Cloudflare, comme pour beauthentik. **Important pour la connexion** : donnez au site et à l'API deux sous-domaines du **même** domaine (ex. `adlyn.com` et `api.adlyn.com`). Sinon, avec les deux adresses `onrender.com`, Safari (iPhone, Mac) refuse le cookie de session et le personnel devrait se reconnecter à chaque ouverture.

### Version et lot (à mettre à jour à CHAQUE déploiement)

La mention « Version X · Lot N · commit » est affichée sur la page de connexion et dans tous les espaces connectés (barre latérale ou pied de page de l'espace boutique, en-tête de l'espace plateforme, Mon compte). Source unique : `frontend/src/version.js`.

- `VERSION` : ajouter 1 à chaque déploiement ;
- `LOT` : numéro de la Pull Request GitHub fusionnée pour ce déploiement ;
- le commit (7 caractères) est calculé automatiquement à la compilation (`RENDER_GIT_COMMIT` sur Render, sinon git) : rien à saisir.

Ce fichier est dans `frontend/` exprès : le site (rootDir `frontend`) n'est reconstruit par Render que si un fichier de ce dossier change ; en modifiant `version.js` à chaque déploiement, l'affichage est toujours à jour, même quand seul le serveur a changé.

### Webhook de création des boutiques
Un système externe (formulaire d'inscription, CRM…) peut créer une boutique :

```
POST https://<api>/api/webhooks/boutiques
X-Adlyn-Horodatage: <secondes Unix>
X-Adlyn-Signature: sha256=<HMAC-SHA256(WEBHOOK_BOUTIQUES_SECRET, "<horodatage>." + corps JSON brut)>

{"evenement_id": "insc-2026-000123", "nom": "Boutique Étoile", "pays": "Burkina Faso", "ville": "Ouagadougou",
 "telephone": "+22625000000", "dg_nom": "Awa Ouédraogo", "dg_email": "awa@exemple.bf", "dg_telephone": "+22670000000"}
```

Champs facultatifs : `adresse`, `email`, `latitude`, `longitude`, `ifu`, `cnss`, `rccm`, `reference_externe`.

Réponses :
- `201 {"resultat": "creee", "code_boutique": "K7M2QD", "statut": "EN_ATTENTE_VALIDATION"}` ;
- `200 {"resultat": "ignoree"}` : la boutique existe déjà (même nom, même `reference_externe` ou DG déjà inscrit) ;
- `401` pour une signature ou un horodatage invalide, `409` pour un événement rejoué, `422` pour une demande invraisemblable, `429` pour un quota atteint ou une adresse IP bloquée.

Le **mot de passe provisoire du DG n'est jamais dans la réponse** : la plateforme envoie l'ID boutique et ce mot de passe au DG lui-même : par WhatsApp (SMS si WhatsApp ne passe pas) et par e-mail. La réponse indique `identifiants_envoyes: {"whatsapp", "sms", "email"}` (`NON_ENVOYE` pour le SMS quand WhatsApp a suffi).

Protections contre les inscriptions « pour s'amuser » :
1. signature HMAC (secret partagé) ;
2. horodatage à ± 5 minutes et `evenement_id` à usage unique (pas de rejeu) ;
3. contrôles de vraisemblance : nom réaliste, e-mail non jetable, téléphone valide, pas de lien ;
4. quota de créations par 24 h (`WEBHOOK_QUOTA_JOUR`) et blocage d'une adresse IP après 10 refus en une heure ;
5. **boutique invisible du public jusqu'à la validation** par l'administrateur, prévenu par e-mail ;
6. journal de tous les appels.

Pour essayer : `WEBHOOK_BOUTIQUES_SECRET=… python backend/outils/envoyer_webhook.py https://<api> demande.json`.

### Sauvegardes : mise en route
1. **Clé de chiffrement** : générez-la une fois avec `python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`, puis mettez-la dans `SAUVEGARDE_CLE`. **Gardez-en une copie hors de Render** (gestionnaire de mots de passe) : sans elle, aucune sauvegarde ne peut être restaurée.
2. **Google Drive** :
   - dans Google Cloud Console, activez l'API Google Drive et créez des identifiants OAuth « Application de bureau » ;
   - sur votre PC : `pip install google-auth-oauthlib`, puis `python backend/outils/obtenir_jeton_gdrive.py --client-id … --client-secret …` ;
   - reportez les 3 valeurs affichées dans Render.
   L'autorisation est limitée aux fichiers créés par la plateforme (portée `drive.file`) : elle ne voit pas le reste du Drive.
3. **Rapport par e-mail** : `RAPPORT_EMAIL` est déjà réglé sur jfrancois.ouoba@gmail.com. Renseignez `PLATEFORME_SMTP_*` (par exemple Gmail : `smtp.gmail.com`, port 587, votre adresse et un « mot de passe d'application »).

Format d'une sauvegarde (`.tlb.gz.enc`) : données JSON de la boutique → compression gzip → chiffrement AES-256-GCM. Toute modification du fichier est détectée à l'ouverture. Les photos et documents restent dans R2 : l'archive contient leurs adresses.

## Sécurité et règles de conception
- **Multi-tenant** :
  - la boutique d'un utilisateur est lue dans son compte côté serveur, jamais dans un paramètre du navigateur (règle de `TECHNICAL_RULES.md` du dépôt `ShuyahBF/Claude`) ;
  - toutes les requêtes passent par `TenantDB` (`backend/db.py`), qui ajoute automatiquement le filtre `boutique_id` ;
  - seul le super-administrateur choisit une boutique (en-tête `X-Boutique-Id`).
- **Montants** : toujours recalculés par le serveur (prix relus en base, jamais repris du navigateur).
- **Opérations atomiques** : numérotation, stock (« impossible de vendre deux fois le dernier téléphone »), validation de facture « tout ou rien ».
- **PawaPay** :
  - le statut d'un paiement est toujours revérifié auprès de PawaPay, et le montant contrôlé ;
  - comme le compte est partagé, une boucle vérifie chaque minute les paiements en attente ;
  - les fonds de toutes les boutiques arrivent sur le compte PawaPay de la plateforme, à reverser aux boutiques.
- **Sessions** : jeton signé dans un cookie HttpOnly ; toute écriture doit porter l'en-tête `X-Adlyn`, qu'un site tiers ne peut pas ajouter (protection CSRF). Chaque changement de mot de passe révoque les sessions ouvertes ailleurs.
- **KYC** : fichiers dans un bucket privé, accessibles seulement par le DG de la boutique et l'administrateur, par lien temporaire de 5 minutes.

## Organisation du code
```
backend/
  server.py              démarrage de l'API et des tâches automatiques
  config.py              toutes les variables d'environnement, commentées
  db.py                  MongoDB + cloisonnement automatique par boutique (TenantDB)
  auth.py                connexion, rôles et table des PERMISSIONS
  identifiants.py        e-mail/téléphone de connexion, codes (WhatsApp > SMS > e-mail), journal
  services.py            numérotation, stock, calcul des lignes de facture
  catalogue_public.py    catalogue commun, publication à 23h, assistant de recherche
  referentiel.py         référentiel mondial des appareils (Google Play + iPhone)
  kyc.py                 dossier d'identification des boutiques (fichiers privés)
  sauvegarde.py          export chiffré / restauration d'une boutique
  gdrive.py              envoi sur Google Drive
  taches_nocturnes.py    sauvegardes de 00h + rapport par e-mail
  journal_paiements.py   historique des paiements
  messagerie.py          e-mails des boutiques (modèles, envoi, journal)
  storage.py             fichiers publics et privés (R2 ou disque local)
  routes/                un fichier par domaine (documents, stock, maintenance, public…)
  tests/                 tests automatiques (base en mémoire)
  outils/                obtenir_jeton_gdrive.py
frontend/src/
  App.jsx                toutes les adresses du site
  components/            mises en page et composants partagés
  context/AuthContext    session et droits (peut(user, "facturation"))
  lib/                   API, formats, panier, statuts
  pages/Connexion, MotDePasseOublie, MonCompte, ChangerMotDePasse   connexion et compte
  pages/public/          portail public
  pages/gestion/         back-office des boutiques
  pages/plateforme/      administration de la plateforme
```
