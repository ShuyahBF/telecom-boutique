"""Tests du catalogue public commun : saisie, publication, copie dans les
boutiques, badge « Nouveau », prix propres à chaque boutique, documents privés."""
import io
import json
from types import SimpleNamespace


def _fiche(client, sa, **extra):
    corps = {"type_produit": "TEL", "marque": "Samsung", "nom": "Galaxy Test", "reference": "SM-TEST",
             "caracteristiques": ["Écran : 6,5 pouces"], "statut": "PRET", **extra}
    r = client.post("/api/plateforme/catalogue", headers=sa, json=corps)
    assert r.status_code == 201, r.text
    return r.json()


def _produit_catalogue(client, h, catalogue_id):
    return next((p for p in client.get("/api/produits", headers=h).json() if p.get("catalogue_id") == catalogue_id), None)


def test_publication_et_propagation(client, super_admin, nouvelle_boutique):
    sa = super_admin
    b1, h1 = nouvelle_boutique()
    tel = _fiche(client, sa, reference="SM-A1")
    piece = _fiche(client, sa, type_produit="PIE", nom="Écran Galaxy Test", reference="PIE-A1",
                   modeles_compatibles=[tel["id"]])
    brouillon = _fiche(client, sa, reference="SM-BROUILLON", statut="BROUILLON")
    # Rien n'est visible des boutiques avant la publication
    assert _produit_catalogue(client, h1, tel["id"]) is None
    etat = client.get("/api/plateforme/catalogue/publication", headers=sa).json()
    assert etat["en_attente"] >= 2 and "T23:00:00" in etat["prochaine_publication"]

    rapport = client.post("/api/plateforme/catalogue/publier", headers=sa).json()
    assert rapport["nouveaux"] >= 2
    p = _produit_catalogue(client, h1, tel["id"])
    # Arrive sans prix, invisible sur le portail, avec le badge « Nouveau »
    assert p["nouveau"] is True and p["prix_vente"] == 0 and p["visible_portail"] is False
    assert _produit_catalogue(client, h1, brouillon["id"]) is None
    ecran = _produit_catalogue(client, h1, piece["id"])
    assert ecran["modeles_compatibles"][0]["nom"] == "Samsung Galaxy Test"
    assert client.get("/api/tableau-de-bord", headers=h1).json()["nb_nouveautes_catalogue"] >= 2

    # Une boutique créée APRÈS reçoit tout le catalogue publié, sans badge « Nouveau »
    b2, h2 = nouvelle_boutique()
    p2 = _produit_catalogue(client, h2, tel["id"])
    assert p2 is not None and p2["nouveau"] is False

    # Chaque boutique fixe SON prix ; les informations partagées restent verrouillées
    corps = {k: p[k] for k in ("reference", "type_produit", "categorie_id", "marque", "description",
                               "caracteristiques", "stock_alerte", "garantie_mois", "actif")}
    r = client.put(f"/api/produits/{p['id']}", headers=h1, json={**corps, "nom": "Nom piraté", "prix_vente": 150000,
                                                                   "visible_portail": True})
    assert r.status_code == 200 and r.json()["nom"] == "Galaxy Test" and r.json()["nouveau"] is False
    assert _produit_catalogue(client, h2, tel["id"])["prix_vente"] == 0

    # Mise à jour de la fiche publique : répercutée chez tous, prix conservés
    client.put(f"/api/plateforme/catalogue/{tel['id']}", headers=sa, json={
        "type_produit": "TEL", "marque": "Samsung", "nom": "Galaxy Test 5G", "reference": "SM-A1",
        "caracteristiques": ["Écran : 6,6 pouces"], "statut": "PRET"})
    assert client.post("/api/plateforme/catalogue/publier", headers=sa).json()["mises_a_jour"] == 1
    p = _produit_catalogue(client, h1, tel["id"])
    assert p["nom"] == "Galaxy Test 5G" and p["prix_vente"] == 150000
    assert _produit_catalogue(client, h2, tel["id"])["caracteristiques"] == ["Écran : 6,6 pouces"]

    # Consultation : fiche du téléphone avec ses pièces compatibles
    fiche = client.get(f"/api/catalogue-public/{tel['id']}", headers=h1).json()
    assert [x["reference"] for x in fiche["pieces"]] == ["PIE-A1"]
    assert fiche["produit"]["prix_vente"] == 150000

    # Une fiche publiée ne se supprime pas ; un brouillon si
    assert client.delete(f"/api/plateforme/catalogue/{tel['id']}", headers=sa).status_code == 409
    assert client.delete(f"/api/plateforme/catalogue/{brouillon['id']}", headers=sa).status_code == 200
    # Réservé au super-admin
    assert client.get("/api/plateforme/catalogue", headers=h1).status_code == 403


