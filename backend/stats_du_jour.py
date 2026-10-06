"""Statistiques internes du jour demandées par SAWALI (rapport quotidien Liluvine).

Protocole (fixé côté SAWALI, ne pas le modifier) :
  - SAWALI envoie un POST signé sur l'URL de retour habituelle
    (POST /api/webhooks/liluvine-retour, mêmes en-têtes X-Emetteur / X-Timestamp /
    X-Signature, même clé LILUVINE_WA_HMAC que les autres retours) ;
  - corps : {"type": "stats_du_jour", "debut": "<ISO>", "fin": "<ISO>"}
    (heures UTC, « debut » inclus, « fin » exclu) ;
  - réponse attendue (HTTP 200, en moins de 8 secondes) :
    {"indicateurs": [{"cle", "libelle", "valeur"}, ...] (4 à 10),
     "faits_marquants": ["phrase courte", ...] (5 au plus)}.

Rien n'est écrit en base : ce module ne fait que COMPTER. Chaque indicateur est
calculé séparément : si l'un d'eux échoue, il vaut « n/d » et les autres restent
justes (le rapport de SAWALI n'est jamais bloqué par un seul calcul).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Optional

from db import db

logger = logging.getLogger(__name__)

TYPE_DEMANDE = "stats_du_jour"  # valeur du champ « type » envoyée par SAWALI
DELAI_MAX = 6.0  # secondes : SAWALI attend 8 s au plus, on garde une marge
DUREE_MAX_PERIODE = timedelta(days=31)  # garde-fou : une période plus longue est refusée
FAITS_MAX = 5  # nombre maximal de faits marquants renvoyés
NON_DISPONIBLE = "n/d"  # valeur affichée quand un calcul a échoué


# ---------------------------------------------------------------------------
# Lecture et contrôle de la période demandée
# ---------------------------------------------------------------------------
def _lire_date(valeur: Any) -> Optional[datetime]:
    """Convertit une date ISO (« 2026-10-05T00:00:00Z » ou « …+00:00 ») en
    date/heure UTC. Une date sans fuseau est considérée comme UTC.
    Renvoie None si la valeur est absente ou illisible."""
    if not isinstance(valeur, str) or not valeur.strip():
        return None
    try:
        d = datetime.fromisoformat(valeur.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def lire_periode(doc: dict) -> tuple[str, str]:
    """Période [debut, fin) au format des dates enregistrées par adLyn (now_iso :
    « AAAA-MM-JJTHH:MM:SS+00:00 »), ce qui permet de comparer directement les
    chaînes en base. ValueError si la période est absente, inversée ou trop longue."""
    debut, fin = _lire_date(doc.get("debut")), _lire_date(doc.get("fin"))
    if not debut or not fin:
        raise ValueError("Champs « debut » et « fin » obligatoires (dates ISO)")
    if fin <= debut:
        raise ValueError("La fin de la période doit être après le début")
    if fin - debut > DUREE_MAX_PERIODE:
        raise ValueError("Période trop longue (31 jours au plus)")
    return debut.isoformat(), fin.isoformat()


# ---------------------------------------------------------------------------
# Petits outils de calcul
# ---------------------------------------------------------------------------
def _entre(debut: str, fin: str) -> dict:
    """Filtre MongoDB « date dans [debut, fin) » sur une date ISO enregistrée en texte."""
    return {"$gte": debut, "$lt": fin}


async def _somme(collection, filtre: dict, champ: str) -> tuple[int, float]:
    """Nombre de documents ET somme d'un champ montant (un seul passage en base)."""
    resultat = await collection.aggregate([
        {"$match": filtre},
        {"$group": {"_id": None, "nb": {"$sum": 1}, "total": {"$sum": f"${champ}"}}},
    ]).to_list(1)
    if not resultat:
        return 0, 0
    return int(resultat[0].get("nb") or 0), float(resultat[0].get("total") or 0)


def _arrondi(montant: float) -> int | float:
    """Montant FCFA lisible : entier quand il n'y a pas de décimales utiles."""
    return int(round(montant)) if abs(montant - round(montant)) < 0.01 else round(montant, 2)


def _fcfa(montant: float) -> str:
    """Montant en texte français : « 250 000 FCFA »."""
    return f"{int(round(montant)):,}".replace(",", " ") + " FCFA"


def _pluriel(n: int, singulier: str, pluriel: str) -> str:
    """Accord simple : « 1 boutique » / « 3 boutiques »."""
    return singulier if n <= 1 else pluriel


