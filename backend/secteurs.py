"""SECTEURS D'ACTIVITÉ (lot A) : adLyn devient une plateforme pour TOUT type de commerce.

Un secteur (télécom, prêt-à-porter, cosmétiques, quincaillerie…) est un référentiel
GLOBAL (collection `tlb_secteurs`), paramétrable par le super-administrateur. Il décrit :
  - `code`, `libelle`, `icone` (pictogramme du menu « Catalogue »), `actif`, `ordre` ;
  - `vocabulaire` : les mots affichés dans l'interface du commerçant
    (« Article » au lieu de « Produit », « Rayon » au lieu de « Catégorie »…) ;
  - `champs` : les caractéristiques propres au secteur, saisies sur chaque fiche
    article et enregistrées dans `produit.attributs = {cle: valeur}` ;
  - `modules` : options de la barre latérale (options_sidebar.py) activées
    d'office à la création d'une boutique de ce secteur ;
  - `categories_depart` : catégories créées pour une nouvelle boutique ;
  - `catalogue_telecom` : vrai seulement pour le télécom (copie du catalogue public
    de téléphones, référentiel mondial des appareils, fiche technique du téléphone).

Chaque boutique porte `secteur` (code, « telecom » par défaut) et
`secteurs_secondaires` (liste prévue pour plus tard, non exposée à l'écran).

Lecture rapide : les secteurs sont gardés EN MÉMOIRE (cache relu au plus toutes les
60 secondes, et aussitôt après chaque modification), pour que l'envoi de la boutique
au navigateur (_sans_secrets, fonction non asynchrone) puisse y ajouter le
vocabulaire sans relire la base. Si un secteur manque en base, sa définition
d'origine (SECTEURS_PAR_DEFAUT) sert de repli : l'interface ne casse jamais.
"""
from __future__ import annotations

import copy
import time
from datetime import date
from typing import Any, Optional

from fastapi import HTTPException

from db import SANS_ID, db
from utils import now_iso

# Code du secteur par défaut : toutes les boutiques créées avant ce lot sont des boutiques télécom
SECTEUR_DEFAUT = "telecom"

# Types de champ autorisés pour les caractéristiques d'un secteur
TYPES_CHAMP = ("texte", "nombre", "date", "liste", "multi_liste")

# Marqueur de la migration « toutes les boutiques existantes -> télécom » (une seule fois)
MIGRATION_TELECOM = "secteur_telecom_v1"

# ---------------------------------------------------------------------------
# Vocabulaire : termes ACTUELS de l'interface (repli quand un secteur ne précise rien)
# ---------------------------------------------------------------------------
VOCABULAIRE_DEFAUT: dict[str, str] = {
    "article": "Produit",               # un élément vendu
    "articles": "Produits",             # pluriel
    "nouvel_article": "Nouveau produit",  # bouton de création
    "categorie": "Catégorie",           # classement des articles
    "categories": "Catégories",
    "catalogue": "Catalogue",           # entrée du menu et titre de la liste
    "stock": "Stock",
    "caracteristiques": "Caractéristiques",  # titre de la section des champs du secteur
}

# Modules « génériques » activés d'office pour un commerce non télécom
# (le SAV / réparation avec IMEI et le catalogue public de téléphones en sont exclus)
_MODULES_COMMERCE = ["produits", "stock", "clients", "documents", "paiements", "fournisseurs",
                     "parametres", "abonnement"]

# Pointures proposées avec les tailles du prêt-à-porter
_POINTURES = [str(p) for p in range(35, 47)]


def _champ(cle: str, libelle: str, type_: str = "texte", options: Optional[list[str]] = None,
           obligatoire: bool = False) -> dict:
    """Raccourci de déclaration d'un champ de secteur."""
    return {"cle": cle, "libelle": libelle, "type": type_, "options": options or [], "obligatoire": obligatoire}


