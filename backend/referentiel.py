"""Référentiel MONDIAL des appareils (liste de tous les modèles existants).

Sources :
  - Google : liste officielle des appareils Android certifiés Google Play
    (https://storage.googleapis.com/play_public/supported_devices.csv, la même
    que celle de la Play Console), environ 50 000 lignes : marque, nom
    commercial, nom de code, code modèle ;
  - Apple : liste des iPhone (Apple ne publie pas de fichier équivalent).

Le référentiel donne l'IDENTITÉ des appareils (marque, nom, codes modèle),
pas leurs caractéristiques. Une fiche détaillée (caractéristiques, photo,
pièces détachées) est créée à la demande dans le catalogue public, avec
l'assistant de recherche, puis publiée à 23h.
"""
from __future__ import annotations

import csv
import io
from typing import Optional

import httpx

from db import SANS_ID, db
from utils import now_iso, slugifier

URL_GOOGLE_PLAY = "https://storage.googleapis.com/play_public/supported_devices.csv"

# Marques écrites de plusieurs façons dans la liste Google -> nom retenu
MARQUES_UNIFIEES = {
    "samsung": "Samsung", "xiaomi": "Xiaomi", "redmi": "Xiaomi", "poco": "Xiaomi", "tecno": "Tecno",
    "tecno mobile": "Tecno", "infinix": "Infinix", "itel": "itel", "google": "Google", "nokia": "Nokia",
    "hmd global": "Nokia", "huawei": "Huawei", "honor": "Honor", "oppo": "Oppo", "vivo": "vivo",
    "realme": "realme", "motorola": "Motorola", "lenovo": "Lenovo", "oneplus": "OnePlus", "sony": "Sony",
    "lg": "LG", "alcatel": "Alcatel", "tcl": "TCL", "zte": "ZTE", "asus": "Asus", "wiko": "Wiko",
}

# iPhone (Apple ne fournit pas de liste téléchargeable) : nom commercial et année de sortie
IPHONES = [
    ("iPhone", 2007), ("iPhone 3G", 2008), ("iPhone 3GS", 2009), ("iPhone 4", 2010), ("iPhone 4S", 2011),
    ("iPhone 5", 2012), ("iPhone 5c", 2013), ("iPhone 5s", 2013), ("iPhone 6", 2014), ("iPhone 6 Plus", 2014),
    ("iPhone 6s", 2015), ("iPhone 6s Plus", 2015), ("iPhone SE (1re génération)", 2016), ("iPhone 7", 2016),
    ("iPhone 7 Plus", 2016), ("iPhone 8", 2017), ("iPhone 8 Plus", 2017), ("iPhone X", 2017), ("iPhone XR", 2018),
    ("iPhone XS", 2018), ("iPhone XS Max", 2018), ("iPhone 11", 2019), ("iPhone 11 Pro", 2019),
    ("iPhone 11 Pro Max", 2019), ("iPhone SE (2e génération)", 2020), ("iPhone 12 mini", 2020), ("iPhone 12", 2020),
    ("iPhone 12 Pro", 2020), ("iPhone 12 Pro Max", 2020), ("iPhone 13 mini", 2021), ("iPhone 13", 2021),
    ("iPhone 13 Pro", 2021), ("iPhone 13 Pro Max", 2021), ("iPhone SE (3e génération)", 2022), ("iPhone 14", 2022),
    ("iPhone 14 Plus", 2022), ("iPhone 14 Pro", 2022), ("iPhone 14 Pro Max", 2022), ("iPhone 15", 2023),
    ("iPhone 15 Plus", 2023), ("iPhone 15 Pro", 2023), ("iPhone 15 Pro Max", 2023), ("iPhone 16", 2024),
    ("iPhone 16 Plus", 2024), ("iPhone 16 Pro", 2024), ("iPhone 16 Pro Max", 2024), ("iPhone 16e", 2025),
    ("iPhone 17", 2025), ("iPhone Air", 2025), ("iPhone 17 Pro", 2025), ("iPhone 17 Pro Max", 2025),
]


def _marque(brut: str) -> str:
    brut = (brut or "").strip()
    return MARQUES_UNIFIEES.get(brut.lower(), brut)


