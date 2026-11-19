# Règles permanentes du propriétaire (ShuyahBF)

Ces règles s'appliquent à TOUS les sites, projets et applications, existants
(SAWALI, Ster, adLyn, beAuthentik, …) et futurs. Elles font partie de la
méthode de travail par défaut, sans qu'il soit nécessaire de les redemander.

## Livraison et déploiement
- Après chaque mise à jour prête pour Render : fusionner automatiquement,
  puis informer le propriétaire dans le chat ET par e-mail HTML
  (jfrancois.ouoba@gmail.com) : date et heure, identification (dépôt, branche,
  commit, version, lot), périmètre, comment vérifier, à activer, points
  d'attention, reste à faire.
- Commits : auteur ET committer `ShuyahBF <jfrancois.ouoba@gmail.com>`,
  messages et commentaires en français, aucune mention d'IA ni de Co-Authored-By.
- Commentaires clairs sur chaque bloc de code (le propriétaire vient de WinDev).
- Ne jamais commiter, afficher ni envoyer de secret (clés, mots de passe,
  chaînes de connexion) : ils vont uniquement dans les variables
  d'environnement, saisies par le propriétaire.

## Version et lot (règles 1 et 2)
1. À chaque déploiement, le numéro de version ET le numéro de lot sont mis à
   jour (jamais une constante figée qui n'est plus incrémentée).
2. La version est toujours affichée sur les pages de connexion et dans le
   portail (barre latérale, en-tête ou pied de page de toutes les pages
   connectées), au format court « Version X · déployée le JJ/MM/AAAA HH:MM »
   (ex. « Version 12 · déployée le 04/10/2026 21:10 »), sans lot ni commit.
   Les pages d'administration / paramétrage affichent le libellé complet
   « Version X · Lot N · <commit court> · déployée le JJ/MM/AAAA HH:MM ».
   Date/heure au format français court
   (`toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })`),
   fournie de façon fiable (date de démarrage côté serveur ou date de
   compilation injectée au build du frontend).
- Une seule source par plateforme :
  - SAWALI : `backend/lot.py` (LOT, LOT_LIBELLE), exposé par `/api/version` ;
    version = compteur de déploiements `1.N`. Modifier `lot.py` à chaque
    déploiement force aussi le redéploiement du serveur (Render ne redéploie
    un service à `rootDir` que si un fichier de son dossier change).
  - Ster : `frontend/src/version.js` (VERSION +1 à chaque déploiement,
    LOT = numéro de la PR fusionnée).
  - adLyn, beAuthentik : même principe (lot = numéro de la PR fusionnée).
    adLyn : `libelleVersion(detaille)` dans `frontend/src/version.js`, date
    de déploiement = date de compilation (Vite `define`), libellé détaillé
    sur les pages Paramètres (boutique et plateforme).
- Nouveau projet : prévoir dès le départ cette source unique et l'affichage.

## Tableaux (règle 3)
- Règle du 29/10/2026 : les NOMBRES (quantités, montants, pourcentages) sont TOUJOURS alignés à DROITE, en-tête de colonne compris (écran : `text-right tabular-nums` ; PDF reportlab : style de paragraphe `alignment=2` ; WinForms : `DefaultCellStyle.Alignment = MiddleRight`).
- Sur TOUT tableau : ligne survolée = fond bleu clair transparent
  (`rgba(56, 189, 248, 0.16)`) ; ligne sélectionnée = fond orange clair
  (`#f6a35b`) avec police BLEU NUIT (`#0A1E3D`, contraste 7,7:1) — règle modifiée le 28/10/2026 : l'ancienne police blanche n'avait que 2:1
  de contraste (illisible).
- Mise en œuvre globale dans le CSS de chaque plateforme ; une ligne est
  sélectionnée si elle porte `ligne-selectionnee`, `aria-selected="true"`,
  `data-selected="true"`, ou si la case à cocher de sa première cellule est cochée.

## Outils de maintenance et d'analyse (règle 9, 17/10/2026 : « règle ultra importante »)
Le propriétaire vient de WinDev : il ne maîtrise ni Python ni PowerShell et préfère les interfaces graphiques.
- NE JAMAIS lui concevoir d'outil de maintenance ou d'analyse qui demande le moins du monde de manipuler Python, PowerShell ou Visual Studio.
- Privilégier une INTERFACE GRAPHIQUE dans la plateforme : rubrique des Paramètres avec un bouton, puis tableau, graphiques et export CSV.
  Calcul en arrière-plan (règle 7), lecture seule par défaut, accès réservé au bon rôle.
  Modèle : « Audit des collections MongoDB » de SAWALI (lot 225, `backend/routes/audit_collections_mongo.py`).
- Si PowerShell est vraiment inévitable (action sur un poste Windows, sans interface possible) : TOUT dans UN SEUL fichier de commandes
  (.ps1) prêt à l'emploi, commenté bloc par bloc, accompagné d'un mode d'emploi détaillé (où l'enregistrer, comment le lancer,
  ce qu'il affiche, que faire en cas d'erreur). Secrets saisis à l'écran, jamais écrits dans un fichier ni dans le chat.
