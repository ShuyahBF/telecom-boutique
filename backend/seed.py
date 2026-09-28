"""Données de départ : compte super-administrateur (depuis les variables
d'environnement) et, sur demande, une boutique de démonstration.

Démo en local :  python seed.py --demo
"""
from __future__ import annotations

import asyncio
import sys

from auth import hash_password, verify_password
from config import get_settings
from db import SANS_ID, TenantDB, db, ensure_indexes
from utils import new_id, now_iso, slugifier


async def ensure_super_admin() -> None:
    """Crée (ou promeut) le super-administrateur défini par SUPER_ADMIN_EMAIL."""
    s = get_settings()
    if not (s.super_admin_email and s.super_admin_password):
        return
    email = s.super_admin_email.lower().strip()
    user = await db.users.find_one({"email": email}, SANS_ID)
    if not user:
        await db.users.insert_one({"id": new_id(), "email": email, "nom": "Administrateur plateforme",
                                   "password_hash": hash_password(s.super_admin_password), "role": "super_admin",
                                   "boutique_id": None, "actif": True, "created_at": now_iso()})
        return
    maj: dict = {"role": "super_admin", "boutique_id": None, "actif": True}
    if s.super_admin_reset_password and not verify_password(s.super_admin_password, user["password_hash"]):
        maj["password_hash"] = hash_password(s.super_admin_password)
    await db.users.update_one({"id": user["id"]}, {"$set": maj})


# Catalogue public d'exemple : (clé, type, marque, nom, référence, année, caractéristiques, compatible avec)
CATALOGUE_DEMO = [
    ("A15", "TEL", "Samsung", "Galaxy A15 128 Go", "SM-A155F", 2023,
     ["Écran : 6,5 pouces Super AMOLED 90 Hz", "Stockage : 128 Go", "Mémoire vive : 4 Go", "Batterie : 5000 mAh",
      "Réseaux : 2G / 3G / 4G", "Double SIM : oui"], []),
    ("SPARK20", "TEL", "Tecno", "Spark 20 256 Go", "KJ5", 2023,
     ["Écran : 6,6 pouces 90 Hz", "Stockage : 256 Go", "Mémoire vive : 8 Go", "Batterie : 5000 mAh", "Double SIM : oui"], []),
    ("HOT40I", "TEL", "Infinix", "Hot 40i 128 Go", "X6528B", 2023,
     ["Écran : 6,56 pouces", "Stockage : 128 Go", "Batterie : 5000 mAh"], []),
    ("IPH13", "TEL", "Apple", "iPhone 13 128 Go", "A2633", 2021,
     ["Écran : 6,1 pouces Super Retina XDR", "Puce : A15 Bionic", "Stockage : 128 Go", "Réseaux : 5G"], []),
    ("N105", "TEL", "Nokia", "105 (2023)", "TA-1557", 2023, ["Double SIM : oui", "Radio FM : oui"], []),
    ("ECR-A15", "PIE", "Samsung", "Écran complet — Galaxy A15", "GH82-32909A", None, [], ["A15"]),
    ("BAT-BL49", "PIE", "Tecno", "Batterie BL-49 — Spark 20", "BL-49ST", None, ["Capacité : 5000 mAh"], ["SPARK20"]),
    ("CHG25", "ACC", "Samsung", "Chargeur rapide 25 W USB-C", "EP-TA800", None, ["Puissance : 25 W"], ["A15"]),
]
# Prix de la boutique de démo pour les modèles copiés : clé -> (prix d'achat, prix de vente, stock)
PRIX_DEMO = {"A15": (85000, 110000, 8), "SPARK20": (70000, 92000, 12), "HOT40I": (60000, 79000, 5),
             "IPH13": (330000, 395000, 2), "N105": (9000, 13500, 20), "ECR-A15": (18000, 30000, 3),
             "BAT-BL49": (4000, 8000, 6), "CHG25": (6000, 10000, 30)}


async def creer_catalogue_demo() -> dict:
    """Catalogue public d'exemple (publié), si le catalogue est encore vide."""
    from catalogue_public import publier

    references = {}
    if await db.catalogue_modeles.count_documents({}):
        async for m in db.catalogue_modeles.find({}, SANS_ID):
            references[m["reference"]] = m["id"]
    else:
        for cle, typ, marque, nom, ref, annee, carac, compat in CATALOGUE_DEMO:
            mid = new_id()
            references[ref] = mid
            await db.catalogue_modeles.insert_one({
                "id": mid, "type_produit": typ, "marque": marque, "nom": nom, "reference": ref, "annee_sortie": annee,
                "description": "", "caracteristiques": carac, "photo_url": None, "sources": [], "statut": "PRET",
                "modeles_compatibles": [references[next(r for k, _, _, _, r, *_ in CATALOGUE_DEMO if k == c)] for c in compat],
                "publie": False, "modifie_apres_publication": False, "version_publiee": 0, "date_publication": None,
                "created_at": now_iso(), "updated_at": now_iso()})
        await publier("demo")
    return {cle: references.get(ref) for cle, _, _, _, ref, *_ in CATALOGUE_DEMO}