# ---------------------------------------------------------------------------
# Secteurs créés au premier démarrage (collection vide). Le super-administrateur
# les modifie ensuite depuis « Plateforme > Secteurs d'activité ».
# ---------------------------------------------------------------------------
SECTEURS_PAR_DEFAUT: list[dict] = [
    {
        "code": "telecom", "libelle": "Télécom (téléphonie et accessoires)", "icone": "📱", "ordre": 1,
        # Vocabulaire actuel, fiche technique du téléphone inchangée (aucun champ en plus)
        "vocabulaire": {}, "champs": [],
        # Aucun module en plus des deux obligatoires : comportement d'avant ce lot
        # (le super-admin active les options boutique par boutique)
        "modules": [],
        # Les rayons (Smartphones, Accessoires…) sont créés par la copie du catalogue public
        "categories_depart": [],
        "catalogue_telecom": True,
    },
    {
        "code": "pret_a_porter", "libelle": "Prêt-à-porter / Vêtements et chaussures", "icone": "👗", "ordre": 2,
        "vocabulaire": {"article": "Article", "articles": "Articles", "nouvel_article": "Nouvel article",
                        "categorie": "Rayon", "categories": "Rayons", "catalogue": "Catalogue",
                        "caracteristiques": "Caractéristiques"},
        "champs": [
            _champ("taille", "Taille / pointure", "liste", ["XS", "S", "M", "L", "XL", "XXL", "XXXL", *_POINTURES, "Taille unique"]),
            _champ("couleur", "Couleur"),
            _champ("matiere", "Matière"),
            _champ("genre", "Genre", "liste", ["Femme", "Homme", "Enfant", "Mixte"]),
            _champ("saison", "Saison", "liste", ["Toutes saisons", "Saison sèche", "Saison des pluies", "Été", "Hiver"]),
        ],
        "modules": list(_MODULES_COMMERCE),
        "categories_depart": ["Femme", "Homme", "Enfant", "Chaussures", "Accessoires de mode"],
        "catalogue_telecom": False,
    },
    {
        "code": "cosmetiques", "libelle": "Cosmétiques et beauté", "icone": "💄", "ordre": 3,
        "vocabulaire": {"categorie": "Rayon", "categories": "Rayons"},
        "champs": [
            _champ("contenance", "Contenance (ex. 50 ml)"),
            _champ("numero_lot", "Numéro de lot"),
            _champ("date_peremption", "Date de péremption", "date"),
            _champ("type_peau", "Type de peau", "liste", ["Tous types", "Sèche", "Grasse", "Mixte", "Sensible"]),
        ],
        "modules": list(_MODULES_COMMERCE),
        "categories_depart": ["Soins du visage", "Soins du corps", "Cheveux", "Maquillage", "Parfums"],
        "catalogue_telecom": False,
    },
    {
        "code": "quincaillerie", "libelle": "Quincaillerie / Matériaux", "icone": "🔧", "ordre": 4,
        "vocabulaire": {"article": "Article", "articles": "Articles", "nouvel_article": "Nouvel article",
                        "categorie": "Famille", "categories": "Familles"},
        "champs": [
            _champ("unite_vente", "Unité de vente", "liste",
                   ["Pièce", "Mètre", "Mètre carré", "Kilogramme", "Litre", "Sac", "Boîte", "Rouleau", "Paquet"]),
            _champ("dimensions", "Dimensions"),
            _champ("materiau", "Matériau"),
            _champ("conditionnement", "Conditionnement"),
        ],
        "modules": list(_MODULES_COMMERCE),
        "categories_depart": ["Outillage", "Plomberie", "Électricité", "Peinture", "Matériaux de construction", "Visserie"],
        "catalogue_telecom": False,
    },
    {
        "code": "alimentation", "libelle": "Alimentation / Supérette", "icone": "🛒", "ordre": 5,
        "vocabulaire": {"article": "Article", "articles": "Articles", "nouvel_article": "Nouvel article",
                        "categorie": "Rayon", "categories": "Rayons"},
        "champs": [
            _champ("numero_lot", "Numéro de lot"),
            _champ("date_peremption", "Date de péremption", "date"),
            _champ("poids_volume", "Poids / volume"),
        ],
        "modules": list(_MODULES_COMMERCE),
        "categories_depart": ["Épicerie", "Boissons", "Produits frais", "Hygiène et entretien"],
        "catalogue_telecom": False,
    },
    {
        "code": "pharmacie", "libelle": "Pharmacie / Parapharmacie", "icone": "💊", "ordre": 6,
        "vocabulaire": {"categorie": "Famille", "categories": "Familles"},
        "champs": [
            _champ("numero_lot", "Numéro de lot"),
            _champ("date_peremption", "Date de péremption", "date"),
            _champ("forme", "Forme", "liste", ["Comprimé", "Gélule", "Sirop", "Pommade", "Crème", "Injectable",
                                               "Sachet", "Gouttes", "Autre"]),
            _champ("dosage", "Dosage"),
        ],
        "modules": list(_MODULES_COMMERCE),
        "categories_depart": ["Médicaments", "Parapharmacie", "Hygiène", "Matériel médical"],
        "catalogue_telecom": False,
    },
    {
        "code": "electromenager", "libelle": "Électroménager / Électronique", "icone": "🔌", "ordre": 7,
        "vocabulaire": {"article": "Article", "articles": "Articles", "nouvel_article": "Nouvel article",
                        "categorie": "Rayon", "categories": "Rayons"},
        # La marque et la garantie (en mois) sont déjà des champs de toute fiche article
        "champs": [
            _champ("modele", "Modèle"),
            _champ("numero_serie", "Numéro de série"),
        ],
        "modules": list(_MODULES_COMMERCE),
        "categories_depart": ["Gros électroménager", "Petit électroménager", "TV et audio", "Informatique"],
        "catalogue_telecom": False,
    },
    {
        "code": "librairie", "libelle": "Librairie / Papeterie", "icone": "📚", "ordre": 8,
        "vocabulaire": {"article": "Article", "articles": "Articles", "nouvel_article": "Nouvel article",
                        "categorie": "Rayon", "categories": "Rayons"},
        "champs": [
            _champ("auteur", "Auteur"),
            _champ("editeur", "Éditeur"),
            _champ("isbn", "ISBN"),
        ],
        "modules": list(_MODULES_COMMERCE),
        "categories_depart": ["Livres", "Scolaire", "Papeterie", "Fournitures de bureau"],
        "catalogue_telecom": False,
    },
    {
        "code": "autre", "libelle": "Autre commerce", "icone": "🏪", "ordre": 99,
        "vocabulaire": {"article": "Article", "articles": "Articles", "nouvel_article": "Nouvel article"},
        "champs": [],
        "modules": list(_MODULES_COMMERCE),
        "categories_depart": ["Général"],
        "catalogue_telecom": False,
    },
]
_DEFAUTS_PAR_CODE = {s["code"]: s for s in SECTEURS_PAR_DEFAUT}

