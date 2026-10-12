"""Page Facebook d'adLyn animée par Liluvine (SAWALI) : accord de la boutique (désactivé par défaut, modifiable dans
Paramètres), candidats (articles en vente des boutiques VALIDÉES et CONSENTANTES, avec photo et prix, nom de la
boutique, lien de partage produit du lot 45, aucune donnée personnelle), publication notée (facebook_publie) et
article non reproposé ; signature exigée comme pour les autres retours. Base en mémoire (voir conftest.py)."""
import asyncio
import json
import time

import pytest

import partage_facebook
import transmission_wa as tw
from config import get_settings
from db import db

CLE = "cle-hmac-de-test-facebook"
CHEMIN = "/api/webhooks/liluvine-retour"


@pytest.fixture
def reglages(client, monkeypatch):
    """Transmission Liluvine configurée avec une clé de test (aucun secret réel)."""
    s = get_settings()
    monkeypatch.setattr(s, "liluvine_wa_url", "https://sawali.test/api/webhook/liluvine-send")
    monkeypatch.setattr(s, "liluvine_wa_hmac", CLE)
    monkeypatch.setattr(s, "liluvine_wa_emetteur", "adlyn")
    return s


def _poster(client, doc, cle=CLE):
    """POST signé exactement comme le fait SAWALI."""
    corps = json.dumps(doc).encode()
    ts = str(int(time.time()))
    return client.post(CHEMIN, content=corps, headers={
        "Content-Type": "application/json", "X-Emetteur": "sawali", "X-Timestamp": ts,
        "X-Signature": tw.signer(cle, ts, corps)})


def _produit(client, h, ref, image="https://cdn.exemple/photo.jpg", **extra):
    """Crée un article visible sur la vitrine, avec sa photo (posée directement en base)."""
    cat = client.post("/api/categories", headers=h, json={"nom": f"Rayon {ref}"}).json()
    donnees = {"reference": ref, "nom": f"Article {ref}", "categorie_id": cat["id"], "prix_vente": 125000,
               "prix_achat": 100000, "stock_initial": 3, "visible_portail": True,
               "description": "Écran 6,5 pouces,   128 Go."}
    donnees.update(extra)
    r = client.post("/api/produits", headers=h, json=donnees)
    assert r.status_code == 201, r.text
    p = r.json()
    asyncio.run(db.produits.update_one({"id": p["id"]}, {"$set": {"image_url": image}}))
    return p


def _maj_boutique(boutique_id, champs):
    asyncio.run(db.boutiques.update_one({"id": boutique_id}, {"$set": champs}))


def _ids(client):
    return [x["element_id"] for x in _poster(client, {"type": "facebook_candidats", "nombre": 15}).json()["candidats"]]


def test_accord_desactive_par_defaut_et_modifiable(client, nouvelle_boutique):
    b, h = nouvelle_boutique(nom="Boutique Accord")
    assert not client.get("/api/boutique", headers=h).json().get("publication_facebook_adlyn")
    r = client.patch("/api/boutique", headers=h, json={"publication_facebook_adlyn": True})
    assert r.status_code == 200 and r.json()["publication_facebook_adlyn"] is True
    fiche = asyncio.run(db.boutiques.find_one({"id": b["id"]}))
    assert fiche["publication_facebook_adlyn_le"] and fiche["publication_facebook_adlyn_par"]
    r = client.patch("/api/boutique", headers=h, json={"publication_facebook_adlyn": False})
    assert r.json()["publication_facebook_adlyn"] is False


