"""Lot E — liens de partage de la boutique et des produits (pages Open Graph publiques,
redirection vers la vitrine, lien du personnel, compteur d'ouvertures)."""
import asyncio

from db import TenantDB, db

# Navigateur d'un humain (redirigé, compté) et robot d'aperçu WhatsApp (ni l'un ni l'autre)
HUMAIN = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/126.0 Mobile"}
ROBOT = {"User-Agent": "WhatsApp/2.24.1 A"}


def _produit(client, h, **extra):
    """Crée une catégorie et un produit visible sur la vitrine ; renvoie le produit."""
    cat = client.post("/api/categories", headers=h, json={"nom": "Rayon partage"}).json()
    donnees = {"reference": "P-PART", "nom": "Galaxy A15", "categorie_id": cat["id"], "prix_vente": 125000,
               "prix_achat": 100000, "stock_initial": 3, "visible_portail": True,
               "description": "Écran 6,5 pouces, 128 Go."}
    donnees.update(extra)
    r = client.post("/api/produits", headers=h, json=donnees)
    assert r.status_code == 201, r.text
    return r.json()


def _maj_boutique(boutique_id, champs):
    asyncio.run(db.boutiques.update_one({"id": boutique_id}, {"$set": champs}))


def test_page_boutique_balises_open_graph(client, nouvelle_boutique):
    b, h = nouvelle_boutique(nom="Boutique Étoile")
    r = client.get(f"/api/partage/b/{b['slug']}", headers=ROBOT)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "max-age=" in r.headers.get("cache-control", "")
    page = r.text
    assert '<meta property="og:title" content="Boutique Étoile — adLyn">' in page
    assert 'property="og:description"' in page and 'property="og:image"' in page
    assert f'/api/partage/b/{b["slug"]}"' in page  # og:url = page de partage elle-même
    # Robot d'aperçu : pas de redirection (il doit lire les balises)
    assert 'http-equiv="refresh"' not in page
    # Visiteur humain : redirection immédiate vers la vitrine + lien de secours
    r = client.get(f"/api/partage/b/{b['slug']}", headers=HUMAIN)
    assert 'http-equiv="refresh"' in r.text and "window.location.replace(" in r.text
    assert f'/b/{b["slug"]}"' in r.text and "Ouvrir la page" in r.text


def test_page_produit_titre_prix_image(client, nouvelle_boutique):
    b, h = nouvelle_boutique()
    p = _produit(client, h)
    # Photo du produit : son adresse doit apparaître (en absolu) dans og:image
    f = {"fichier": ("photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")}
    r = client.post(f"/api/produits/{p['id']}/image", headers=h, files=f)
    image = r.json().get("image_url") if r.status_code == 200 else None
    page = client.get(f"/api/partage/b/{b['slug']}/p/{p['slug']}", headers=ROBOT).text
    assert '<meta property="og:title" content="Galaxy A15 – 125 000 FCFA">' in page
    assert '<meta property="og:type" content="product">' in page
    assert '<meta property="product:price:amount" content="125000">' in page
    assert "Écran 6,5 pouces" in page
    if image:
        assert f'<meta property="og:image" content="{image}">' in page
    else:
        assert '<meta property="og:image" content="http' in page
    # Redirection de l'humain vers la fiche produit de la vitrine
    humain = client.get(f"/api/partage/b/{b['slug']}/p/{p['slug']}", headers=HUMAIN).text
    assert f'/b/{b["slug"]}/produit/{p["slug"]}' in humain


def test_echappement_html(client, nouvelle_boutique):
    b, h = nouvelle_boutique()
    p = _produit(client, h, nom='<script>alert("x")</script> Pirate', description='"><img src=x onerror=alert(1)>')
    page = client.get(f"/api/partage/b/{b['slug']}/p/{p['slug']}", headers=HUMAIN).text
    assert "<script>alert" not in page and "<img src=x" not in page
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; Pirate" in page
    # Nom de boutique piégé (modifié directement en base) : échappé lui aussi
    _maj_boutique(b["id"], {"nom": "<b>Boutique</b> & Cie"})
    page = client.get(f"/api/partage/b/{b['slug']}", headers=ROBOT).text
    assert "<b>Boutique</b>" not in page and "&lt;b&gt;Boutique&lt;/b&gt; &amp; Cie" in page