# ---------------------------------------------------------------------------
# Cache mémoire des secteurs (code -> fiche), relu au plus toutes les 60 s
# ---------------------------------------------------------------------------
_CACHE: dict[str, Any] = {"secteurs": {}, "lu_le": 0.0}
DUREE_CACHE = 60  # secondes


def normaliser(secteur: dict) -> dict:
    """Fiche complète d'un secteur : tous les champs présents, sans « _id »."""
    s = {k: v for k, v in (secteur or {}).items() if k != "_id"}
    s.setdefault("libelle", s.get("code", ""))
    s.setdefault("icone", "🏪")
    s.setdefault("actif", True)
    s.setdefault("ordre", 50)
    s["vocabulaire"] = dict(s.get("vocabulaire") or {})
    s["champs"] = list(s.get("champs") or [])
    s["modules"] = list(s.get("modules") or [])
    s["categories_depart"] = list(s.get("categories_depart") or [])
    s["catalogue_telecom"] = bool(s.get("catalogue_telecom"))
    return s


async def rafraichir_cache(force: bool = False) -> None:
    """Relit les secteurs en base si le cache a plus de 60 s (ou tout de suite si force=True)."""
    if not force and time.monotonic() - _CACHE["lu_le"] < DUREE_CACHE and _CACHE["secteurs"]:
        return
    liste = await db.secteurs.find({}, SANS_ID).to_list(500)
    _CACHE["secteurs"] = {s["code"]: normaliser(s) for s in liste if s.get("code")}
    _CACHE["lu_le"] = time.monotonic()