async def _sur(calcul: Awaitable, nom: str):
    """Exécute un calcul ; en cas d'erreur, renvoie None et le note dans les logs
    (sans aucune donnée personnelle)."""
    try:
        return await calcul
    except Exception as exc:  # noqa: BLE001 — un calcul en échec ne doit pas casser le rapport
        logger.warning("Statistiques du jour : calcul « %s » impossible (%s)", nom, type(exc).__name__)
        return None


# ---------------------------------------------------------------------------
# Calcul des indicateurs et des faits marquants
# ---------------------------------------------------------------------------
async def _calculer(debut: str, fin: str) -> dict:
    periode = _entre(debut, fin)

    # --- 1. Lancement de tous les comptages EN PARALLÈLE (réponse rapide) ---
    taches = {
        # Connexions réussies au portail (journal des connexions des boutiques)
        "connexions": db.connexions_journal.count_documents({"date": periode, "resultat": "SUCCES"}),
        # Tentatives refusées (mauvais identifiants ou règle d'accès)
        "connexions_refusees": db.connexions_journal.count_documents(
            {"date": periode, "resultat": {"$in": ["ECHEC", "BLOQUE"]}}),
        # Boutiques créées sur la période (inscriptions)
        "boutiques_nouvelles": db.boutiques.find(
            {"created_at": periode}, {"_id": 0, "nom": 1}).to_list(200),
        # Boutiques actives (photo à l'instant de la demande, boutiques de test exclues)
        "boutiques_actives": db.boutiques.count_documents({"actif": True, "test": {"$ne": True}}),
        # Nouveaux clients enregistrés par les boutiques (fiche ou commande en ligne)
        "clients_nouveaux": db.clients.count_documents({"created_at": periode}),
        # Commandes reçues sur les vitrines en ligne
        "commandes": _somme(db.commandes, {"date": periode}, "total"),
        # Factures validées sur la période (nombre + chiffre d'affaires TTC)
        "factures": _somme(db.documents, {"type_document": "FAC", "statut": {"$ne": "BROUILLON"},
                                          "date_validation": periode}, "total_ttc"),
        # Proformas créées sur la période
        "proformas": db.documents.count_documents({"type_document": "PRO", "created_at": periode}),
        # Paiements en ligne (PawaPay) confirmés sur la période
        "paiements": _somme(db.paiements, {"statut": "paye", "updated_at": periode}, "montant"),
        # Abonnements payés (nouveaux ou renouvelés) sur la période
        "abonnements": _somme(db.abonnement_paiements, {"created_at": periode}, "montant"),
        # Parrainages enregistrés sur la période
        "parrainages": db.parrainages.count_documents({"created_at": periode}),
        # Plus grosse facture validée de la période
        "plus_grosse_facture": db.documents.find(
            {"type_document": "FAC", "statut": {"$ne": "BROUILLON"}, "date_validation": periode},
            {"_id": 0, "total_ttc": 1, "boutique_id": 1}).sort("total_ttc", -1).to_list(1),
        # Abonnements qui arrivent à échéance dans les 3 prochains jours
        "echeances_proches": _echeances_proches(),
    }
    noms = list(taches)
    valeurs = await asyncio.gather(*(_sur(taches[n], n) for n in noms))
    r = dict(zip(noms, valeurs))

    # --- 2. Indicateurs (10 au plus) ---
    def val(v):
        """Valeur affichée : le nombre, ou « n/d » si le calcul a échoué."""
        return NON_DISPONIBLE if v is None else v

    def nb(cle):
        """Nombre de documents d'un calcul « _somme » (ou « n/d »)."""
        return NON_DISPONIBLE if r[cle] is None else r[cle][0]

    def montant(cle):
        """Montant total d'un calcul « _somme » (ou « n/d »)."""
        return NON_DISPONIBLE if r[cle] is None else _arrondi(r[cle][1])

    nouvelles = r["boutiques_nouvelles"]
    indicateurs = [
        {"cle": "connexions", "libelle": "Connexions", "valeur": val(r["connexions"])},
        {"cle": "boutiques_nouvelles", "libelle": "Nouvelles boutiques",
         "valeur": NON_DISPONIBLE if nouvelles is None else len(nouvelles)},
        {"cle": "boutiques_actives", "libelle": "Boutiques actives", "valeur": val(r["boutiques_actives"])},
        {"cle": "clients_nouveaux", "libelle": "Nouveaux clients", "valeur": val(r["clients_nouveaux"])},
        {"cle": "commandes", "libelle": "Commandes en ligne", "valeur": nb("commandes")},
        {"cle": "factures", "libelle": "Factures validées", "valeur": nb("factures")},
        {"cle": "chiffre_affaires", "libelle": "Montant facturé (FCFA)", "valeur": montant("factures")},
        {"cle": "paiements", "libelle": "Paiements en ligne reçus", "valeur": nb("paiements")},
        {"cle": "montant_paiements", "libelle": "Montant encaissé en ligne (FCFA)", "valeur": montant("paiements")},
        {"cle": "abonnements_payes", "libelle": "Abonnements payés", "valeur": nb("abonnements")},
    ]

    # --- 3. Faits marquants (5 au plus, phrases courtes) ---
    faits: list[str] = []
    if nouvelles:
        liste = ", ".join(b.get("nom", "?") for b in nouvelles[:3]) + (" …" if len(nouvelles) > 3 else "")
        faits.append(f"{len(nouvelles)} {_pluriel(len(nouvelles), 'nouvelle boutique inscrite', 'nouvelles boutiques inscrites')} : {liste}")
    if r["plus_grosse_facture"]:
        fac = r["plus_grosse_facture"][0]
        nom = await _sur(_nom_boutique(fac.get("boutique_id")), "nom_boutique")
        faits.append(f"Plus grosse facture : {_fcfa(fac.get('total_ttc') or 0)}" + (f" ({nom})" if nom else ""))
    if r["echeances_proches"]:
        n = r["echeances_proches"]
        faits.append(f"{n} {_pluriel(n, 'abonnement arrive', 'abonnements arrivent')} à échéance d'ici 3 jours")
    if r["abonnements"] and r["abonnements"][0]:
        faits.append(f"Abonnements encaissés : {_fcfa(r['abonnements'][1])}")
    if r["parrainages"]:
        n = r["parrainages"]
        faits.append(f"{n} {_pluriel(n, 'parrainage enregistré', 'parrainages enregistrés')}")
    if r["proformas"]:
        n = r["proformas"]
        faits.append(f"{n} {_pluriel(n, 'proforma émise', 'proformas émises')}")
    if r["connexions_refusees"]:
        n = r["connexions_refusees"]
        faits.append(f"{n} {_pluriel(n, 'tentative de connexion refusée', 'tentatives de connexion refusées')}")
    return {"indicateurs": indicateurs, "faits_marquants": faits[:FAITS_MAX]}