def test_boutique_non_validee(client, nouvelle_boutique):
    b, h = nouvelle_boutique()
    p = _produit(client, h)
    _maj_boutique(b["id"], {"validee": False})
    # Pages publiques : redirection vers l'accueil du site, sans erreur
    for chemin in (f"/api/partage/b/{b['slug']}", f"/api/partage/b/{b['slug']}/p/{p['slug']}"):
        r = client.get(chemin, headers=HUMAIN, follow_redirects=False)
        assert r.status_code == 302 and not r.headers["location"].rstrip("/").endswith(b["slug"])
    # Personnel : partage désactivé avec un message explicite
    infos = client.get("/api/partage/lien", headers=h).json()
    assert infos["partageable"] is False and "après la validation de votre boutique" in infos["raison"]
    assert infos["url"] == "" and infos["message"] == ""
    infos = client.get(f"/api/partage/lien/produit/{p['id']}", headers=h).json()
    assert infos["partageable"] is False and "validation" in infos["raison"]


def test_produit_inexistant_ou_masque_redirige_vers_la_vitrine(client, nouvelle_boutique):
    b, h = nouvelle_boutique()
    p = _produit(client, h, visible_portail=False)
    for slug in ("produit-inexistant", p["slug"]):
        r = client.get(f"/api/partage/b/{b['slug']}/p/{slug}", headers=HUMAIN, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"].endswith(f"/b/{b['slug']}")
    # Boutique inconnue : accueil du site
    r = client.get("/api/partage/b/boutique-qui-n-existe-pas", headers=HUMAIN, follow_redirects=False)
    assert r.status_code == 302
    # Personnel : produit masqué non partageable, avec la raison
    infos = client.get(f"/api/partage/lien/produit/{p['id']}", headers=h).json()
    assert infos["partageable"] is False and "masqué" in infos["raison"]


def test_lien_et_message_du_personnel(client, nouvelle_boutique, connecter_membre):
    b, h = nouvelle_boutique(nom="Chez Awa")
    p = _produit(client, h)
    infos = client.get("/api/partage/lien", headers=h).json()
    assert infos["partageable"] is True
    assert infos["url"].endswith(f"/api/partage/b/{b['slug']}")
    assert infos["message"] == f"Découvrez Chez Awa sur adLyn : {infos['url']}"
    infos = client.get(f"/api/partage/lien/produit/{p['id']}", headers=h).json()
    assert infos["partageable"] is True and infos["url"].endswith(f"/p/{p['slug']}")
    assert infos["message"] == f"Galaxy A15 – 125 000 FCFA chez Chez Awa : {infos['url']}"
    # Un collaborateur (technicien) peut aussi partager la boutique et un produit
    r = client.post("/api/boutique/equipe", headers=h, json={"nom": "Tech", "email": "tech-partage@test.bf",
                                                             "role": "technicien", "mot_de_passe": "motdepasse-123"})
    assert r.status_code == 201, r.text
    ht, _ = connecter_membre(b["code_marchand"], "tech-partage@test.bf")
    assert client.get("/api/partage/lien", headers=ht).json()["partageable"] is True
    assert client.get(f"/api/partage/lien/produit/{p['id']}", headers=ht).json()["partageable"] is True


def test_compteur_des_ouvertures(client, nouvelle_boutique):
    b, h = nouvelle_boutique()
    p = _produit(client, h)
    url = f"/api/partage/b/{b['slug']}/p/{p['slug']}"
    client.get(url, params={"via": "whatsapp"}, headers=HUMAIN)
    client.get(url, params={"via": "whatsapp"}, headers=HUMAIN)
    client.get(url, params={"via": "qr"}, headers=HUMAIN)
    client.get(url, params={"via": "n'importe-quoi"}, headers=HUMAIN)
    client.get(url, params={"via": "facebook"}, headers=ROBOT)  # robot d'aperçu : non compté
    client.get(f"/api/partage/b/{b['slug']}", params={"via": "copie"}, headers=HUMAIN)
    infos = client.get(f"/api/partage/lien/produit/{p['id']}", headers=h).json()
    assert infos["ouvertures"] == 4
    assert infos["canaux"] == {"whatsapp": 2, "qr": 1, "autre": 1}
    # La fiche article affiche le compteur (« Ouvert X fois via un lien partagé »)
    assert client.get(f"/api/produits/{p['id']}", headers=h).json()["partages"]["ouvertures"] == 4
    assert client.get("/api/partage/lien", headers=h).json()["ouvertures"] == 1
    # Cumul du jour, sans donnée personnelle
    lignes = asyncio.run(db.partages_clics.find({"boutique_id": b["id"]}, {"_id": 0}).to_list(50))
    assert sum(l["ouvertures"] for l in lignes) == 5
    assert all(set(l) == {"boutique_id", "produit_id", "canal", "jour", "ouvertures"} for l in lignes)
    # Le produit reste intact (le comptage ne touche que le champ « partages »)
    produit = asyncio.run(TenantDB(b["id"]).produits.find_one({"id": p["id"]}))
    assert produit["prix_vente"] == 125000 and produit["visible_portail"] is True
