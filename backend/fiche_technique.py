"""Fiche technique STRUCTURÉE d'un téléphone créé par une boutique.

Champs normalisés (au lieu d'un texte libre) pour que chaque boutique décrive
ses téléphones de la même façon : fabricant, modèle, système, batterie,
écran, mémoire, réseau, options, couleur, état... Ces informations restent
PRIVÉES à la boutique (jamais copiées dans le catalogue public) ; elles sont
affichées sur SA vitrine.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SYSTEMES = ("Android", "iOS", "HarmonyOS", "KaiOS", "Autre")
RESEAUX = ("2G", "3G", "4G", "5G")
ETATS = {"NEUF": "Neuf", "RECONDITIONNE": "Reconditionné", "OCCASION": "Occasion"}
# Options proposées sous forme de cases à cocher (d'autres peuvent être saisies librement)
OPTIONS = ("Double SIM", "eSIM", "NFC", "Charge rapide", "Charge sans fil", "Lecteur d'empreintes",
           "Reconnaissance faciale", "Carte mémoire", "Prise jack 3,5 mm", "Radio FM", "Résistant à l'eau",
           "Torche", "Double appareil photo", "Stylet")


class FicheTechnique(BaseModel):
    fabricant: str = Field("", max_length=80)
    modele: str = Field("", max_length=80)          # code ou nom du modèle (ex. SM-A155F)
    systeme: Optional[Literal["Android", "iOS", "HarmonyOS", "KaiOS", "Autre"]] = None
    version_systeme: str = Field("", max_length=40)  # ex. Android 14
    batterie_mah: Optional[int] = Field(None, ge=100, le=30000)
    ecran_pouces: Optional[float] = Field(None, ge=1, le=20)
    stockage_go: Optional[int] = Field(None, ge=0, le=4096)
    ram_go: Optional[float] = Field(None, ge=0, le=64)
    appareil_photo: str = Field("", max_length=80)  # ex. 50 Mpx + 5 Mpx
    reseau: Optional[Literal["2G", "3G", "4G", "5G"]] = None
    options: list[str] = Field(default_factory=list, max_length=30)
    couleur: str = Field("", max_length=40)
    etat: Literal["NEUF", "RECONDITIONNE", "OCCASION"] = "NEUF"
    annee_sortie: Optional[int] = Field(None, ge=1990, le=2100)


def _nombre(v) -> str:
    """6.5 -> « 6,5 » ; 8.0 -> « 8 » (écriture française)."""
    return f"{v:g}".replace(".", ",")


def lignes(fiche: Optional[dict], garantie_mois: int = 0) -> list[str]:
    """Fiche -> lignes « Libellé : valeur » affichées aux clients (vides ignorées)."""
    if not fiche:
        return []
    f = fiche
    systeme = " ".join(x for x in (f.get("systeme") or "", f.get("version_systeme") or "") if x).strip()
    valeurs = [
        ("Fabricant", f.get("fabricant")),
        ("Modèle", f.get("modele")),
        ("Système", systeme),
        ("Écran", f"{_nombre(f['ecran_pouces'])} pouces" if f.get("ecran_pouces") else ""),
        ("Stockage", f"{f['stockage_go']} Go" if f.get("stockage_go") else ""),
        ("Mémoire vive", f"{_nombre(f['ram_go'])} Go" if f.get("ram_go") else ""),
        ("Batterie", f"{f['batterie_mah']} mAh" if f.get("batterie_mah") else ""),
        ("Appareil photo", f.get("appareil_photo")),
        ("Réseau", f.get("reseau")),
        ("Options", ", ".join(f.get("options") or [])),
        ("Couleur", f.get("couleur")),
        ("État", ETATS.get(f.get("etat") or "", "") if f.get("etat") != "NEUF" else "Neuf"),
        ("Année de sortie", str(f["annee_sortie"]) if f.get("annee_sortie") else ""),
        ("Garantie", f"{garantie_mois} mois" if garantie_mois else ""),
    ]
    return [f"{libelle} : {valeur}" for libelle, valeur in valeurs if valeur]
