# Caisse Aizenta — contrat d'échange Loois → adLyn (version 1)

Ce document décrit comment **Loois** envoie à **adLyn** la situation de caisse du
logiciel **Aizenta** d'une boutique. adLyn l'affiche dans l'écran « Caisse Aizenta »
du back-office (toujours présent dans le menu de la boutique).

Code serveur : `backend/caisse_aizenta.py` (contrat, enregistrement, calculs) et
`backend/routes/caisse_aizenta.py` (webhook, écran, administration).
Tests : `backend/tests/test_caisse_aizenta.py`.

---

## 1. Mise en service (à faire une fois par boutique)

1. **Super-admin adLyn** : page *Plateforme* → carte de la boutique →
   **« 🧭 Barre latérale & Caisse Aizenta »** → **« Générer le jeton »**.
   Le jeton (`aiz_…`) n'est **affiché qu'une seule fois** : copiez-le aussitôt.
   adLyn n'en garde qu'une empreinte (SHA-256) ; s'il est perdu, on en régénère
   un nouveau (l'ancien cesse alors immédiatement de fonctionner).
2. **Loois** (poste où tourne Aizenta) : saisir
   - l'adresse du webhook, affichée dans la même fenêtre, de la forme
     `https://<adresse de l'API adLyn>/api/webhooks/caisse-aizenta` ;
   - l'**ID boutique** (code marchand de 6 caractères, ex. `K7M2QD`) ;
   - le **jeton**.
3. Vérifier dans la même fenêtre, rubrique « Dernières réceptions », que les
   envois arrivent avec le résultat « ✅ Acceptée ».

Le bouton « Révoquer le jeton » coupe la réception ; les données déjà reçues
sont conservées.

---

## 2. Appel HTTP

```
POST /api/webhooks/caisse-aizenta
Authorization: Bearer <jeton de la boutique>
X-Code-Boutique: K7M2QD            (facultatif si "code_boutique" est dans le corps)
Content-Type: application/json; charset=utf-8

<corps JSON décrit ci-dessous>
```

- Le jeton ne vaut que pour **sa** boutique : un jeton d'une autre boutique est refusé.
- Si le code boutique figure à la fois dans l'en-tête et dans le corps, ils doivent être identiques.
- Corps limité à **8 Mo** (environ 20 000 opérations) : au-delà, découper la période
  (par exemple un envoi par jour).
- Au plus **30 appels par minute** par adresse IP ; après **10 appels refusés** dans
  l'heure (réglage `WEBHOOK_MAX_ECHECS_IP`), l'adresse est bloquée jusqu'à la fin de l'heure.

### Réponses

| Code | Signification |
|------|---------------|
| 200  | Envoi accepté. Le corps indique les compteurs (voir ci-dessous). |
| 400  | Corps illisible (JSON invalide), code boutique absent ou incohérent. |
| 401  | Jeton absent, ou jeton invalide pour cette boutique (même réponse si la boutique n'existe pas). |
| 413  | Envoi trop volumineux. |
| 422  | Contenu non conforme au contrat : la liste `erreurs` dit précisément quoi corriger. **Rien n'est enregistré.** |
| 429  | Trop d'envois : réessayer plus tard. |

Exemple de réponse acceptée :

```json
{
  "resultat": "acceptee",
  "reception_id": "6b0d1c9e-…",
  "periode": {"du": "2026-10-01", "au": "2026-10-01"},
  "nb_operations": 3, "nb_arrets": 0, "nb_types_paiement": 3,
  "operations_nouvelles": 2, "operations_mises_a_jour": 1, "operations_supprimees": 0,
  "arrets_nouvelles": 0, "arrets_mises_a_jour": 0, "arrets_supprimees": 0
}
```

Exemple de refus (422) :

```json
{
  "resultat": "refusee",
  "detail": "Contenu non conforme au contrat v1",
  "erreurs": [
    "operations[3].montant : nombre attendu",
    "operations[7].date_heure : 2026-10-02 est en dehors de la période envoyée (2026-10-01 au 2026-10-01)",
    "operations[9] : le téléphone du client ne doit pas être transmis (donnée personnelle inutile à la caisse)"
  ]
}
```

Chaque appel (accepté ou refusé) est inscrit au **journal des réceptions** : date,
boutique, adresse IP, période, nombre de lignes, résultat, erreurs.

---

## 3. Corps JSON (contrat v1)

**Validation stricte** : un champ inconnu est une erreur (cela détecte les fautes de
frappe dans Loois). Les textes sont débarrassés de leurs espaces en début et fin.

### 3.1 En-tête de l'envoi

| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `version` | entier | oui | Toujours `1`. |
| `code_boutique` | texte (6 lettres/chiffres) | oui* | ID boutique adLyn. *Peut être remplacé par l'en-tête `X-Code-Boutique`. |
| `source` | texte | non | `"Loois"` par défaut. |
| `base` | texte | non | Nom de la base Aizenta (affiché dans le journal). |
| `genere_le` | date-heure ISO 8601 | non | Moment où Loois a préparé l'envoi. |
| `periode` | objet `{"du": "AAAA-MM-JJ", "au": "AAAA-MM-JJ"}` | oui | Période couverte (bornes incluses, 366 jours au plus). **Toutes** les opérations et arrêts envoyés doivent être dans cette période. |
| `remplacer_periode` | booléen | non (`false`) | `true` : adLyn **remplace** tout ce qu'il connaît de la période par le contenu de l'envoi (les opérations qui n'y figurent plus sont supprimées ; une liste vide vide la période). `false` : ajout / mise à jour seulement. |
| `types_paiement` | liste | non | Référentiel **TypePaiementCaisse** (voir 3.3). |
| `operations` | liste (20 000 au plus) | non (vide par défaut) | Opérations de caisse (voir 3.2). |
| `arrets_caisse` | liste (2 000 au plus) | non | Arrêts (clôtures) de caisse (voir 3.4). Absent de la source RèglementCaisse : à omettre. |

### 3.2 Opération (`operations[]`) = une ligne de la table **RèglementCaisse**

| Champ JSON | Colonne Aizenta | Type | Obligatoire | Remarques |
|------------|-----------------|------|-------------|-----------|
| `id` | `Numéro` | texte (1 à 100) | oui | Identifiant **unique** de la ligne côté Aizenta. Clé d'idempotence. |
| `date_heure` | `DateHeure_Création`, sinon `Date` | date-heure ISO 8601 | oui | `"2026-10-01T09:15:00"`, `"2026-10-01T09:15:00Z"`, avec décalage (`+01:00`, converti en UTC) ou date seule (`"2026-10-01"` = minuit). Sans fuseau : heure de Ouagadougou (UTC+0). |
| `type` | — | `VENTE` \| `REGLEMENT` \| `AVOIR` \| `DEPENSE` \| `VERSEMENT` \| `FOND_DE_CAISSE` \| `AUTRE` | non | `REGLEMENT` par défaut (cas de RèglementCaisse). |
| `mode_paiement` | (déduit de `TypeRèglementCaisse`) | `ESPECES` \| `MOBILE_MONEY` \| `CHEQUE` \| `CARTE` \| `CREDIT` \| `AUTRE` | non | Mode **normalisé**, `AUTRE` par défaut. Indicatif seulement. |
| `mode_paiement_code` | `TypeRèglementCaisse` | texte (30) | non | Code d'origine du type de paiement (TypePaiementCaisse). |
| `mode_paiement_libelle` | libellé de TypePaiementCaisse | texte (100) | non | Libellé d'origine. **C'est lui qui sert à la ventilation « par mode de paiement »** (à défaut : libellé du référentiel `types_paiement` pour ce code, puis le mode normalisé). |
| `montant` | `Montant` | nombre (entier ou décimal) | oui | En F CFA. **Le signe fait foi** (voir 3.5). Un texte `"15000"` est refusé. |
| `caissier` | `Caissier` | texte (100) | non | Sert à la ventilation « par caissier ». |
| `poste` | — | texte (100) | non | Poste de caisse. |
| `reference` | `Recu A` / `Recu M` | texte (100) | non | Numéro de reçu. |
| `libelle` | — | texte (300) | non | |
| `observation` | `Observation` | texte (500) | non | |
| `code_client` | `Code_Client` | texte (60) | non | Code du client dans Aizenta (aucune autre donnée client). |
| `cheque` | `Chèque`, `Date Chèque`, `Echéance` | objet `{"numero", "date", "echeance"}` | non | Dates au format `AAAA-MM-JJ`. |

**Ne jamais transmettre** la colonne `Téléphone` (donnée personnelle du client,
inutile pour une situation de caisse) : un champ `telephone` / `téléphone` est
**refusé** avec un message explicite. Les colonnes `LC` et
`DateHeure_modification` ne sont pas utilisées.

### 3.3 Référentiel des types de paiement (`types_paiement[]`) = table **TypePaiementCaisse**

| Champ | Type | Obligatoire | Remarques |
|-------|------|-------------|-----------|
| `code` | texte (1 à 30) | oui | Valeur référencée par `RèglementCaisse.TypeRèglementCaisse`. |
| `libelle` | texte (1 à 100) | oui | Libellé affiché. |
| `mode_paiement` | mode normalisé | non | Correspondance indicative. |

adLyn mémorise ce référentiel **par boutique** (mis à jour à chaque envoi qui le
contient) : une opération qui ne porte que `mode_paiement_code` est alors libellée
correctement.

### 3.4 Arrêt de caisse (`arrets_caisse[]`, facultatif)

| Champ | Type | Obligatoire | Remarques |
|-------|------|-------------|-----------|
| `id` | texte | oui | Unique côté Aizenta. |
| `date_heure` | date-heure ISO 8601 | oui | |
| `caissier` | texte | non | |
| `montant_theorique` | nombre | oui | |
| `montant_compte` | nombre | oui | |
| `ecart` | nombre | non | Calculé par adLyn (`compté − théorique`) s'il est absent. |

L'écran ne montre la rubrique « Arrêts de caisse » que s'il y en a sur la période.

### 3.5 Convention des montants (choix retenu)

- **Entrée d'argent : montant positif. Sortie (dépense, versement en banque, avoir
  remboursé…) : montant NÉGATIF.** Le `type` sert seulement à classer.
- `FOND_DE_CAISSE` (monnaie de départ) n'est compté **ni** dans le total encaissé
  **ni** dans le solde net ; il est affiché à part.
- Total encaissé = somme des montants positifs (hors fond de caisse) ;
  Sorties = somme des montants négatifs (affichée en positif) ;
  **Solde net = total encaissé − sorties.**

### 3.6 Idempotence

- Clé d'unicité : **(boutique, `id`)**. Renvoyer la même période ne crée jamais de
  doublon : une opération déjà connue est **mise à jour** (montant corrigé, etc.).
- Le même `id` deux fois dans un même envoi est refusé.
- Pour qu'une ligne **supprimée dans Aizenta** disparaisse aussi d'adLyn, renvoyer
  la période avec `"remplacer_periode": true`.
- Conseil pour Loois : envoyer « aujourd'hui » toutes les 10 à 15 minutes avec
  `remplacer_periode: true`, et la veille une dernière fois après la clôture.

---

## 4. Exemple complet (données fictives)

```json
{
  "version": 1,
  "code_boutique": "K7M2QD",
  "source": "Loois",
  "base": "AIZENTA_DEMO",
  "genere_le": "2026-10-01T18:30:00Z",
  "periode": {"du": "2026-10-01", "au": "2026-10-01"},
  "remplacer_periode": true,
  "types_paiement": [
    {"code": "1", "libelle": "Espèces", "mode_paiement": "ESPECES"},
    {"code": "2", "libelle": "Orange Money", "mode_paiement": "MOBILE_MONEY"},
    {"code": "3", "libelle": "Chèque", "mode_paiement": "CHEQUE"}
  ],
  "operations": [
    {
      "id": "RC-000101",
      "date_heure": "2026-10-01T08:05:00",
      "type": "FOND_DE_CAISSE",
      "mode_paiement": "ESPECES", "mode_paiement_code": "1", "mode_paiement_libelle": "Espèces",
      "montant": 25000,
      "caissier": "CAISSIER 1", "poste": "CAISSE-1"
    },
    {
      "id": "RC-000102",
      "date_heure": "2026-10-01T09:15:00",
      "type": "REGLEMENT",
      "mode_paiement": "MOBILE_MONEY", "mode_paiement_code": "2", "mode_paiement_libelle": "Orange Money",
      "montant": 15000,
      "caissier": "CAISSIER 1", "poste": "CAISSE-1",
      "reference": "RA-00451", "code_client": "CLI-0007",
      "observation": "Acompte"
    },
    {
      "id": "RC-000103",
      "date_heure": "2026-10-01T11:40:00",
      "type": "REGLEMENT",
      "mode_paiement": "CHEQUE", "mode_paiement_code": "3", "mode_paiement_libelle": "Chèque",
      "montant": 120000.5,
      "caissier": "CAISSIER 2",
      "reference": "RM-00012",
      "cheque": {"numero": "0001234", "date": "2026-10-01", "echeance": "2026-10-31"}
    },
    {
      "id": "RC-000104",
      "date_heure": "2026-10-01T16:00:00",
      "type": "DEPENSE",
      "mode_paiement": "ESPECES", "mode_paiement_code": "1",
      "montant": -3500,
      "caissier": "CAISSIER 1",
      "libelle": "Achat de fournitures"
    }
  ],
  "arrets_caisse": [
    {"id": "AR-0001", "date_heure": "2026-10-01T19:00:00", "caissier": "CAISSIER 1",
     "montant_theorique": 36500, "montant_compte": 36000}
  ]
}
```

Situation obtenue dans adLyn pour le 01/10/2026 : total encaissé 135 000,5 F ;
sorties 3 500 F ; solde net 131 500,5 F ; fond de caisse 25 000 F ;
arrêt de caisse avec un écart de −500 F (mis en évidence).

---

## 5. Écran « Caisse Aizenta » (back-office de la boutique)

- **Qui le voit** : le DG, le comptable et le secrétariat (permission
  `caisse_aizenta` dans `backend/auth.py`). Les commerciaux et techniciens ne le
  voient pas. L'option est toujours active (non désactivable par le super-admin).
- **Période** : Aujourd'hui (par défaut), Hier, 7 derniers jours, Ce mois, ou
  intervalle personnalisé (du / au). « Aujourd'hui » = date de Ouagadougou (UTC+0).
- **Situation** : total encaissé, sorties, solde net, nombre d'opérations (fond de
  caisse à part) ; ventilations **par type**, **par mode de paiement** (libellé
  d'origine Aizenta, avec son code) et **par caissier** ; arrêts de caisse avec
  écarts ; liste détaillée paginée et filtrable (type, mode, caissier, recherche) ;
  **export CSV** (séparateur `;`, lisible par Excel).
- **Dernière réception** de Loois affichée, avec une **alerte si rien n'est arrivé
  depuis plus de 24 heures**. Sans aucune donnée, l'écran explique comment
  configurer Loois (adresse du webhook, jeton, ID boutique).

## 6. Données en base (MongoDB, préfixe `tlb_`)

| Collection | Contenu |
|------------|---------|
| `caisse_operations` | Opérations (index unique `boutique_id` + `id_aizenta`, index `boutique_id` + `jour`). |
| `caisse_arrets` | Arrêts de caisse (même principe). |
| `caisse_types_paiement` | Référentiel TypePaiementCaisse par boutique. |
| `caisse_jetons` | Empreinte SHA-256 du jeton de chaque boutique (jamais le jeton). |
| `caisse_receptions` | Journal des appels du webhook. |

Les trois premières sont incluses dans la sauvegarde chiffrée de la boutique.
