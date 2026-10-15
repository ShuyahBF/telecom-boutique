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
- Sur TOUT tableau : ligne survolée = fond bleu clair transparent
  (`rgba(56, 189, 248, 0.16)`) ; ligne sélectionnée = fond orange clair
  (`#f6a35b`) avec police blanche.
- Mise en œuvre globale dans le CSS de chaque plateforme ; une ligne est
  sélectionnée si elle porte `ligne-selectionnee`, `aria-selected="true"`,
  `data-selected="true"`, ou si la case à cocher de sa première cellule est cochée.

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
