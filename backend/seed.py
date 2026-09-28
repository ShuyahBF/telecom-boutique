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
from utils import new_id, now_iso


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


PRODUITS_DEMO = [
    # (référence, nom, type, catégorie, marque, prix achat, prix vente, stock)
    ("SAM-A15", "Samsung Galaxy A15 128 Go", "TEL", "Smartphones", "Samsung", 85000, 110000, 8),
    ("TEC-SP20", "Tecno Spark 20 256 Go", "TEL", "Smartphones", "Tecno", 70000, 92000, 12),
    ("INF-HOT40", "Infinix Hot 40i", "TEL", "Smartphones", "Infinix", 60000, 79000, 5),
    ("IPH-13", "Apple iPhone 13 128 Go", "TEL", "Smartphones", "Apple", 330000, 395000, 2),
    ("NOK-105", "Nokia 105", "TEL", "Téléphones basiques", "Nokia", 9000, 13500, 20),
    ("ACC-CHG25", "Chargeur rapide 25 W USB-C", "ACC", "Chargeurs & câbles", "Samsung", 6000, 10000, 30),
    ("ACC-ECO", "Écouteurs Bluetooth", "ACC", "Audio", "Oraimo", 8000, 15000, 15),
    ("ACC-VERRE", "Verre trempé universel", "ACC", "Protections", "", 300, 1500, 60),
    ("PIE-ECR-A15", "Écran de remplacement Galaxy A15", "PIE", "Pièces détachées", "Samsung", 18000, 30000, 3),
    ("SER-MO", "Main d'œuvre réparation", "SER", "Services", "", 0, 5000, 0),
]


async def creer_demo() -> None:
    """Boutique « Démo Télécom » (gérant : demo@demo-telecom.bf / demo-2026!)."""
    from routes.plateforme import boutique_par_defaut
    from utils import slugifier

    if await db.boutiques.find_one({"slug": "demo-telecom"}):
        print("La boutique de démonstration existe déjà.")
        return
    boutique = {"id": new_id(), "nom": "Démo Télécom", "slug": "demo-telecom", "code_marchand": "DEMO01",
                "ville": "Ouagadougou", "telephone": "+22625000000", "email": "", "actif": True,
                "mise_en_avant": True, "ordre": 0, "created_at": now_iso(), **boutique_par_defaut("Démo Télécom"),
                "slogan": "Téléphones, accessoires et réparation", "adresse": "Avenue Kwame Nkrumah, Ouagadougou"}
    await db.boutiques.insert_one(boutique.copy())
    await db.users.insert_one({"id": new_id(), "email": "demo@demo-telecom.bf", "nom": "Gérant Démo",
                               "password_hash": hash_password("demo-2026!"), "role": "gerant",
                               "boutique_id": boutique["id"], "actif": True, "created_at": now_iso()})
    tdb = TenantDB(boutique["id"])
    categories: dict[str, dict] = {}
    for ordre, (ref, nom, typ, cat, marque, pa, pv, stock) in enumerate(PRODUITS_DEMO):
        if cat not in categories:
            categories[cat] = {"id": new_id(), "nom": cat, "slug": slugifier(cat), "ordre": ordre}
            await tdb.categories.insert_one(categories[cat])
        await tdb.produits.insert_one({
            "id": new_id(), "reference": ref, "nom": nom, "slug": slugifier(f"{nom}-{ref}"), "type_produit": typ,
            "categorie_id": categories[cat]["id"], "categorie_nom": cat, "marque": marque, "description": "",
            "caracteristiques": [], "image_url": None, "prix_achat": pa, "prix_vente": pv, "stock": stock,
            "stock_alerte": 2, "garantie_mois": 12 if typ == "TEL" else 0, "visible_portail": typ in ("TEL", "ACC"),
            "actif": True, "created_at": now_iso()})
    print("Boutique de démonstration créée : /b/demo-telecom — gérant demo@demo-telecom.bf / demo-2026!")


if __name__ == "__main__":
    async def _main():
        await ensure_indexes()
        await ensure_super_admin()
        if "--demo" in sys.argv:
            await creer_demo()

    asyncio.run(_main())
