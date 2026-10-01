"""Caisse Aizenta : situation de caisse reçue de Loois (contrat JSON v1).

Loois (outil installé chez la boutique) lit deux tables HFSQL du logiciel Aizenta :
  - « RèglementCaisse »    : un enregistrement par règlement encaissé ;
  - « TypePaiementCaisse » : référentiel des types / modes de paiement
                             (code + libellé), cité par RèglementCaisse.TypeRèglementCaisse.
Il envoie ces données à adLyn sur le webhook POST /api/webhooks/caisse-aizenta
(voir routes/caisse_aizenta.py et docs/caisse-aizenta.md pour le contrat complet).

Ce module contient :
  1. le CONTRAT (modèles Pydantic, validation stricte, messages d'erreur en français) ;
  2. l'ENREGISTREMENT idempotent (une opération = une ligne par boutique et par
     identifiant Aizenta : renvoyer la même période ne crée jamais de doublon) ;
  3. les CALCULS de la situation de caisse sur une période (totaux, ventilations).

Conventions retenues :
  - Montants en F CFA (entiers ou décimaux). LE SIGNE FAIT FOI : une ENTRÉE
    d'argent est positive, une SORTIE (dépense, versement en banque, avoir
    remboursé…) est NÉGATIVE. Le « type » ne sert qu'à classer.
  - « FOND_DE_CAISSE » (monnaie de départ) n'est compté ni dans les encaissements
    ni dans le solde net : il est affiché à part.
  - Heures : Ouagadougou est à UTC+0 toute l'année. Une heure SANS fuseau est donc
    prise telle quelle ; une heure AVEC fuseau est convertie en UTC.
  - Le téléphone du client (colonne « Téléphone » de RèglementCaisse) n'est NI
    transmis NI stocké : donnée personnelle inutile pour une situation de caisse.

Collections (toutes cloisonnées par boutique_id) :
  caisse_operations, caisse_arrets, caisse_types_paiement, caisse_receptions (journal),
  caisse_jetons (jeton d'accès du webhook, stocké HACHÉ).
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, ValidationError, field_validator, model_validator
from pymongo import UpdateOne

from db import SANS_ID, db
from utils import new_id, now_iso

VERSION_CONTRAT = 1
OPERATIONS_MAX = 20_000  # opérations au plus par envoi (découper les grosses périodes)
ARRETS_MAX = 2_000
TYPES_PAIEMENT_MAX = 500
PERIODE_MAX_JOURS = 366

TYPES = ("VENTE", "REGLEMENT", "AVOIR", "DEPENSE", "VERSEMENT", "FOND_DE_CAISSE", "AUTRE")
LIBELLES_TYPE = {"VENTE": "Vente", "REGLEMENT": "Règlement", "AVOIR": "Avoir", "DEPENSE": "Dépense",
                 "VERSEMENT": "Versement", "FOND_DE_CAISSE": "Fond de caisse", "AUTRE": "Autre"}
MODES = ("ESPECES", "MOBILE_MONEY", "CHEQUE", "CARTE", "CREDIT", "AUTRE")
LIBELLES_MODE = {"ESPECES": "Espèces", "MOBILE_MONEY": "Mobile Money", "CHEQUE": "Chèque", "CARTE": "Carte",
                 "CREDIT": "Crédit", "AUTRE": "Autre"}

# Un montant : nombre entier ou décimal (pas de texte « 15000 », pas d'infini)
Montant = Union[StrictInt, StrictFloat]
MONTANT_MAX = 1e12
CHAMPS_INTERDITS = ("telephone", "téléphone", "Telephone", "Téléphone", "tel")


# ---------------------------------------------------------------------------
# Dates et heures
# ---------------------------------------------------------------------------
def aujourd_hui() -> date:
    """Date du jour à Ouagadougou (UTC+0 toute l'année)."""
    return datetime.now(timezone.utc).date()


def lire_date_heure(valeur: Any) -> datetime:
    """« 2026-10-01 », « 2026-10-01T09:15:00 », « 2026-10-01T09:15:00Z » ou avec
    décalage (+01:00) -> date et heure UTC (= heure de Ouagadougou), sans fuseau."""
    if not isinstance(valeur, str) or not valeur.strip():
        raise ValueError("date/heure attendue au format ISO 8601, ex. 2026-10-01T09:15:00")
    texte = valeur.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texte):
        texte += "T00:00:00"
    try:
        dh = datetime.fromisoformat(texte.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError as exc:
        raise ValueError(f"date/heure invalide « {valeur[:40]} » (format ISO 8601 attendu, ex. 2026-10-01T09:15:00)") from exc
    if dh.tzinfo is not None:
        dh = dh.astimezone(timezone.utc).replace(tzinfo=None)
    return dh.replace(microsecond=0)


# ---------------------------------------------------------------------------
# 1. Contrat JSON v1 (validation stricte : champ inconnu = erreur)
# ---------------------------------------------------------------------------
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _sans_telephone(donnees: Any) -> Any:
    """Refuse explicitement le téléphone du client (donnée personnelle)."""
    if isinstance(donnees, dict):
        for cle in donnees:
            if str(cle) in CHAMPS_INTERDITS:
                raise ValueError("le téléphone du client ne doit pas être transmis (donnée personnelle inutile à la caisse)")
    return donnees


def _verifier_montant(v: Optional[float]) -> Optional[float]:
    if v is not None and (v != v or abs(v) > MONTANT_MAX):  # v != v : « pas un nombre » (NaN)
        raise ValueError("montant hors limites")
    return v


class Cheque(_Strict):
    numero: str = Field("", max_length=60)
    date: Optional[str] = Field(None, max_length=30)
    echeance: Optional[str] = Field(None, max_length=30)

    @field_validator("date", "echeance")
    @classmethod
    def _date(cls, v):
        if v in (None, ""):
            return None
        return lire_date_heure(v).date().isoformat()


class TypePaiement(_Strict):
    """Une ligne du référentiel TypePaiementCaisse d'Aizenta."""
    code: str = Field(..., min_length=1, max_length=30)
    libelle: str = Field(..., min_length=1, max_length=100)
    # Correspondance facultative vers un mode normalisé (indicatif)
    mode_paiement: Optional[Literal["ESPECES", "MOBILE_MONEY", "CHEQUE", "CARTE", "CREDIT", "AUTRE"]] = None


class Operation(_Strict):
    """Une opération de caisse (pour Loois : une ligne de RèglementCaisse)."""
    id: str = Field(..., min_length=1, max_length=100)  # identifiant unique côté Aizenta (Numéro)
    date_heure: str  # DateHeure_Création si présent, sinon Date
    type: Literal["VENTE", "REGLEMENT", "AVOIR", "DEPENSE", "VERSEMENT", "FOND_DE_CAISSE", "AUTRE"] = "REGLEMENT"
    mode_paiement: Literal["ESPECES", "MOBILE_MONEY", "CHEQUE", "CARTE", "CREDIT", "AUTRE"] = "AUTRE"
    mode_paiement_code: str = Field("", max_length=30)  # code TypePaiementCaisse d'origine
    mode_paiement_libelle: str = Field("", max_length=100)  # libellé TypePaiementCaisse d'origine
    montant: Montant
    caissier: str = Field("", max_length=100)
    poste: str = Field("", max_length=100)
    reference: str = Field("", max_length=100)  # Recu A / Recu M
    libelle: str = Field("", max_length=300)
    observation: str = Field("", max_length=500)
    code_client: str = Field("", max_length=60)
    cheque: Optional[Cheque] = None

    @model_validator(mode="before")
    @classmethod
    def _telephone(cls, donnees):
        return _sans_telephone(donnees)

    @field_validator("date_heure")
    @classmethod
    def _dh(cls, v):
        return lire_date_heure(v).isoformat()

    @field_validator("montant")
    @classmethod
    def _montant(cls, v):
        return _verifier_montant(v)


class ArretCaisse(_Strict):
    """Arrêt (clôture) de caisse : facultatif, absent de la source RèglementCaisse."""
    id: str = Field(..., min_length=1, max_length=100)
    date_heure: str
    caissier: str = Field("", max_length=100)
    montant_theorique: Montant
    montant_compte: Montant
    ecart: Optional[Montant] = None  # calculé (compté - théorique) s'il est absent

    @field_validator("date_heure")
    @classmethod
    def _dh(cls, v):
        return lire_date_heure(v).isoformat()

    @field_validator("montant_theorique", "montant_compte", "ecart")
    @classmethod
    def _montant(cls, v):
        return _verifier_montant(v)


class Periode(_Strict):
    du: date
    au: date

    @model_validator(mode="after")
    def _ordre(self):
        if self.du > self.au:
            raise ValueError("« du » doit être antérieur ou égal à « au »")
        if (self.au - self.du).days >= PERIODE_MAX_JOURS:
            raise ValueError(f"période trop longue ({PERIODE_MAX_JOURS} jours au plus par envoi)")
        return self


class EnvoiCaisse(_Strict):
    """Corps complet d'un envoi de Loois (contrat v1)."""
    version: Literal[1]
    code_boutique: str = Field(..., pattern=r"^[A-Za-z0-9]{6}$")
    source: str = Field("Loois", max_length=40)
    base: str = Field("", max_length=100)  # nom de la base Aizenta
    genere_le: Optional[str] = None
    periode: Periode
    # vrai : toutes les opérations (et arrêts) déjà reçus sur la période sont
    # REMPLACÉS par cet envoi (celles qui n'y figurent plus sont supprimées)
    remplacer_periode: bool = False
    types_paiement: list[TypePaiement] = Field(default_factory=list, max_length=TYPES_PAIEMENT_MAX)
    operations: list[Operation] = Field(default_factory=list, max_length=OPERATIONS_MAX)
    arrets_caisse: list[ArretCaisse] = Field(default_factory=list, max_length=ARRETS_MAX)

    @field_validator("genere_le")
    @classmethod
    def _genere(cls, v):
        return lire_date_heure(v).isoformat() if v else None

    @model_validator(mode="after")
    def _coherence(self):
        du, au = self.periode.du.isoformat(), self.periode.au.isoformat()
        for nom, lignes in (("operations", self.operations), ("arrets_caisse", self.arrets_caisse)):
            vus: set[str] = set()
            for i, ligne in enumerate(lignes):
                if ligne.id in vus:
                    raise ValueError(f"{nom}[{i}].id : identifiant « {ligne.id} » en double dans l'envoi")
                vus.add(ligne.id)
                jour = ligne.date_heure[:10]
                if not du <= jour <= au:
                    raise ValueError(f"{nom}[{i}].date_heure : {jour} est en dehors de la période envoyée ({du} au {au})")
        return self


_MESSAGES = {
    "missing": "champ obligatoire manquant",
    "extra_forbidden": "champ inconnu (non prévu par le contrat v1)",
    "literal_error": "valeur non autorisée",
    "int_type": "nombre attendu",
    "float_type": "nombre attendu",
    "string_type": "texte attendu",
    "bool_type": "vrai/faux attendu (true / false)",
    "list_type": "liste attendue",
    "date_from_datetime_parsing": "date attendue au format AAAA-MM-JJ",
    "date_parsing": "date attendue au format AAAA-MM-JJ",
    "date_type": "date attendue au format AAAA-MM-JJ",
    "string_too_long": "texte trop long",
    "string_too_short": "texte vide ou trop court",
    "string_pattern_mismatch": "format invalide",
    "too_long": "liste trop longue",
    "model_type": "objet JSON attendu",
}


def erreurs_lisibles(exc: ValidationError, limite: int = 20) -> list[str]:
    """Erreurs Pydantic -> phrases en français : « operations[3].montant : nombre attendu »."""
    lignes = []
    for err in exc.errors()[:limite]:
        chemin = ""
        for partie in err.get("loc", ()):
            if isinstance(partie, int):
                chemin += f"[{partie}]"
            elif partie in ("int", "float") or str(partie).startswith(("function-", "constrained-")):
                # Branches internes de Pydantic (entier / décimal...) : sans intérêt pour Loois
                continue
            else:
                chemin += ("." if chemin else "") + str(partie)
        message = _MESSAGES.get(err.get("type", ""))
        if err.get("type") == "literal_error":
            attendues = str(err.get("ctx", {}).get("expected", "")).replace(" or ", " ou ")
            message = f"valeur non autorisée (attendu : {attendues})"
        if err.get("type") in ("value_error", "assertion_error") or not message:
            message = str(err.get("msg", "")).removeprefix("Value error, ")
        if not chemin and re.match(r"^[a-z_]+\[\d+\]", message):
            lignes.append(message)  # message qui désigne déjà la ligne en cause
        else:
            lignes.append(f"{chemin or 'corps'} : {message}")
    if len(exc.errors()) > limite:
        lignes.append(f"… et {len(exc.errors()) - limite} autre(s) erreur(s)")
    # Doublons éventuels (une même erreur signalée pour les deux branches entier / décimal)
    return list(dict.fromkeys(lignes))


# ---------------------------------------------------------------------------
# Jeton d'accès du webhook (un par boutique, stocké HACHÉ)
# ---------------------------------------------------------------------------
def hacher_jeton(jeton: str) -> str:
    """Empreinte SHA-256 du jeton (le jeton lui-même n'est jamais enregistré)."""
    return hashlib.sha256(jeton.encode()).hexdigest()


async def generer_jeton(boutique_id: str, par: str) -> str:
    """Nouveau jeton pour la boutique (l'ancien cesse aussitôt de fonctionner).
    Renvoyé UNE SEULE FOIS : il faut le copier dans Loois tout de suite."""
    jeton = "aiz_" + secrets.token_urlsafe(32)
    await db.caisse_jetons.update_one({"boutique_id": boutique_id}, {"$set": {
        "boutique_id": boutique_id, "hash": hacher_jeton(jeton), "apercu": jeton[:8] + "…",
        "cree_le": now_iso(), "par": par}}, upsert=True)
    return jeton


async def infos_jeton(boutique_id: str) -> Optional[dict]:
    doc = await db.caisse_jetons.find_one({"boutique_id": boutique_id}, SANS_ID)
    return {k: doc[k] for k in ("apercu", "cree_le", "par") if k in doc} if doc else None


# ---------------------------------------------------------------------------
# 2. Enregistrement idempotent d'un envoi
# ---------------------------------------------------------------------------
async def enregistrer_envoi(boutique_id: str, envoi: EnvoiCaisse, reception_id: str) -> dict:
    """Écrit l'envoi en base. Clé d'unicité : (boutique, identifiant Aizenta).
    Renvoie les compteurs (nouvelles, mises à jour, supprimées)."""
    du, au = envoi.periode.du.isoformat(), envoi.periode.au.isoformat()
    recu_le = now_iso()

    # Référentiel des types de paiement (pour libeller correctement)
    for t in envoi.types_paiement:
        await db.caisse_types_paiement.update_one(
            {"boutique_id": boutique_id, "code": t.code},
            {"$set": {"boutique_id": boutique_id, "code": t.code, "libelle": t.libelle,
                      "mode_paiement": t.mode_paiement, "maj_le": recu_le}}, upsert=True)

    compteurs = {"nb_operations": len(envoi.operations), "nb_arrets": len(envoi.arrets_caisse),
                 "nb_types_paiement": len(envoi.types_paiement)}
    for collection, lignes, prefixe in ((db.caisse_operations, envoi.operations, "operations"),
                                        (db.caisse_arrets, envoi.arrets_caisse, "arrets")):
        supprimees = 0
        if envoi.remplacer_periode:
            # Tout ce qui était connu sur la période et n'est plus dans l'envoi disparaît
            ids = [l.id for l in lignes]
            res = await collection.delete_many({"boutique_id": boutique_id, "jour": {"$gte": du, "$lte": au},
                                                "id_aizenta": {"$nin": ids}})
            supprimees = res.deleted_count
        ecritures = []
        for ligne in lignes:
            doc = ligne.model_dump()
            doc["id_aizenta"] = doc.pop("id")
            doc["jour"] = doc["date_heure"][:10]
            if prefixe == "arrets" and doc.get("ecart") is None:
                doc["ecart"] = doc["montant_compte"] - doc["montant_theorique"]
            doc.update({"boutique_id": boutique_id, "base": envoi.base, "recu_le": recu_le, "reception_id": reception_id})
            ecritures.append(UpdateOne({"boutique_id": boutique_id, "id_aizenta": doc["id_aizenta"]},
                                       {"$set": doc, "$setOnInsert": {"premiere_reception": recu_le}}, upsert=True))
        nouvelles = mises_a_jour = 0
        for i in range(0, len(ecritures), 1000):  # par paquets de 1000
            res = await collection.bulk_write(ecritures[i:i + 1000], ordered=False)
            nouvelles += res.upserted_count
            mises_a_jour += res.matched_count
        compteurs.update({f"{prefixe}_nouvelles": nouvelles, f"{prefixe}_mises_a_jour": mises_a_jour,
                          f"{prefixe}_supprimees": supprimees})
    return compteurs


# ---------------------------------------------------------------------------
# 3. Situation de caisse sur une période
# ---------------------------------------------------------------------------
def borner_periode(du: Optional[str], au: Optional[str]) -> tuple[str, str]:
    """Période demandée par l'écran (par défaut : aujourd'hui à Ouagadougou)."""
    try:
        d = date.fromisoformat(du) if du else aujourd_hui()
        a = date.fromisoformat(au) if au else (d if du else aujourd_hui())
    except ValueError as exc:
        raise ValueError("Dates attendues au format AAAA-MM-JJ") from exc
    if d > a:
        raise ValueError("La date de début doit précéder la date de fin")
    if (a - d).days > 3 * PERIODE_MAX_JOURS:
        raise ValueError("Période trop longue (3 ans au plus)")
    return d.isoformat(), a.isoformat()


async def _types_paiement(boutique_id: str) -> dict[str, str]:
    return {t["code"]: t["libelle"] async for t in db.caisse_types_paiement.find({"boutique_id": boutique_id}, SANS_ID)}


def libelle_mode(op: dict, types: dict[str, str]) -> str:
    """Libellé du mode de paiement : celui d'ORIGINE (Aizenta) en priorité,
    puis celui du référentiel reçu, enfin le mode normalisé."""
    return (op.get("mode_paiement_libelle") or types.get(op.get("mode_paiement_code") or "")
            or (f"Code {op['mode_paiement_code']}" if op.get("mode_paiement_code") else "")
            or LIBELLES_MODE.get(op.get("mode_paiement"), "Autre"))


async def operations_periode(boutique_id: str, du: str, au: str) -> tuple[list[dict], dict[str, str]]:
    ops = await db.caisse_operations.find({"boutique_id": boutique_id, "jour": {"$gte": du, "$lte": au}},
                                          SANS_ID).to_list(None)
    types = await _types_paiement(boutique_id)
    for op in ops:
        op["mode_libelle"] = libelle_mode(op, types)
        op["type_libelle"] = LIBELLES_TYPE.get(op.get("type"), op.get("type"))
    ops.sort(key=lambda o: (o.get("date_heure", ""), o.get("id_aizenta", "")), reverse=True)
    return ops, types


def _arrondi(v: float) -> Union[int, float]:
    v = round(v, 2)
    return int(v) if v == int(v) else v


def calculer_situation(ops: list[dict]) -> dict:
    """Totaux et ventilations (fonction pure : facile à tester)."""
    def est_fond(o):
        return o.get("type") == "FOND_DE_CAISSE"

    encaisse = sum(o["montant"] for o in ops if o["montant"] > 0 and not est_fond(o))
    sorties = -sum(o["montant"] for o in ops if o["montant"] < 0 and not est_fond(o))
    fond = sum(o["montant"] for o in ops if est_fond(o))

    def ventiler(cle_de, avec_detail=False):
        """Regroupe les opérations selon cle_de(opération) : nombre, total, entrées, sorties."""
        groupes: dict[str, dict] = {}
        for o in ops:
            cle = cle_de(o)
            g = groupes.setdefault(cle, {"cle": cle, "libelle": cle, "nb": 0, "total": 0.0, "entrees": 0.0, "sorties": 0.0,
                                         "codes": set(), "modes": set()})
            g["nb"] += 1
            g["total"] += o["montant"]
            if not est_fond(o):
                if o["montant"] > 0:
                    g["entrees"] += o["montant"]
                else:
                    g["sorties"] += -o["montant"]
            g["codes"].add(o.get("mode_paiement_code") or "")
            g["modes"].add(o.get("mode_paiement") or "AUTRE")
        resultat = []
        for g in groupes.values():
            for k in ("total", "entrees", "sorties"):
                g[k] = _arrondi(g[k])
            codes, modes = g.pop("codes"), g.pop("modes")
            if avec_detail:
                g["codes"] = sorted(c for c in codes if c)  # codes TypePaiementCaisse d'origine
                g["modes"] = sorted(modes)  # modes normalisés (indicatifs)
            resultat.append(g)
        return sorted(resultat, key=lambda g: (-abs(g["total"]), g["libelle"]))

    par_type = ventiler(lambda o: o.get("type") or "AUTRE")
    for g in par_type:
        g["type"], g["libelle"] = g["cle"], LIBELLES_TYPE.get(g["cle"], g["cle"])
    return {
        "nb_operations": len(ops),
        "total_encaisse": _arrondi(encaisse),
        "total_sorties": _arrondi(sorties),
        "fond_de_caisse": _arrondi(fond),
        "solde_net": _arrondi(encaisse - sorties),
        "par_type": par_type,
        # Ventilation sur le LIBELLÉ D'ORIGINE d'Aizenta (le mode normalisé n'est qu'indicatif)
        "par_mode": ventiler(lambda o: o.get("mode_libelle") or "Autre", avec_detail=True),
        "par_caissier": ventiler(lambda o: o.get("caissier") or "(non renseigné)"),
    }


async def derniere_reception(boutique_id: str) -> Optional[dict]:
    lignes = await db.caisse_receptions.find({"boutique_id": boutique_id, "resultat": "ACCEPTEE"}, SANS_ID) \
        .sort("date", -1).limit(1).to_list(1)
    return lignes[0] if lignes else None


async def situation(boutique_id: str, du: str, au: str) -> dict:
    ops, _ = await operations_periode(boutique_id, du, au)
    arrets = await db.caisse_arrets.find({"boutique_id": boutique_id, "jour": {"$gte": du, "$lte": au}},
                                         SANS_ID).sort("date_heure", 1).to_list(None)
    derniere = await derniere_reception(boutique_id)
    alerte = True
    if derniere:
        alerte = datetime.fromisoformat(derniere["date"]) < datetime.now(timezone.utc) - timedelta(hours=24)
    return {
        "periode": {"du": du, "au": au},
        **calculer_situation(ops),
        "arrets_caisse": [{k: a.get(k) for k in ("id_aizenta", "date_heure", "caissier", "montant_theorique",
                                                 "montant_compte", "ecart")} for a in arrets],
        "derniere_reception": {k: derniere.get(k) for k in ("date", "nb_operations", "periode", "base")} if derniere else None,
        # Aucune réception depuis plus de 24 h (ou jamais) : Loois est peut-être arrêté
        "alerte_reception": alerte,
        "jeton_configure": bool(await db.caisse_jetons.find_one({"boutique_id": boutique_id}, {"_id": 0, "apercu": 1})),
        "a_des_donnees": bool(await db.caisse_operations.find_one({"boutique_id": boutique_id}, {"_id": 0, "jour": 1})),
    }


def filtrer(ops: list[dict], type_: str = "", mode: str = "", caissier: str = "", q: str = "") -> list[dict]:
    """Filtres de la liste détaillée (type, libellé du mode, caissier, recherche libre)."""
    q = (q or "").strip().lower()
    resultat = []
    for o in ops:
        if type_ and o.get("type") != type_:
            continue
        if mode and o.get("mode_libelle") != mode:
            continue
        if caissier and (o.get("caissier") or "(non renseigné)") != caissier:
            continue
        if q and not any(q in str(o.get(c) or "").lower()
                         for c in ("id_aizenta", "reference", "libelle", "observation", "code_client", "caissier")):
            continue
        resultat.append(o)
    return resultat


COLONNES_CSV = [("date_heure", "Date et heure"), ("id_aizenta", "N° Aizenta"), ("type_libelle", "Type"),
                ("mode_libelle", "Mode de paiement"), ("mode_paiement_code", "Code mode"), ("mode_paiement", "Mode normalisé"),
                ("montant", "Montant (FCFA)"), ("caissier", "Caissier"), ("poste", "Poste"), ("reference", "Référence"),
                ("libelle", "Libellé"), ("observation", "Observation"), ("code_client", "Code client"),
                ("cheque_numero", "N° chèque"), ("cheque_echeance", "Échéance chèque")]


def exporter_csv(ops: list[dict]) -> str:
    """CSV « à la française » (séparateur ;) lisible directement par Excel."""
    sortie = io.StringIO()
    ecrivain = csv.writer(sortie, delimiter=";")
    ecrivain.writerow([titre for _, titre in COLONNES_CSV])
    for o in ops:
        cheque = o.get("cheque") or {}
        ligne = {**o, "cheque_numero": cheque.get("numero", ""), "cheque_echeance": cheque.get("echeance") or ""}
        valeurs = []
        for colonne, _ in COLONNES_CSV:
            valeur = ligne.get(colonne)
            if colonne == "montant":
                valeur = str(_arrondi(valeur or 0)).replace(".", ",")  # virgule décimale (Excel français)
            valeurs.append("" if valeur is None else valeur)
        ecrivain.writerow(valeurs)
    return "﻿" + sortie.getvalue()  # BOM : accents corrects dans Excel


async def journaliser_reception(**champs) -> str:
    """Trace d'un appel du webhook (accepté ou refusé), consultable par le super-admin."""
    ligne = {"id": new_id(), "date": now_iso(), **champs}
    if "erreurs" in ligne:
        ligne["erreurs"] = [str(e)[:300] for e in ligne["erreurs"][:25]]
    await db.caisse_receptions.insert_one(ligne.copy())
    return ligne["id"]