def test_portail_masque_les_produits_sans_prix(client, super_admin, nouvelle_boutique):
    tel = _fiche(client, super_admin, reference="SM-PORTAIL")
    client.post("/api/plateforme/catalogue/publier", headers=super_admin)
    b, h = nouvelle_boutique()
    p = _produit_catalogue(client, h, tel["id"])
    corps = {k: p[k] for k in ("reference", "nom", "type_produit", "categorie_id", "marque", "description",
                               "caracteristiques", "stock_alerte", "garantie_mois", "actif")}
    # Visible sans prix : refusé
    assert client.put(f"/api/produits/{p['id']}", headers=h, json={**corps, "prix_vente": 0, "visible_portail": True}).status_code == 400
    liste = client.get(f"/api/public/b/{b['slug']}/produits").json()["produits"]
    assert all(x["id"] != p["id"] for x in liste)


def test_documents_prives(client, boutique_equipee, nouvelle_boutique):
    a = boutique_equipee
    tel = a["tel"]
    pdf = io.BytesIO(b"%PDF-1.4 document de test")
    r = client.post(f"/api/produits/{tel['id']}/documents", headers=a["h"],
                    files={"fichier": ("manuel.pdf", pdf, "application/pdf")},
                    data={"titre": "Manuel", "type_document": "MANUEL", "visible_clients": "true"})
    assert r.status_code == 200, r.text
    doc = r.json()["documents"][0]
    assert f"boutiques/{a['boutique']['id']}/documents/" in doc["url"]
    fiche = client.get(f"/api/public/b/{a['boutique']['slug']}/produits/{tel['slug']}").json()
    assert fiche["documents"][0]["titre"] == "Manuel"
    client.patch(f"/api/produits/{tel['id']}/documents/{doc['id']}", headers=a["h"], json={"visible_clients": False})
    assert client.get(f"/api/public/b/{a['boutique']['slug']}/produits/{tel['slug']}").json()["documents"] == []
    # Une autre boutique ne voit pas ce produit
    _, hb = nouvelle_boutique()
    assert client.post(f"/api/produits/{tel['id']}/documents", headers=hb,
                       files={"fichier": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
                       data={"titre": "X"}).status_code == 404


def test_assistant_recherche(client, super_admin, monkeypatch):
    import catalogue_public as cp
    from config import get_settings

    # Sans clé API : message clair
    r = client.post("/api/plateforme/catalogue/recherche", headers=super_admin, json={"marque": "Tecno", "modele": "Spark 20"})
    assert r.status_code == 503

    # Avec une fausse API : la pause (pause_turn) est relancée puis la fiche est lue
    fiche = {"trouve": True, "marque": "Tecno", "nom": "Spark 20", "reference_fabricant": "KJ5", "annee_sortie": 2023,
             "description": "…", "caracteristiques": ["Écran : 6,56 pouces"], "photo_url": "", "pieces_detachees": ["Écran"],
             "sources": ["https://www.tecno-mobile.com"], "remarques": ""}
    appels = []

    class FauxMessages:
        async def create(self, **kwargs):
            appels.append(kwargs)
            if len(appels) == 1:
                return SimpleNamespace(stop_reason="pause_turn", content=[SimpleNamespace(type="server_tool_use")])
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(fiche))])

    class FauxClient:
        def __init__(self, **_):
            self.beta = SimpleNamespace(messages=FauxMessages())

    import anthropic
    monkeypatch.setattr(anthropic, "AsyncAnthropic", FauxClient)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "cle-de-test")
    r = client.post("/api/plateforme/catalogue/recherche", headers=super_admin, json={"marque": "Tecno", "modele": "Spark 20"})
    assert r.status_code == 200 and r.json()["reference_fabricant"] == "KJ5"
    assert len(appels) == 2 and appels[0]["tools"][0]["type"] == "web_search_20260209"
    assert appels[1]["messages"][1]["role"] == "assistant"  # reprise après la pause
    assert cp.prochaine_publication().hour == 23


def test_visibilite_du_deuxieme_document_et_recherche_sans_accents(client, boutique_equipee):
    a = boutique_equipee
    tel = a["tel"]
    for titre in ("Premier", "Second"):
        client.post(f"/api/produits/{tel['id']}/documents", headers=a["h"],
                    files={"fichier": (f"{titre}.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
                    data={"titre": titre, "type_document": "BROCHURE", "visible_clients": "false"})
    docs = client.get(f"/api/produits/{tel['id']}", headers=a["h"]).json()["documents"]
    second = next(d for d in docs if d["titre"] == "Second")
    r = client.patch(f"/api/produits/{tel['id']}/documents/{second['id']}", headers=a["h"], json={"visible_clients": True}).json()
    assert {d["titre"]: d["visible_clients"] for d in r["documents"]} == {"Premier": False, "Second": True}
    # « telephone » retrouve « Téléphone test »
    assert any(p["id"] == tel["id"] for p in client.get("/api/produits", headers=a["h"], params={"q": "telephone"}).json())