async def _echeances_proches() -> int:
    """Boutiques actives (hors test) dont l'échéance d'abonnement tombe entre
    aujourd'hui et dans 3 jours (dates « AAAA-MM-JJ » au fuseau de la plateforme)."""
    from abonnements import aujourd_hui  # import local : évite une dépendance au chargement

    jour = aujourd_hui()
    return await db.boutiques.count_documents({
        "actif": True, "test": {"$ne": True},
        "abonnement.echeance": {"$gte": jour.isoformat(), "$lte": (jour + timedelta(days=3)).isoformat()}})


async def _nom_boutique(boutique_id: Optional[str]) -> str:
    """Nom d'une boutique (vide si inconnue)."""
    if not boutique_id:
        return ""
    fiche = await db.boutiques.find_one({"id": boutique_id}, {"_id": 0, "nom": 1})
    return (fiche or {}).get("nom", "")


async def statistiques(doc: dict) -> dict:
    """Point d'entrée appelé par le webhook : période contrôlée (ValueError si
    invalide), puis calcul borné à DELAI_MAX secondes. Si le délai est dépassé,
    on renvoie quand même une réponse valide (indicateurs « n/d »)."""
    debut, fin = lire_periode(doc)
    try:
        return await asyncio.wait_for(_calculer(debut, fin), timeout=DELAI_MAX)
    except asyncio.TimeoutError:
        logger.warning("Statistiques du jour : délai de %s s dépassé", DELAI_MAX)
        return {"indicateurs": [{"cle": c, "libelle": l, "valeur": NON_DISPONIBLE} for c, l in (
            ("connexions", "Connexions"), ("boutiques_nouvelles", "Nouvelles boutiques"),
            ("boutiques_actives", "Boutiques actives"), ("clients_nouveaux", "Nouveaux clients"))],
            "faits_marquants": ["Statistiques indisponibles : calcul trop long"]}
