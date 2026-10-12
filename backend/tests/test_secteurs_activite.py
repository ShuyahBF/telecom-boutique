"""Lot A — secteurs d'activité : référentiel initialisé au démarrage, migration des
boutiques existantes vers le télécom, création d'une boutique de prêt-à-porter
(modules, catégories, aucune copie du catalogue de téléphones), validation des
attributs des articles, vocabulaire envoyé par /auth/me, CRUD réservé au super-admin."""
import asyncio

import pytest
from fastapi import HTTPException

import secteurs
from db import db


def _login(client, boutique, email):
    """Connexion du DG d'une boutique créée dans le test (jeton « Bearer »)."""
    r = client.post("/api/auth/login", json={"code_boutique": boutique["code_marchand"], "email": email,
                                              "password": "motdepasse-123"})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _creer_boutique(client, super_admin, suffixe, **extra):
    """Crée une boutique par la plateforme (avec un secteur éventuel) ; renvoie (réponse, en-têtes du DG)."""
    email = f"dg-secteur-{suffixe}@test.bf"
    r = client.post("/api/plateforme/boutiques", headers=super_admin, json={
        "nom": f"Boutique secteur {suffixe}", "ville": "Ouagadougou", "telephone": "25 00 00 00",
        "dg_nom": f"DG {suffixe}", "dg_email": email, "dg_mot_de_passe": "motdepasse-123", **extra})
    assert r.status_code == 201, r.text
    return r.json(), _login(client, r.json()["boutique"], email)


# ---------------------------------------------------------------------------
# Initialisation et migration
# ---------------------------------------------------------------------------
def test_secteurs_initialises_au_demarrage(client, super_admin):
    r = client.get("/api/plateforme/secteurs", headers=super_admin)
    assert r.status_code == 200, r.text
    codes = [s["code"] for s in r.json()["secteurs"]]
    for code in ("telecom", "pret_a_porter", "cosmetiques", "quincaillerie", "alimentation",
                 "pharmacie", "electromenager", "librairie", "autre"):
        assert code in codes
    fiches = {s["code"]: s for s in r.json()["secteurs"]}
    # Seul le télécom reçoit le catalogue de téléphones ; le SAV n'est proposé d'office à aucun autre secteur
    assert [c for c, s in fiches.items() if s["catalogue_telecom"]] == ["telecom"]
    assert all("maintenance" not in s["modules"] and "catalogue_public" not in s["modules"]
               for c, s in fiches.items() if c != "telecom")
    assert {c["cle"] for c in fiches["pret_a_porter"]["champs"]} >= {"taille", "couleur", "matiere", "genre", "saison"}
    # Relancer l'initialisation ne crée pas de doublon
    asyncio.run(secteurs.initialiser())
    assert asyncio.run(db.secteurs.count_documents({"code": "telecom"})) == 1
    # Route publique : secteurs actifs seulement, code + libellé + pictogramme
    publics = client.get("/api/secteurs").json()
    assert {"code", "libelle", "icone"} == set(publics[0])
    assert "telecom" in [s["code"] for s in publics]


def test_migration_des_boutiques_existantes_vers_telecom(client, nouvelle_boutique):
    b, h = nouvelle_boutique()
    # Boutique « d'avant le lot » : sans secteur ; on rejoue la migration sans son marqueur
    asyncio.run(db.boutiques.update_one({"id": b["id"]}, {"$unset": {"secteur": "", "secteurs_secondaires": ""}}))
    asyncio.run(db.migrations.delete_one({"id": secteurs.MIGRATION_TELECOM}))
    assert asyncio.run(secteurs.migrer_boutiques()) >= 1
    fiche = asyncio.run(db.boutiques.find_one({"id": b["id"]}, {"_id": 0}))
    assert fiche["secteur"] == "telecom" and fiche["secteurs_secondaires"] == []
    # Idempotente : le marqueur empêche une seconde exécution
    asyncio.run(db.boutiques.update_one({"id": b["id"]}, {"$unset": {"secteur": ""}}))
    assert asyncio.run(secteurs.migrer_boutiques()) == 0
    # Sans secteur, la boutique reste traitée comme une boutique télécom
    me = client.get("/api/auth/me", headers=h).json()
    assert me["boutique"]["secteur"] == "telecom"
    asyncio.run(db.boutiques.update_one({"id": b["id"]}, {"$set": {"secteur": "telecom"}}))


