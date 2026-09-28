"""Petits utilitaires partagés : dates, identifiants, téléphone, arrondis,
montant en toutes lettres (factures)."""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal


def now_iso() -> str:
    """Date et heure actuelles (UTC = heure de Ouagadougou), format ISO."""
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    """Date du jour au format AAAA-MM-JJ."""
    return date.today().isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def normaliser_telephone(tel: str | None) -> str:
    """Garde uniquement les chiffres et le + initial : « 70 12-34 56 » -> « 70123456 »."""
    tel = (tel or "").strip()
    return ("+" if tel.startswith("+") else "") + re.sub(r"\D", "", tel)


def slugifier(texte: str) -> str:
    """« Boutique Étoile & Fils » -> « boutique-etoile-fils » (pour les adresses web)."""
    texte = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    texte = re.sub(r"[^a-zA-Z0-9]+", "-", texte).strip("-").lower()
    return texte or "element"


def arrondi(valeur) -> int:
    """Arrondi à l'unité, au plus proche (le FCFA n'a pas de centimes)."""
    return int(Decimal(str(valeur)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Montant en toutes lettres (« Arrêtée la présente facture à la somme de… »)
# ---------------------------------------------------------------------------
_UNITES = [
    "zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
    "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
    "dix-sept", "dix-huit", "dix-neuf",
]
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _moins_de_100(n: int) -> str:
    """0 à 99, avec les cas français 70-79 et 90-99."""
    if n < 20:
        return _UNITES[n]
    dizaine, unite = divmod(n, 10)
    if dizaine in (7, 9):
        base = "soixante" if dizaine == 7 else "quatre-vingt"
        liaison = " et " if (dizaine == 7 and unite == 1) else "-"
        return f"{base}{liaison}{_UNITES[10 + unite]}"
    if dizaine == 8:
        return "quatre-vingts" if unite == 0 else f"quatre-vingt-{_UNITES[unite]}"
    base = _DIZAINES[dizaine]
    if unite == 0:
        return base
    if unite == 1:
        return f"{base} et un"
    return f"{base}-{_UNITES[unite]}"


def _moins_de_1000(n: int) -> str:
    centaines, reste = divmod(n, 100)
    morceaux = []
    if centaines:
        if centaines == 1:
            morceaux.append("cent")
        else:
            # « deux cents » prend un s seulement s'il n'y a rien derrière
            morceaux.append(f"{_UNITES[centaines]} cent{'s' if reste == 0 else ''}")
    if reste or not centaines:
        morceaux.append(_moins_de_100(reste))
    return " ".join(morceaux)


def nombre_en_lettres(n: int) -> str:
    """1 250 500 -> « un million deux cent cinquante mille cinq cents »."""
    n = int(n)
    if n == 0:
        return "zéro"
    morceaux = []
    for valeur, singulier, pluriel in ((1_000_000_000, "milliard", "milliards"), (1_000_000, "million", "millions")):
        bloc, n = divmod(n, valeur)
        if bloc:
            morceaux.append(f"{nombre_en_lettres(bloc)} {singulier if bloc == 1 else pluriel}")
    milliers, n = divmod(n, 1000)
    if milliers:
        if milliers == 1:
            morceaux.append("mille")  # on ne dit pas « un mille »
        else:
            texte = _moins_de_1000(milliers)
            # Devant « mille », « cents » et « quatre-vingts » perdent leur s
            if texte.endswith(("cents", "vingts")):
                texte = texte[:-1]
            morceaux.append(f"{texte} mille")
    if n:
        morceaux.append(_moins_de_1000(n))
    return " ".join(morceaux)


def montant_en_lettres(montant, devise: str = "FCFA") -> str:
    texte = nombre_en_lettres(arrondi(montant))
    return f"{texte[0].upper()}{texte[1:]} {devise}"


# Majuscules incluses : on ne dépend pas de la gestion des accents par l'option "i"
_VARIANTES = {"a": "aàâäAÀÂÄ", "c": "cçCÇ", "e": "eéèêëEÉÈÊË", "i": "iîïIÎÏ", "o": "oôöOÔÖ", "u": "uùûüUÙÛÜ", "y": "yÿYŸ"}


def motif_recherche(texte: str) -> str:
    """Expression de recherche qui ignore les accents : « ecran » trouve « Écran »
    (et inversement). À utiliser avec l'option "i" (sans majuscules)."""
    sans = unicodedata.normalize("NFKD", texte.strip().lower()).encode("ascii", "ignore").decode()
    morceaux = []
    for car in sans:
        if car in _VARIANTES:
            morceaux.append(f"[{_VARIANTES[car]}]")
        else:
            morceaux.append(re.escape(car))
    return "".join(morceaux)