def secteur_en_cache(code: Optional[str]) -> dict:
    """Fiche d'un secteur (lecture sans base de données) : cache, sinon définition
    d'origine, sinon le télécom. Ne renvoie jamais None."""
    code = code or SECTEUR_DEFAUT
    trouve = _CACHE["secteurs"].get(code) or _DEFAUTS_PAR_CODE.get(code)
    if not trouve:
        trouve = _CACHE["secteurs"].get(SECTEUR_DEFAUT) or _DEFAUTS_PAR_CODE[SECTEUR_DEFAUT]
    return normaliser(copy.deepcopy(trouve))


async def lire_secteur(code: Optional[str]) -> dict:
    """Fiche d'un secteur lue EN BASE (création de boutique, validation des articles)."""
    code = code or SECTEUR_DEFAUT
    trouve = await db.secteurs.find_one({"code": code}, SANS_ID)
    if trouve:
        return normaliser(trouve)
    return secteur_en_cache(code)


def code_de_boutique(boutique: Optional[dict]) -> str:
    """Code du secteur principal d'une boutique (« telecom » si absent : boutique d'avant ce lot)."""
    return (boutique or {}).get("secteur") or SECTEUR_DEFAUT


def vocabulaire(secteur: dict) -> dict:
    """Vocabulaire complet : termes actuels, remplacés par ceux du secteur (valeurs non vides)."""
    propres = {k: str(v).strip() for k, v in (secteur.get("vocabulaire") or {}).items() if str(v or "").strip()}
    return {**VOCABULAIRE_DEFAUT, **propres}


def infos_boutique(boutique: Optional[dict]) -> dict:
    """Ce que le navigateur reçoit avec la boutique (/auth/me, /boutique) :
    secteur, vocabulaire, champs du secteur, pictogramme et drapeau télécom."""
    s = secteur_en_cache(code_de_boutique(boutique))
    return {
        "secteur": code_de_boutique(boutique),
        "secteur_info": {"code": s["code"], "libelle": s["libelle"], "icone": s["icone"],
                         "catalogue_telecom": s["catalogue_telecom"]},
        "vocabulaire": vocabulaire(s),
        "champs_secteur": s["champs"],
    }


# ---------------------------------------------------------------------------
# Démarrage : secteurs par défaut + migration des boutiques existantes
# ---------------------------------------------------------------------------
async def initialiser() -> None:
    """Appelé au démarrage du serveur :
      1) collection vide -> création des secteurs par défaut ;
      2) migration (une seule fois) : boutiques existantes -> secteur « telecom » ;
      3) chargement du cache."""
    if not await db.secteurs.count_documents({}):
        await db.secteurs.insert_many([{**copy.deepcopy(s), "actif": True, "created_at": now_iso()}
                                       for s in SECTEURS_PAR_DEFAUT])
    await migrer_boutiques()
    await rafraichir_cache(force=True)


async def migrer_boutiques() -> int:
    """Toutes les boutiques SANS secteur passent au télécom. Exécutée une seule fois
    (marqueur dans `tlb_migrations`) ; relancée, elle ne change rien (idempotente).
    Renvoie le nombre de boutiques modifiées."""
    if await db.migrations.find_one({"id": MIGRATION_TELECOM}, SANS_ID):
        return 0
    res = await db.boutiques.update_many({"secteur": {"$exists": False}},
                                         {"$set": {"secteur": SECTEUR_DEFAUT, "secteurs_secondaires": []}})
    await db.migrations.insert_one({"id": MIGRATION_TELECOM, "date": now_iso(), "boutiques": res.modified_count})
    return res.modified_count


async def codes_catalogue_telecom() -> list[str]:
    """Codes des secteurs qui reçoivent le catalogue public de téléphones."""
    codes = [s["code"] async for s in db.secteurs.find({"catalogue_telecom": True}, {"_id": 0, "code": 1})]
    return codes or [SECTEUR_DEFAUT]


async def filtre_boutiques_telecom() -> dict:
    """Filtre MongoDB des boutiques concernées par le catalogue public de téléphones
    (sans secteur = boutique d'avant ce lot = télécom)."""
    return {"$or": [{"secteur": {"$exists": False}}, {"secteur": None},
                    {"secteur": {"$in": await codes_catalogue_telecom()}}]}