# ---------------------------------------------------------------------------
# Création d'une boutique
# ---------------------------------------------------------------------------
def test_creation_boutique_telecom_par_defaut(client, super_admin):
    donnees, _ = _creer_boutique(client, super_admin, "tel")
    b = donnees["boutique"]
    assert b["secteur"] == "telecom"
    # Comportement inchangé : seules les deux options obligatoires
    actives = {c for c, v in b["options_actives"].items() if v}
    assert actives == {"tableau_de_bord", "caisse_aizenta"}


def test_creation_boutique_pret_a_porter(client, super_admin):
    # Un modèle publié dans le catalogue public : une boutique télécom le recevrait
    asyncio.run(db.catalogue_publie.update_one({"id": "modele-test-secteur"}, {"$set": {
        "id": "modele-test-secteur", "reference": "TST-1", "nom": "Téléphone test secteur", "marque": "Test",
        "type_produit": "TEL", "caracteristiques": [], "modeles_compatibles": []}}, upsert=True))
    donnees, h = _creer_boutique(client, super_admin, "pap", secteur="pret_a_porter")
    b = donnees["boutique"]
    assert b["secteur"] == "pret_a_porter" and b["secteurs_secondaires"] == []
    # Aucun téléphone copié
    assert donnees["produits_copies"] == 0
    assert client.get("/api/produits", headers=h).json() == []
    # Modules du secteur activés, SAV et catalogue public non proposés
    actives = b["options_actives"]
    for module in ("produits", "stock", "clients", "documents"):
        assert actives[module] is True
    assert actives["maintenance"] is False and actives["catalogue_public"] is False
    # Catégories de départ créées
    noms = [c["nom"] for c in client.get("/api/categories", headers=h).json()]
    assert noms[:3] == ["Femme", "Homme", "Enfant"]
    # Une boutique télécom, elle, reçoit le modèle
    telecom, _ = _creer_boutique(client, super_admin, "tel2")
    assert telecom["produits_copies"] >= 1
    # Publication du soir : une nouvelle fiche ne part que chez les boutiques télécom
    import catalogue_public
    asyncio.run(db.catalogue_modeles.insert_one({
        "id": "modele-test-secteur-2", "reference": "TST-2", "nom": "Téléphone du soir", "marque": "Test",
        "type_produit": "TEL", "statut": "PRET", "caracteristiques": [], "modeles_compatibles": []}))
    try:
        asyncio.run(catalogue_public.publier("test"))
        assert asyncio.run(db.produits.count_documents({"boutique_id": b["id"]})) == 0
        assert asyncio.run(db.produits.count_documents({"boutique_id": telecom["boutique"]["id"],
                                                        "catalogue_id": "modele-test-secteur-2"})) == 1
    finally:
        # Le catalogue public partagé par toute la suite de tests est remis en l'état
        for collection in (db.catalogue_publie, db.catalogue_modeles):
            asyncio.run(collection.delete_many({"id": {"$in": ["modele-test-secteur", "modele-test-secteur-2"]}}))
        asyncio.run(db.produits.delete_many({"catalogue_id": {"$in": ["modele-test-secteur", "modele-test-secteur-2"]}}))