def test_candidats_filtres_consentement_et_sans_donnee_personnelle(client, nouvelle_boutique, reglages):
    # Boutique consentante et validée : ses articles en vente avec photo sont proposés
    b, h = nouvelle_boutique(nom="Boutique Soleil", dg_telephone="70 11 22 33")
    client.patch("/api/boutique", headers=h, json={"publication_facebook_adlyn": True})
    ok = _produit(client, h, "FB-OK")
    relative = _produit(client, h, "FB-REL", image="/uploads/photo-relative.png")   # rendue absolue par le serveur
    sans_photo = _produit(client, h, "FB-SANS", image=None)
    masque = _produit(client, h, "FB-MASQUE", visible_portail=False)
    # Boutique NON consentante (réglage par défaut) : jamais proposée
    b2, h2 = nouvelle_boutique(nom="Boutique Discrète")
    discret = _produit(client, h2, "FB-DISC")
    # Boutique consentante mais non validée, ou de démonstration : jamais proposée
    b3, h3 = nouvelle_boutique(nom="Boutique Attente")
    client.patch("/api/boutique", headers=h3, json={"publication_facebook_adlyn": True})
    attente = _produit(client, h3, "FB-ATT")
    _maj_boutique(b3["id"], {"validee": False})
    b4, h4 = nouvelle_boutique(nom="Boutique Démo")
    client.patch("/api/boutique", headers=h4, json={"publication_facebook_adlyn": True})
    demo = _produit(client, h4, "FB-DEMO")
    _maj_boutique(b4["id"], {"test": True})

    r = _poster(client, {"type": "facebook_candidats", "nombre": 15})
    assert r.status_code == 200
    cands = r.json()["candidats"]
    ids = [x["element_id"] for x in cands]
    assert ok["id"] in ids and relative["id"] in ids
    for exclu in (sans_photo, masque, discret, attente, demo):
        assert exclu["id"] not in ids
    c = next(x for x in cands if x["element_id"] == ok["id"])
    assert c["nom"] == "Article FB-OK" and c["boutique"] == "Boutique Soleil"
    assert c["prix_fcfa"] == 125000 and c["prix_txt"] == "125 000 FCFA"
    assert c["photo_url"] == "https://cdn.exemple/photo.jpg" and c["description"] == "Écran 6,5 pouces, 128 Go."
    assert c["lien"].endswith(f"/api/partage/b/{b['slug']}/p/{ok['slug']}?via=facebook")
    assert next(x for x in cands if x["element_id"] == relative["id"])["photo_url"].startswith("http")
    # Uniquement des données de vitrine : ni gérant, ni téléphone, ni prix d'achat
    assert set(c) == {"element_id", "type", "nom", "description", "boutique", "prix_fcfa", "prix_txt", "photo_url", "lien"}
    texte = json.dumps(cands)
    assert "70 11 22 33" not in texte and "100000" not in texte and "DG " not in texte
    # Au plus 2 articles par boutique et par demande
    assert sum(1 for x in cands if x["boutique"] == "Boutique Soleil") <= partage_facebook.PAR_BOUTIQUE

    # La boutique retire son accord : plus rien n'est proposé
    client.patch("/api/boutique", headers=h, json={"publication_facebook_adlyn": False})
    assert ok["id"] not in _ids(client)


def test_facebook_publie_et_delai(client, nouvelle_boutique, reglages):
    b, h = nouvelle_boutique(nom="Boutique Publiée")
    client.patch("/api/boutique", headers=h, json={"publication_facebook_adlyn": True})
    p = _produit(client, h, "FB-PUB")
    assert p["id"] in _ids(client)
    assert _poster(client, {"type": "facebook_publie", "element_id": p["id"], "post_id": "123_456"}).json() == {"ok": True}
    fiche = asyncio.run(db.produits.find_one({"id": p["id"]}))
    assert fiche["facebook_post_id"] == "123_456" and fiche["facebook_publie_le"]
    assert p["id"] not in _ids(client)                       # pas reproposé avant 30 jours
    assert _poster(client, {"type": "facebook_publie", "element_id": "inconnu"}).json() == {"ok": False}


def test_signature_exigee(client, reglages):
    assert _poster(client, {"type": "facebook_candidats"}, cle="mauvaise").status_code == 401
    assert client.post(CHEMIN, json={"type": "facebook_candidats"}).status_code == 401
