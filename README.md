# TelecomBoutique — plateforme SaaS multi-boutiques de téléphonie

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

### Pour l'administrateur de la plateforme (`/plateforme`)
- Création des boutiques avec pays, localisation, DG, IFU, CNSS, RCCM et le compte du DG. Chaque nouvelle boutique reçoit **tout le catalogue public**.
- Vérification des dossiers **KYC**, suspension des boutiques, mise en avant dans le carrousel.
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

**Tests automatiques** (38 tests) : `cd backend && python -m pytest tests -q`. Ils couvrent notamment le cloisonnement entre boutiques, les droits des rôles, les factures, le stock, le catalogue public, le KYC, les sauvegardes et l'historique des paiements.

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
   - **sauvegardes** : `SAUVEGARDE_CLE`, Google Drive, SMTP de la plateforme (détails ci-dessous).
3. Noms de domaine : décommenter les blocs `domains` de `render.yaml` et créer les CNAME chez Cloudflare, comme pour beauthentik.

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
- **KYC** : fichiers dans un bucket privé, accessibles seulement par le DG de la boutique et l'administrateur, par lien temporaire de 5 minutes.

## Organisation du code
```
backend/
  server.py              démarrage de l'API et des tâches automatiques
  config.py              toutes les variables d'environnement, commentées
  db.py                  MongoDB + cloisonnement automatique par boutique (TenantDB)
  auth.py                connexion, rôles et table des PERMISSIONS
  services.py            numérotation, stock, calcul des lignes de facture
  catalogue_public.py    catalogue commun, publication à 23h, assistant de recherche
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
  pages/public/          portail public
  pages/gestion/         back-office des boutiques
  pages/plateforme/      administration de la plateforme
```