def test_secteur_inconnu_refuse(client, super_admin):
    r = client.post("/api/plateforme/boutiques", headers=super_admin, json={
        "nom": "Boutique inconnue", "dg_nom": "DG X", "dg_email": "dg-inconnu@test.bf",
        "dg_mot_de_passe": "motdepasse-123", "secteur": "nimporte_quoi"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /auth/me : vocabulaire et champs du secteur
# ---------------------------------------------------------------------------
def test_auth_me_contient_le_vocabulaire(client, super_admin):
    _, h = _creer_boutique(client, super_admin, "voc", secteur="pret_a_porter")
    b = client.get("/api/auth/me", headers=h).json()["boutique"]
    assert b["secteur"] == "pret_a_porter"
    assert b["vocabulaire"]["article"] == "Article" and b["vocabulaire"]["categorie"] == "Rayon"
    # Termes non précisés par le secteur : valeurs actuelles de l'interface
    assert b["vocabulaire"]["stock"] == "Stock"
    assert any(c["cle"] == "taille" for c in b["champs_secteur"])
    assert b["secteur_info"]["icone"] == "👗" and b["secteur_info"]["catalogue_telecom"] is False
    # Boutique télécom : vocabulaire actuel, aucun champ en plus
    _, h_tel = _creer_boutique(client, super_admin, "voc-tel")
    t = client.get("/api/auth/me", headers=h_tel).json()["boutique"]
    assert t["vocabulaire"]["article"] == "Produit" and t["champs_secteur"] == []


# ---------------------------------------------------------------------------
# Articles : type par défaut et attributs
# ---------------------------------------------------------------------------
def test_validation_des_attributs_sur_les_articles(client, super_admin):
    donnees, h = _creer_boutique(client, super_admin, "attr", secteur="pret_a_porter")
    cat = client.get("/api/categories", headers=h).json()[0]
    base = {"reference": "ROBE-1", "nom": "Robe d'été", "categorie_id": cat["id"], "prix_vente": 15000}
    # Valeur hors liste refusée
    r = client.post("/api/produits", headers=h, json={**base, "attributs": {"taille": "Gigantesque"}})
    assert r.status_code == 400 and "Taille" in r.json()["detail"]
    # Article valide : type « ART » par défaut, attributs nettoyés (clé inconnue ignorée)
    r = client.post("/api/produits", headers=h, json={**base, "attributs": {
        "taille": "M", "couleur": " Bleu ", "inconnu": "x", "genre": ""}})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["type_produit"] == "ART" and p["attributs"] == {"taille": "M", "couleur": "Bleu"}
    assert p["fiche_technique"] is None
    # Modification sans attributs : ceux enregistrés sont gardés
    r = client.put(f"/api/produits/{p['id']}", headers=h, json={**base, "prix_vente": 16000})
    assert r.status_code == 200 and r.json()["attributs"] == {"taille": "M", "couleur": "Bleu"}
    # Champ obligatoire, nombre et date (secteur modifié par le super-admin)
    fiche = client.get("/api/plateforme/secteurs", headers=super_admin).json()
    pap = next(s for s in fiche["secteurs"] if s["code"] == "pret_a_porter")
    corps = {k: pap[k] for k in ("libelle", "icone", "actif", "ordre", "vocabulaire", "modules",
                                 "categories_depart", "catalogue_telecom")}
    champs = pap["champs"] + [{"cle": "poids_g", "libelle": "Poids (g)", "type": "nombre", "options": [], "obligatoire": True},
                              {"cle": "arrivage", "libelle": "Arrivage", "type": "date", "options": [], "obligatoire": False}]
    try:
        assert client.put("/api/plateforme/secteurs/pret_a_porter", headers=super_admin,
                          json={**corps, "champs": champs}).status_code == 200
        r = client.post("/api/produits", headers=h, json={**base, "reference": "ROBE-2", "attributs": {}})
        assert r.status_code == 400 and "obligatoire" in r.json()["detail"]
        r = client.post("/api/produits", headers=h, json={**base, "reference": "ROBE-2", "attributs": {"poids_g": "abc"}})
        assert r.status_code == 400
        r = client.post("/api/produits", headers=h, json={**base, "reference": "ROBE-2",
                                                         "attributs": {"poids_g": "250,5", "arrivage": "2026-10-01"}})
        assert r.status_code == 201, r.text
        assert r.json()["attributs"] == {"poids_g": 250.5, "arrivage": "2026-10-01"}
    finally:
        client.put("/api/plateforme/secteurs/pret_a_porter", headers=super_admin, json={**corps, "champs": pap["champs"]})


def test_valider_attributs_types():
    champs = [{"cle": "tailles", "libelle": "Tailles", "type": "multi_liste", "options": ["S", "M"], "obligatoire": False},
              {"cle": "date_peremption", "libelle": "Péremption", "type": "date", "options": [], "obligatoire": False}]
    assert secteurs.valider_attributs(champs, {"tailles": ["S", "M"]}) == {"tailles": ["S", "M"]}
    with pytest.raises(HTTPException):
        secteurs.valider_attributs(champs, {"tailles": ["XL"]})
    with pytest.raises(HTTPException):
        secteurs.valider_attributs(champs, {"date_peremption": "31/12/2026"})
    assert secteurs.lignes_attributs(champs, {"date_peremption": "2026-12-31"}) == ["Péremption : 31/12/2026"]


def test_boutique_telecom_inchangee(client, boutique_equipee):
    """Télécom : type « TEL » par défaut (comme avant), aucun attribut imposé."""
    assert boutique_equipee["tel"]["type_produit"] == "TEL"
    assert boutique_equipee["tel"]["attributs"] == {}


# ---------------------------------------------------------------------------
# CRUD réservé au super-administrateur
# ---------------------------------------------------------------------------
def test_crud_reserve_au_super_admin(client, super_admin, nouvelle_boutique):
    _, h_dg = nouvelle_boutique()
    nouveau = {"code": "bijouterie", "libelle": "Bijouterie", "icone": "💍", "vocabulaire": {"article": "Bijou", "inconnu": "x"},
               "champs": [{"cle": "metal", "libelle": "Métal", "type": "liste", "options": ["Or", "Argent"]}],
               "modules": ["produits", "stock"], "categories_depart": ["Bagues", "Colliers", "bagues"]}
    # Un DG ou un visiteur ne peut ni lire ni modifier le référentiel
    assert client.get("/api/plateforme/secteurs", headers=h_dg).status_code in (401, 403)
    assert client.post("/api/plateforme/secteurs", headers=h_dg, json=nouveau).status_code in (401, 403)
    assert client.post("/api/plateforme/secteurs", json=nouveau).status_code in (401, 403)
    # Création par le super-admin (vocabulaire filtré, catégories sans doublon)
    r = client.post("/api/plateforme/secteurs", headers=super_admin, json=nouveau)
    assert r.status_code == 201, r.text
    assert r.json()["vocabulaire"] == {"article": "Bijou"} and r.json()["categories_depart"] == ["Bagues", "Colliers"]
    assert client.post("/api/plateforme/secteurs", headers=super_admin, json=nouveau).status_code == 409
    # Contrôles : liste sans options, module inconnu
    mauvais = {**nouveau, "code": "x_mauvais", "champs": [{"cle": "metal", "libelle": "Métal", "type": "liste"}]}
    assert client.post("/api/plateforme/secteurs", headers=super_admin, json=mauvais).status_code == 400
    assert client.post("/api/plateforme/secteurs", headers=super_admin,
                       json={**nouveau, "code": "x_mauvais2", "modules": ["inexistant"]}).status_code == 400
    # Modification : désactivé, il disparaît de la liste publique
    corps = {k: v for k, v in nouveau.items() if k != "code"}
    assert client.put("/api/plateforme/secteurs/bijouterie", headers=h_dg, json=corps).status_code in (401, 403)
    r = client.put("/api/plateforme/secteurs/bijouterie", headers=super_admin, json={**corps, "actif": False})
    assert r.status_code == 200 and r.json()["actif"] is False
    assert "bijouterie" not in [s["code"] for s in client.get("/api/secteurs").json()]
    # Le télécom ne peut être ni désactivé ni supprimé
    assert client.delete("/api/plateforme/secteurs/telecom", headers=super_admin).status_code == 400
    # Suppression
    assert client.delete("/api/plateforme/secteurs/bijouterie", headers=h_dg).status_code in (401, 403)
    assert client.delete("/api/plateforme/secteurs/bijouterie", headers=super_admin).status_code == 200
    assert client.delete("/api/plateforme/secteurs/bijouterie", headers=super_admin).status_code == 404


def test_super_admin_change_le_secteur_d_une_boutique(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique()
    r = client.patch(f"/api/plateforme/boutiques/{b['id']}", headers=super_admin, json={"secteur": "cosmetiques"})
    assert r.status_code == 200 and r.json()["secteur"] == "cosmetiques"
    assert client.get("/api/auth/me", headers=h).json()["boutique"]["champs_secteur"][0]["cle"] == "contenance"
    r = client.patch(f"/api/plateforme/boutiques/{b['id']}", headers=super_admin, json={"secteur": "inconnu"})
    assert r.status_code == 400


def test_attributs_sur_la_vitrine_publique():
    """Vitrine : les attributs s'ajoutent aux lignes « Libellé : valeur » sous le titre « Caractéristiques »."""
    from routes.public import _produit_public
    champs = secteurs.secteur_en_cache("pret_a_porter")["champs"]
    p = {"id": "x", "nom": "Robe", "type_produit": "ART", "attributs": {"taille": "M", "couleur": "Bleu"}, "stock": 3}
    publique = _produit_public(p, champs)
    assert publique["fiche_technique"] == ["Taille / pointure : M", "Couleur : Bleu"]
    assert publique["titre_fiche"] == "Caractéristiques"