async def code_valide(code: Optional[str]) -> str:
    """Contrôle le secteur demandé à la création d'une boutique (vide -> « telecom »)."""
    code = (code or "").strip() or SECTEUR_DEFAUT
    s = await db.secteurs.find_one({"code": code}, SANS_ID)
    if s is None and code in _DEFAUTS_PAR_CODE:
        return code  # base pas encore initialisée : définition d'origine
    if s is None:
        raise HTTPException(400, f"Secteur d'activité inconnu : {code}")
    if s.get("actif") is False:
        raise HTTPException(400, f"Secteur d'activité désactivé : {s.get('libelle') or code}")
    return code


# ---------------------------------------------------------------------------
# Champs du secteur saisis sur la fiche article : contrôle et nettoyage
# ---------------------------------------------------------------------------
def _vide(valeur: Any) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip()) or (isinstance(valeur, list) and not valeur)


def valider_attributs(champs: list[dict], attributs: Optional[dict]) -> dict:
    """Contrôle les valeurs saisies pour les champs du secteur et renvoie le
    dictionnaire nettoyé {cle: valeur} (les clés inconnues du secteur sont ignorées).
    Erreur 400 (message en français) si :
      - un champ obligatoire est vide ;
      - un nombre n'en est pas un ; une date n'est pas au format AAAA-MM-JJ ;
      - une valeur de liste n'est pas parmi les options proposées."""
    attributs = attributs or {}
    if not isinstance(attributs, dict):
        raise HTTPException(400, "Caractéristiques invalides")
    propres: dict[str, Any] = {}
    for champ in champs or []:
        cle, libelle, type_ = champ.get("cle"), champ.get("libelle") or champ.get("cle"), champ.get("type", "texte")
        valeur = attributs.get(cle)
        if _vide(valeur):
            if champ.get("obligatoire"):
                raise HTTPException(400, f"Le champ « {libelle} » est obligatoire")
            continue
        options = champ.get("options") or []
        if type_ == "nombre":
            try:
                nombre = float(str(valeur).replace(",", ".").replace(" ", ""))
            except ValueError:
                raise HTTPException(400, f"« {libelle} » doit être un nombre") from None
            valeur = int(nombre) if nombre.is_integer() else nombre
        elif type_ == "date":
            try:
                valeur = date.fromisoformat(str(valeur)[:10]).isoformat()
            except ValueError:
                raise HTTPException(400, f"« {libelle} » doit être une date (AAAA-MM-JJ)") from None
        elif type_ == "liste":
            valeur = str(valeur).strip()
            if options and valeur not in options:
                raise HTTPException(400, f"Valeur non proposée pour « {libelle} » : {valeur}")
        elif type_ == "multi_liste":
            liste = valeur if isinstance(valeur, list) else [valeur]
            liste = [str(v).strip() for v in liste if str(v).strip()]
            hors = [v for v in liste if options and v not in options]
            if hors:
                raise HTTPException(400, f"Valeur non proposée pour « {libelle} » : {', '.join(hors)}")
            if not liste:
                if champ.get("obligatoire"):
                    raise HTTPException(400, f"Le champ « {libelle} » est obligatoire")
                continue
            valeur = liste
        else:  # texte
            valeur = str(valeur).strip()[:500]
        propres[cle] = valeur
    return propres


def lignes_attributs(champs: list[dict], attributs: Optional[dict]) -> list[str]:
    """Attributs -> lignes « Libellé : valeur » (vitrine publique), dans l'ordre des champs."""
    attributs = attributs or {}
    lignes = []
    for champ in champs or []:
        valeur = attributs.get(champ.get("cle"))
        if _vide(valeur):
            continue
        if isinstance(valeur, list):
            valeur = ", ".join(str(v) for v in valeur)
        elif champ.get("type") == "date":
            try:
                valeur = date.fromisoformat(str(valeur)).strftime("%d/%m/%Y")
            except ValueError:
                pass
        elif isinstance(valeur, float):
            valeur = f"{valeur:g}".replace(".", ",")
        lignes.append(f"{champ.get('libelle') or champ.get('cle')} : {valeur}")
    return lignes