- Un outil à usage unique (script Python, suite de commandes à enchaîner) n'est PAS une réponse acceptable.

## Listes finies = listes déroulantes (règle 10, 17/10/2026)
- Dès que l'ensemble des valeurs possibles est fini et connu (opérateurs, pays, rôles, statuts, catégories, devises, modes de
  paiement…), le champ est une LISTE DÉROULANTE, jamais une saisie libre ni une grille de grosses cartes.
- Si un nouveau choix doit rester possible, ajouter en fin de liste « Autre… » qui ouvre une saisie libre, seulement dans ce cas.
- Une valeur déjà enregistrée mais absente de la liste reste sélectionnable (jamais de perte de donnée à l'édition).
- Même principe sur toute plateforme, existante ou à venir.

## Fenêtres modales dimensionnées (règle 11, 17/10/2026 : « comme pour beAuthentik et adLyn »)
- Sur PC comme sur mobile, une fenêtre modale n'est jamais exagérément grande : largeur 28 rem au plus (`max-w-md`), 36 rem pour un
  formulaire à plusieurs colonnes (`max-w-xl`), hauteur 85 % de l'écran au plus (`max-h-[85dvh]`) avec défilement DANS la fenêtre.
- Sur mobile : feuille collée en bas ou fenêtre centrée avec marge, jamais plein écran sauf besoin réel (scanner, aperçu).
- Un seul composant de modale par plateforme (ex. `components/Modal.jsx`) porte ces dimensions ; les écrans ne les redéfinissent pas.

## Attentes et chargements
- Toute attente longue (connexion, recherche…) affiche un toast « Patientez… »
  et une jauge circulaire transparente (arc qui tourne), comme sur SAWALI.

## Dépôts GitHub des plateformes (règle permanente du propriétaire, 14/10/2026 : « rends-les permanents quelles que soient les sessions »)
Tous les dépôts sont sous le compte GitHub `ShuyahBF`. Quand une demande nomme une plateforme, utiliser CE tableau sans
le redemander. Dépôt absent de la session : `list_repos` (requête « ShuyahBF »), puis `add_repo` (accès « push » pour
modifier), cloner UNE fois (`git clone --depth 1`, délai généreux), puis `register_repo_root`.

| Plateforme | Dépôt | Branche de base / déploiement |
|---|---|---|
| SAWALI | `ShuyahBF/Emergent` | PR vers `render-production` (Render y déploie) |
| ZandGo | `ShuyahBF/zandgo` | `main` |
| Portail e-Kol (élèves et parents) | `ShuyahBF/ekol-portail` | `main` |
| adLyn | `ShuyahBF/telecom-boutique` | `main` |
| beAuthentik | `ShuyahBF/site-meetafrican` | `main` |
| ALBARKA | `ShuyahBF/albarka-portal` | `main` |
| Ster (= DentalCare, confirmé par le propriétaire le 14/10/2026) | `ShuyahBF/dentalcare` | `main` |
| Loois (logiciel Windows) et sa mise à jour | `ShuyahBF/Loois`, `ShuyahBF/Loois-MAJ` | `main` |
| Aizenta (analyse qualité des stocks) | `ShuyahBF/Aizenta-Analyse-Qualit-Gestion-Stocks` | voir ses règles |
| BF Mobility (VTC) | `ShuyahBF/sawali-bfmobility` | `main` |

Autres dépôts utiles : `ShuyahBF/Claude` (règles techniques, `TECHNICAL_RULES.md`), `ShuyahBF/reglesmetier_claude` (règles métier).
Dépôt refusé par le contrôle d'accès de la session (ex. `shuyah-mirror`) : ne pas insister, le dire au propriétaire.

## Chargement des pages et gros calculs (règle 7, 15/10/2026 : « C'est une RÈGLE ! »)
Constat e-Kol (lots 33 à 36) : le tableau de bord mettait 37 s en moyenne (jusqu'à 87 s) ; après correction, moins de 1 s.
Cette méthode s'applique à TOUTES les plateformes et à tout projet à venir, dès la première version.
- **Mesurer d'abord** : chaque appel au serveur note sa durée (journal des accès, route « Appels les plus lents » : moyenne,
  5 derniers, dernier, maximum). On corrige la route réellement lente, jamais au hasard. Tout nouveau projet prévoit cette mesure.
- **Jamais d'appel à un service externe lent ou limité DANS la requête d'une page** (géolocalisation d'IP, SMS, WhatsApp, API
  tierce, envoi d'e-mail…) : il part en ARRIÈRE-PLAN (`asyncio.create_task`, tâche planifiée), la page répond tout de suite avec
  la valeur connue ou « en cours d'identification », et le résultat est gardé en cache pour l'affichage suivant.
- **Jamais de boucle N+1** (une lecture de base PAR élève / client / ligne) : lire EN BLOC (une requête par collection, ou une
  agrégation) puis regrouper en mémoire.
- **Gros calculs** (statistiques, totaux, situations, tableaux de bord) : lectures indépendantes lancées EN PARALLÈLE
  (`asyncio.gather`) ; calcul lourd (> 1 s) = cache court (ex. 60 s) ou pré-calcul planifié, jamais refait à chaque clic.
- **Authentification et droits** : lire compte et droits en même temps, pas l'un après l'autre.
- **Index** sur tout filtre fréquent (école/site, type, date) : jamais de parcours complet d'une collection dans une requête de page.
- **Objectif** : toute route d'affichage répond en moins de 1 s côté serveur. Au-delà, on corrige AVANT de livrer ; un appel
  externe en arrière-plan reçoit un test qui prouve que la requête n'attend pas.
- **Écran** : afficher d'abord ce qui est prêt ; une section lente ne doit pas bloquer le reste de la page (chargement séparé).

## Outils de la session et comptes rendus par e-mail (règle 12, 17/10/2026 : « ajoute cette règle partout »)
- **Outils différés** : dans une session, les outils des connecteurs (Gmail, Google Drive, Agenda, Render, GitHub…) apparaissent par leur NOM
  seulement ; ils ne sont utilisables qu'après les avoir chargés avec ToolSearch. AVANT de dire qu'un outil manque, le CHERCHER avec ToolSearch
  (ex. « gmail send message », « google drive create file »). Ne jamais conclure « je n'ai pas l'outil » sans cette recherche.
- **Compte rendu par e-mail** : après chaque livraison, envoyer l'e-mail HTML à jfrancois.ouoba@gmail.com avec l'outil Gmail
  (`mcp__Gmail__send_message`, champ `htmlBody`) : date et heure, identification (dépôt, lot, commit), périmètre, comment vérifier, à activer,
  points d'attention, reste à faire. Ce n'est pas un envoi « à un tiers » : le propriétaire l'a demandé de façon permanente (règle « Livraison et déploiement »).
- **Google Drive** : disponible pour déposer ou lire des documents si le propriétaire le demande ; jamais de secret dans un document.

## Exemples d'identification dans les formulaires (règle 13, 06/11/2026)
- Dans TOUT formulaire où la personne s'identifie (nom, e-mail), les exemples affichés sont LOCAUX : nom « BADINI Awa » (NOM puis prénom) et
  e-mail Gmail « awa.badini@gmail.com ». Jamais « Jean Dupont », « Prénom Nom » ni « @entreprise.fr / @exemple.com ».
- Une seule source par plateforme : SAWALI = constantes `EXEMPLE_NOM` / `EXEMPLE_EMAIL` dans `frontend/src/lib/exemplesIdentite.js`, importées par
  chaque formulaire ; ailleurs, créer le même fichier (ou l'équivalent côté application : texte d'indication des champs, WinForms comprises).


## Pictogramme œil sur toute saisie secrète (règle 22, 16/11/2026 : « pour toute saisie d'un mot de passe, pin ou passphrase mettre un pictogramme œil pour afficher ou masquer. Applique cela à tous nos projets, web comme Android »)
- **Toute saisie d'un mot de passe, d'un code PIN, d'une phrase secrète, d'un jeton ou d'une clé secrète** (connexion, création, confirmation, changement, ouverture d'un coffre, fenêtre de sécurité d'un paiement, paramètres…) porte un **pictogramme œil** : œil ouvert = saisie masquée (un clic l'affiche), œil barré / singe = saisie visible (un clic la masque). **Masquée par défaut** à chaque ouverture.
- Le pictogramme est **dans le champ** (à droite), avec une description d'accessibilité (« Afficher la saisie » / « Masquer la saisie ») et une zone tactile d'au moins 44 px.
- **Un seul composant par plateforme**, utilisé partout (jamais un `<input type="password">` nu) : web = `ChampMotDePasse` / `MotDePasse` / `PasswordInput` (ou le champ de base de l'interface qui l'intègre quand `type="password"`) ; Android Compose = champ avec `trailingIcon` (`Visibility` / `VisibilityOff`) ; Android à vues = `FrameLayout` + œil ; WinForms = case ou bouton œil qui bascule `UseSystemPasswordChar`.
- Un nouvel écran, un nouveau projet : le champ secret reçoit l'œil dès la première version. Exception : la saisie d'un code à usage unique (code reçu par e-mail ou SMS, code de l'application d'authentification), qui n'est pas un secret durable.

## Tableaux de plus de 30 lignes : barre de défilement (règle 24, 18/11/2026 : « C'est une règle à considérer partout sur toutes les plateformes »)
- Tout tableau qui présente PLUS DE 30 LIGNES défile dans son cadre (hauteur = 30 lignes + l'en-tête) au lieu d'allonger la page ; l'en-tête reste visible en haut pendant le défilement ;
  à l'impression, toutes les lignes sortent. Exception possible : `<table data-sans-defilement>`.
- Mise en œuvre ici : module global `frontend/src/lib/defilementTableaux.js` installé au démarrage du site (règles CSS dans `index.css`) : rien à ajouter tableau par tableau.

## Compte rendu par e-mail AUTOMATIQUE après toute livraison (règle du propriétaire, 19/11/2026 : « L'envoi de l'e-mail doit être automatique »)
- L'e-mail HTML à jfrancois.ouoba@gmail.com (outil Gmail, voir règle 12) part TOUT SEUL à la fin de CHAQUE livraison, sans que le
  propriétaire ait à le demander ni à le rappeler, et sans demander confirmation avant l'envoi.
- « Livraison » = tout ce qui atteint le propriétaire ou les utilisateurs, même sans fusion ni déploiement Render : dépôt d'un APK ou d'une
  nouvelle version dans ShuyahStore, publication d'une version, correction, changement de libellé, simple règle ajoutée au CLAUDE.md, fichier
  envoyé au propriétaire. Aucune exception de taille.
- Ne pas conclure « la règle ne s'applique pas, rien n'a été déployé sur Render » : en cas de doute, envoyer l'e-mail.
- Contenu : date et heure, identification (dépôt, branche, commit, version, lot), périmètre, comment vérifier, à activer, points
  d'attention, reste à faire. Jamais de secret (clé, mot de passe, chaîne de connexion) dans l'e-mail.
- Charger l'outil Gmail avec ToolSearch AVANT de dire qu'il manque ; s'il est vraiment indisponible, le dire dans le chat et ne pas clore la livraison.