async def creer_demo() -> None:
    """Boutique « Démo Télécom » (DG : demo@demo-telecom.bf / demo-2026!)."""
    from catalogue_public import copier_catalogue_dans_boutique
    from kyc import kyc_vide
    from routes.plateforme import boutique_par_defaut
    from services import entree_stock

    if await db.boutiques.find_one({"slug": "demo-telecom"}):
        print("La boutique de démonstration existe déjà.")
        return
    ids_catalogue = await creer_catalogue_demo()
    boutique = {"id": new_id(), "nom": "Démo Télécom", "slug": "demo-telecom", "code_marchand": "DEMO01",
                "telephone": "+22625000000", "email": "", "actif": True, "mise_en_avant": True, "ordre": 0,
                "created_at": now_iso(), **boutique_par_defaut("Démo Télécom"),
                "slogan": "Téléphones, accessoires et réparation", "pays": "Burkina Faso", "ville": "Ouagadougou",
                "adresse": "Avenue Kwame Nkrumah, Ouagadougou", "latitude": 12.3686, "longitude": -1.5275,
                "dg_nom": "DG Démo", "ifu": "00012345A", "cnss": "123456", "rccm": "BF-OUA-2026-B-0001",
                "kyc": kyc_vide()}
    await db.boutiques.insert_one(boutique.copy())
    await db.users.insert_one({"id": new_id(), "email": "demo@demo-telecom.bf", "nom": "DG Démo",
                               "password_hash": hash_password("demo-2026!"), "role": "dg",
                               "boutique_id": boutique["id"], "actif": True, "created_at": now_iso()})
    # Première initialisation : copie du catalogue public, puis prix et stock de la boutique
    await copier_catalogue_dans_boutique(boutique["id"])
    tdb = TenantDB(boutique["id"])
    for cle, (pa, pv, stock) in PRIX_DEMO.items():
        produit = await tdb.produits.find_one({"catalogue_id": ids_catalogue.get(cle)})
        if not produit:
            continue
        await tdb.produits.update_one({"id": produit["id"]}, {"$set": {
            "prix_achat": pa, "prix_vente": pv, "visible_portail": produit["type_produit"] in ("TEL", "ACC")}})
        await entree_stock(tdb, produit, stock, "INVENT", "", "Stock initial (démo)")
    # Produits propres à la boutique (non partagés)
    categorie = await tdb.categories.find_one({"nom": "Accessoires"}) or {"id": new_id(), "nom": "Accessoires"}
    services = {"id": new_id(), "nom": "Services", "slug": "services", "ordre": 9}
    await tdb.categories.insert_one(services)
    for ref, nom, typ, cat, pa, pv, stock in (("ACC-VERRE", "Verre trempé universel", "ACC", categorie, 300, 1500, 60),
                                              ("SER-MO", "Main d'œuvre réparation", "SER", services, 0, 5000, 0)):
        produit = {"id": new_id(), "reference": ref, "nom": nom, "slug": slugifier(f"{nom}-{ref}"), "type_produit": typ,
                   "categorie_id": cat["id"], "categorie_nom": cat["nom"], "marque": "", "description": "",
                   "caracteristiques": [], "image_url": None, "image_source": "boutique", "prix_achat": pa,
                   "prix_vente": pv, "stock": 0, "stock_alerte": 2, "garantie_mois": 0,
                   "visible_portail": typ == "ACC", "actif": True, "catalogue_id": None, "source": "boutique",
                   "nouveau": False, "documents": [], "modeles_compatibles": [], "conseils_utilisation": "",
                   "created_at": now_iso()}
        await tdb.produits.insert_one(produit)
        if stock:
            await entree_stock(tdb, produit, stock, "INVENT", "", "Stock initial (démo)")
    print("Boutique de démonstration créée : /b/demo-telecom — DG demo@demo-telecom.bf / demo-2026!")


if __name__ == "__main__":
    async def _main():
        await ensure_indexes()
        await ensure_super_admin()
        if "--demo" in sys.argv:
            await creer_demo()

    asyncio.run(_main())
