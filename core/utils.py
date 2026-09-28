"""
Petits utilitaires partagés : montant en toutes lettres (pour les factures).
"""

import re
from decimal import Decimal

# Mots de base de la numération française
_UNITES = [
    "zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
    "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
    "dix-sept", "dix-huit", "dix-neuf",
]
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _moins_de_100(n: int) -> str:
    """Écrit un nombre de 0 à 99 (gère les cas 70-79 et 90-99 à la française)."""
    if n < 20:
        return _UNITES[n]
    dizaine, unite = divmod(n, 10)
    if dizaine in (7, 9):
        # 70 = soixante-dix, 91 = quatre-vingt-onze...
        base = "soixante" if dizaine == 7 else "quatre-vingt"
        reste = 10 + unite
        liaison = " et " if (dizaine == 7 and unite == 1) else "-"
        return f"{base}{liaison}{_UNITES[reste]}"
    if dizaine == 8:
        return "quatre-vingts" if unite == 0 else f"quatre-vingt-{_UNITES[unite]}"
    base = _DIZAINES[dizaine]
    if unite == 0:
        return base
    if unite == 1:
        return f"{base} et un"
    return f"{base}-{_UNITES[unite]}"


def _moins_de_1000(n: int) -> str:
    """Écrit un nombre de 0 à 999."""
    centaines, reste = divmod(n, 100)
    morceaux = []
    if centaines:
        if centaines == 1:
            morceaux.append("cent")
        else:
            # "deux cents" prend un s seulement s'il n'y a rien derrière
            morceaux.append(f"{_UNITES[centaines]} cent{'s' if reste == 0 else ''}")
    if reste or not centaines:
        morceaux.append(_moins_de_100(reste))
    return " ".join(morceaux)


def nombre_en_lettres(n: int) -> str:
    """
    Convertit un entier positif en toutes lettres, en français.
    Exemple : 1 250 500 -> "un million deux cent cinquante mille cinq cents"
    """
    n = int(n)
    if n == 0:
        return "zéro"
    morceaux = []
    for valeur, singulier, pluriel in (
        (1_000_000_000, "milliard", "milliards"),
        (1_000_000, "million", "millions"),
    ):
        bloc, n = divmod(n, valeur)
        if bloc:
            morceaux.append(f"{nombre_en_lettres(bloc)} {singulier if bloc == 1 else pluriel}")
    milliers, n = divmod(n, 1000)
    if milliers:
        # "mille" est invariable et on ne dit pas "un mille".
        # Devant "mille", "cents" et "quatre-vingts" perdent leur s
        # (deux cent mille, quatre-vingt mille).
        if milliers == 1:
            morceaux.append("mille")
        else:
            texte = _moins_de_1000(milliers)
            if texte.endswith(("cents", "vingts")):
                texte = texte[:-1]
            morceaux.append(f"{texte} mille")
    if n:
        morceaux.append(_moins_de_1000(n))
    return " ".join(morceaux)


def montant_en_lettres(montant, devise: str = "FCFA") -> str:
    """Montant arrondi à l'unité, en lettres, suivi de la devise (1re lettre en majuscule)."""
    texte = nombre_en_lettres(int(Decimal(montant).quantize(Decimal("1"))))
    return f"{texte[0].upper()}{texte[1:]} {devise}"


def normaliser_telephone(tel: str) -> str:
    """Garde uniquement les chiffres et le + initial : « 70 12-34 56 » -> « 70123456 »."""
    tel = (tel or "").strip()
    return ("+" if tel.startswith("+") else "") + re.sub(r"\D", "", tel)