def lire_liste_google(contenu: bytes) -> dict[str, dict]:
    """Fichier Google (UTF-16) -> appareils regroupés par marque + nom commercial.
    Une même référence commerciale a souvent plusieurs codes modèle (variantes
    régionales) : ils sont regroupés sur une seule ligne."""
    texte = contenu.decode("utf-16")
    appareils: dict[str, dict] = {}
    for ligne in csv.DictReader(io.StringIO(texte)):
        marque = _marque(ligne.get("Retail Branding", ""))
        nom = (ligne.get("Marketing Name") or "").strip()
        modele = (ligne.get("Model") or "").strip()
        code = (ligne.get("Device") or "").strip()
        if not marque or not (nom or modele):
            continue  # lignes sans marque : inexploitables
        nom = nom or modele
        # Le nom commercial répète souvent la marque : « Samsung Galaxy A15 » -> « Galaxy A15 »
        brut = (ligne.get("Retail Branding") or "").strip()
        for prefixe in (marque, brut):
            if prefixe and nom.lower().startswith(prefixe.lower() + " "):
                nom = nom[len(prefixe) + 1:]
        # « TECNO Mobile SPARK 20 » -> « SPARK 20 »
        if nom.lower().startswith("mobile "):
            nom = nom[7:]
        nom = nom.strip() or modele
        cle = slugifier(f"{marque}-{nom}")
        entree = appareils.setdefault(cle, {"cle": cle, "marque": marque, "nom": nom, "codes_modele": [], "noms_code": []})
        if modele and modele not in entree["codes_modele"] and len(entree["codes_modele"]) < 50:
            entree["codes_modele"].append(modele)
        if code and code not in entree["noms_code"] and len(entree["noms_code"]) < 50:
            entree["noms_code"].append(code)
    return appareils


async def enregistrer(appareils: dict[str, dict], source: str) -> dict:
    """Ajoute les nouveaux appareils et complète les codes des existants
    (jamais de suppression : un appareil retiré d'une liste reste connu).
    Traitement groupé : quelques requêtes pour des dizaines de milliers de lignes."""
    # Lecture de tout le référentiel existant en une passe (quelques Mo), plus
    # rapide qu'une recherche « $in » sur des dizaines de milliers de clés
    existants = {d["cle"]: d async for d in db.referentiel_appareils.find(
        {}, {"_id": 0, "cle": 1, "codes_modele": 1, "noms_code": 1, "sources": 1})}
    a_inserer, maj = [], 0
    for cle, a in appareils.items():
        actuel = existants.get(cle)
        if actuel is None:
            a_inserer.append({**a, "id": cle, "sources": [source], "annee_sortie": a.get("annee_sortie"),
                              "catalogue_id": None, "date_ajout": now_iso(), "date_maj": now_iso()})
            continue
        codes = [c for c in a["codes_modele"] if c not in actuel.get("codes_modele", [])]
        noms = [c for c in a["noms_code"] if c not in actuel.get("noms_code", [])]
        if codes or noms or source not in actuel.get("sources", []):
            await db.referentiel_appareils.update_one({"cle": cle}, {
                "$push": {"codes_modele": {"$each": codes}, "noms_code": {"$each": noms}},
                "$addToSet": {"sources": source}, "$set": {"date_maj": now_iso()}})
            maj += 1
    for debut in range(0, len(a_inserer), 1000):
        await db.referentiel_appareils.insert_many([dict(x) for x in a_inserer[debut:debut + 1000]])
    return {"nouveaux": len(a_inserer), "mis_a_jour": maj}


async def importer(contenu_google: Optional[bytes] = None) -> dict:
    """Import complet : liste Google Play (téléchargée si non fournie) + iPhone."""
    if contenu_google is None:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            r = await client.get(URL_GOOGLE_PLAY)
            r.raise_for_status()
            contenu_google = r.content
    google = await enregistrer(lire_liste_google(contenu_google), "Google Play")
    apple = await enregistrer({slugifier(f"Apple-{nom}"): {"cle": slugifier(f"Apple-{nom}"), "marque": "Apple", "nom": nom,
                                                          "annee_sortie": annee, "codes_modele": [], "noms_code": []}
                               for nom, annee in IPHONES}, "Apple")
    rapport = {"date": now_iso(), "google": google, "apple": apple,
               "total": await db.referentiel_appareils.count_documents({})}
    await db.referentiel_imports.insert_one(dict(rapport))
    return rapport


async def lier_fiche(cle: str, catalogue_id: str) -> None:
    """Relie un appareil du référentiel à sa fiche détaillée du catalogue public."""
    await db.referentiel_appareils.update_one({"cle": cle}, {"$set": {"catalogue_id": catalogue_id}})


async def dernier_import() -> Optional[dict]:
    derniers = await db.referentiel_imports.find({}, SANS_ID).sort("date", -1).to_list(1)
    return derniers[0] if derniers else None
