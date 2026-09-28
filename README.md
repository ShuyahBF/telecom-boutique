# TelecomPro — plateforme de gestion d'une entreprise télécom

Site web complet en **Python / Django** pour une boutique de téléphonie :

| Module | Ce qu'il fait |
|---|---|
| **Catalogue** | Téléphones, accessoires, pièces détachées, services ; catégories, marques, photos, caractéristiques |
| **Stock** | Journal des entrées/sorties ; bons de réception fournisseur multi-lignes ; alertes de stock bas |
| **Ventes** | Factures et proformas **multi-lignes** (remise et TVA par ligne), conversion proforma → facture, règlements partiels (espèces, Orange Money, Moov Money...), montant en toutes lettres, impression A4 / PDF |
| **Commandes en ligne** | Panier et commande depuis le portail, suivi par n° de commande, génération de la facture en un clic |
| **Maintenance (SAV)** | Dossier de réparation numéroté automatiquement (`MNT-2026-00001`) + code de suivi, bon de dépôt imprimable, historique des statuts, pièces utilisées (déstockées automatiquement), facture de réparation |
| **Clients / Fournisseurs** | Fiches tiers, retrouvées par téléphone |
| **Centre de messagerie** | Demandes de conseil des clients (fil de discussion), réponses de l'équipe, e-mails automatiques. **Paramétrable par l'admin** : serveur SMTP, expéditeur, textes des messages, activation par type, journal des envois |
| **Portail public** | Vitrine, recherche/filtres, panier, commande, suivi commande, suivi réparation, demande de conseil |
| **Tableau de bord** | CA du mois, factures en brouillon, commandes à traiter, réparations en cours/en retard, stock en alerte |

## Démarrage rapide (Windows / Visual Studio 2026 ou terminal)

```bash
cd telecom-platform
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/Mac : source .venv/bin/activate)
pip install -r requirements.txt

python manage.py migrate           # crée la base (fichier db.sqlite3)
python manage.py createsuperuser   # crée votre compte administrateur
python manage.py donnees_demo      # (facultatif) produits, clients et un dossier SAV d'exemple
python manage.py runserver
```

Puis ouvrir :

- **http://127.0.0.1:8000/** : portail public (clients)
- **http://127.0.0.1:8000/gestion/** : tableau de bord du personnel
- **http://127.0.0.1:8000/admin/** : saisie de toutes les données

> Dans Visual Studio : *Fichier > Ouvrir > Dossier* sur `telecom-platform`, sélectionner l'interpréteur
> Python du dossier `.venv`, puis lancer `manage.py` avec l'argument `runserver`.

Tests automatiques (24 tests des règles métier) : `python manage.py test`

## Premiers réglages (dans /admin/)

1. **Paramètres généraux › Fiche entreprise** : raison sociale, adresse, IFU, RCCM, logo, devise, TVA par défaut
   (mettre 0 si l'entreprise n'est pas assujettie), mentions en pied de facture, validité des proformas.
2. **Centre de messagerie › Paramètres de messagerie** : cocher « Envoi d'e-mails activé », renseigner le serveur SMTP
   (ex. Gmail : `smtp.gmail.com`, port 587, STARTTLS, mot de passe d'application), l'adresse publique du site et
   l'e-mail de l'équipe. Le champ « Envoyer un e-mail de test » vérifie les réglages à l'enregistrement.
3. **Centre de messagerie › Modèles de messages** : adapter les textes. Variables disponibles : `{{ client.nom }}`,
   `{{ commande.numero }}`, `{{ dossier.numero }}`, `{{ dossier.get_statut_display }}`, `{{ dossier.code_suivi }}`,
   `{{ entreprise.nom }}`, `{{ lien }}` (lien de suivi)...
4. **Utilisateurs** : créer les comptes vendeurs / techniciens (case « Statut équipe ») et leur donner les droits
   par module (groupes « Vendeurs », « Techniciens »...).

## Règles de gestion importantes

- **Numérotation automatique** par préfixe et par année, sans doublon même avec plusieurs postes :
  `PRO-` proforma, `FAC-` facture, `CMD-` commande en ligne, `MNT-` dossier SAV, `BE-` bon d'entrée.
- **Facture** : reste en *brouillon* (modifiable, sans numéro) jusqu'au bouton **« Valider la facture »**, qui
  contrôle le stock, attribue le numéro définitif (numérotation continue) et déstocke. Une facture validée ne se
  modifie ni ne se supprime : on l'**annule** (le stock est réintégré).
- **Proforma** : numérotée dès sa création, sans effet sur le stock ; bouton **« Convertir en facture »**.
- **Stock** : jamais saisi à la main. Il évolue uniquement par des mouvements (réception validée, facture validée,
  pièce utilisée en SAV, casse, inventaire...). Pour corriger, saisir un mouvement inverse.
- **Suivi client sans compte** : commande = n° + téléphone ; réparation = n° de dossier + téléphone *ou* code de
  suivi imprimé sur le bon de dépôt. Le n° seul ne suffit pas (il est prévisible).
- **Paiement en ligne** : non inclus dans cette version — le client paie au retrait/à la livraison. L'intégration
  Orange Money / Moov Money (API marchand) pourra être ajoutée.

## Base de données

Par défaut : **SQLite** (un simple fichier, rien à installer). Pour la production, PostgreSQL est recommandé :

```bash
pip install "psycopg[binary]"
set DATABASE_ENGINE=django.db.backends.postgresql
set DATABASE_NAME=telecompro
set DATABASE_USER=...
set DATABASE_PASSWORD=...
set DATABASE_HOST=localhost
```

**Et HFSQL ?** Django n'a pas de pilote HFSQL, et le fournisseur OLE-DB `PCSoft.HFSQL` n'existe que sous Windows :
le site ne peut donc pas utiliser HFSQL comme base principale. Si des données existent déjà dans une application
WinDev (produits, clients), la bonne approche est un **script d'import/synchronisation** Windows (OLE-DB, comme
`HFSQL_LoginApp/HFSQL_SchemaExplorer`) qui alimente la base du site. MongoDB Atlas n'est pas retenu non plus : les
factures multi-lignes et les mouvements de stock ont besoin de transactions relationnelles, que l'ORM Django
gère nativement avec SQLite/PostgreSQL.

## Production

Variables d'environnement à définir : `DJANGO_SECRET_KEY` (longue chaîne aléatoire), `DJANGO_DEBUG=0`,
`DJANGO_ALLOWED_HOSTS=mondomaine.com`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://mondomaine.com`, puis
`python manage.py collectstatic` et un serveur WSGI (gunicorn, waitress sous Windows) derrière HTTPS.

## Organisation du code

```
telecom-platform/
├── config/        paramètres Django et table des adresses (urls.py)
├── core/          fiche entreprise, compteurs de numérotation, tableau de bord, impressions, montant en lettres
├── tiers/         clients, fournisseurs
├── catalogue/     catégories, marques, produits
├── stock/         mouvements de stock, bons d'entrée
├── ventes/        factures/proformas + lignes + règlements, commandes en ligne
├── maintenance/   dossiers SAV, historique, pièces utilisées
├── messagerie/    paramètres SMTP, modèles de messages, journal, conversations (services.py = envoi)
├── portail/       site public (vues, formulaires, panier en session)
├── templates/     pages HTML (portail/, gestion/, surcharges admin/)
├── static/css/    feuille de style du portail
└── tests/         tests automatiques
```
