# Maintenance de la plateforme — déconnexion de tous les utilisateurs

Espace super-admin : **Plateforme › Paramètres › Déconnexion de tous les utilisateurs**.

## Déroulement

| Phase | Période | Personnel des boutiques | Super-admin |
|---|---|---|---|
| Annonce | de l'envoi au début du verrouillage (100 − part %) | modale fermable (message + décompte), puis bandeau rouge | bandeau orange + « Annuler » |
| Verrouillage | dernière part de la durée (80 % par défaut) | écran plein, non fermable (ni Échap, ni clic, page inerte), décompte mm:ss | idem |
| Maintenance | à l'échéance, jusqu'à la réactivation | déconnexion forcée ; API → **503** ; connexion et mot de passe oublié → **503** | bandeau rouge « Maintenance en cours — connexions bloquées » + « Réactiver les connexions » |

- Réglages : message (obligatoire, 1 000 caractères max), durée 1 à 120 min (5 par défaut), part verrouillée 0 à 100 % (80 par défaut).
- Décompte calé sur l'heure du serveur (`maintenant_serveur`) ; état relu toutes les 15 s et au retour sur l'onglet.
- Annulation possible avant l'échéance : personne n'est déconnecté.
- Réactivation : « sessions valides après » = échéance ; les sessions ouvertes avant restent invalides (401), chacun se reconnecte.
- Les super-admins ne sont jamais bloqués.

## Routes

- `GET /api/maintenance/etat` — public, sans donnée sensible (phase, message, dates, `secondes_restantes`, `maintenant_serveur`).
- `GET|POST /api/plateforme/deconnexion-generale`, `POST …/annuler`, `POST …/reactiver` — super-admin.

## Non bloqué

Webhooks entrants (`/api/webhooks/boutiques`, `/api/webhooks/caisse-aizenta`, `/api/paiements/webhooks/depots/{secret}`),
portail et catalogue publics (`/api/public/…`, `GET /api/paiements/{deposit_id}`, `/api/tiktok/callback`),
`/api/health`, `/api/maintenance/etat`, `/api/auth/logout`, et les tâches de fond (aucune session).

## Stockage

`tlb_maintenance_plateforme` (document unique `_id: "etat"`) et `tlb_maintenance_plateforme_journal`
(annonce, annulation, réactivation : qui, quand, message, durée, part verrouillée).

## Reprendre sur une autre plateforme

Copier `backend/maintenance_plateforme.py`, `backend/routes/maintenance_plateforme.py`,
`frontend/src/lib/maintenancePlateforme.js`, `frontend/src/components/MaintenancePlateforme.jsx`,
`frontend/src/pages/plateforme/_plateforme/DeconnexionGenerale.jsx`, puis brancher :
heure d'ouverture `ouv` dans le jeton + `controler_session` dans la vérification de session,
`refuser_si_maintenance` dans la connexion et le mot de passe oublié, les deux routeurs (le public
avant toute route `/maintenance/{id}`), `<SurveillanceMaintenance />` dans le routeur du site et
`<AvisMaintenance />` sur la page de connexion.
