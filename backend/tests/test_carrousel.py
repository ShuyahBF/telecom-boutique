"""Carrousel WhatsApp : service inactif tant que WhatsApp n'est pas branché, envoi réservé
aux clients qui ont donné leur accord, corps du modèle Meta, boutiques de démonstration."""
import httpx

from config import get_settings
from db import db


class _Ok:
    """Réponse simulée de l'API WhatsApp (message accepté)."""
    status_code = 200
    text = "{}"


def _preparer(client, boutique_equipee):
    """Met les deux produits de la boutique en vente avec une photo en ligne."""
    b = boutique_equipee["boutique"]
    client.portal.call(lambda: db.produits.update_many({"boutique_id": b["id"]}, {"$set": {
        "actif": True, "visible_portail": True, "image_url": "https://pub-test.r2.dev/photo.jpg"}}))
    return [boutique_equipee["tel"]["id"], boutique_equipee["service"]["id"]]


def _brancher_whatsapp(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_access_token", "jeton-test")
    monkeypatch.setattr(s, "whatsapp_phone_number_id", "123456")
    monkeypatch.setattr(s, "whatsapp_carrousel_template", "adlyn_carrousel")


def _capturer(monkeypatch):
    envois = []

    async def faux_post(self, url, json=None, headers=None):
        envois.append(json)
        return _Ok()

    monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)
    return envois


def test_service_inactif_sans_whatsapp(client, boutique_equipee):
    h = boutique_equipee["h"]
    assert client.get("/api/boutique/carrousel", headers=h).json()["configure"] is False
    produits = _preparer(client, boutique_equipee)
    r = client.post("/api/boutique/carrousel/envoyer", headers=h, json={
        "produit_ids": produits, "message": "Nouveautés !", "client_ids": [boutique_equipee["client"]["id"]]})
    assert r.status_code == 503


def test_envoi_carrousel_aux_clients_consentants(client, boutique_equipee, monkeypatch):
    _brancher_whatsapp(monkeypatch)
    envois = _capturer(monkeypatch)
    b, h, cli = boutique_equipee["boutique"], boutique_equipee["h"], boutique_equipee["client"]
    produits = _preparer(client, boutique_equipee)
    assert len(client.get("/api/boutique/carrousel/produits", headers=h).json()) == 2

    # Sans accord du client : aucun destinataire possible
    campagne = {"produit_ids": produits, "message": "Nos offres de la semaine", "client_ids": [cli["id"]]}
    assert client.post("/api/boutique/carrousel/envoyer", headers=h, json=campagne).status_code == 400

    # Accord donné sur la fiche client : date enregistrée
    fiche = {k: cli[k] for k in ("nom", "telephone", "email")}
    r = client.put(f"/api/clients/{cli['id']}", headers=h, json={**fiche, "accepte_whatsapp": True})
    assert r.json()["accepte_whatsapp"] is True and r.json()["accepte_whatsapp_le"]
    # Accord donné par un autre client lors d'une commande sur la vitrine
    r = client.post(f"/api/public/b/{b['slug']}/commandes", json={
        "nom": "Awa Kaboré", "telephone": "76 55 44 33", "accepte_whatsapp": True,
        "lignes": [{"produit_id": boutique_equipee["tel"]["id"], "quantite": 1}]})
    assert r.status_code == 201, r.text
    dest = client.get("/api/boutique/carrousel/destinataires", headers=h).json()
    assert {d["nom"] for d in dest} == {"Client Test", "Awa Kaboré"}

    r = client.post("/api/boutique/carrousel/envoyer", headers=h,
                    json={**campagne, "client_ids": [d["id"] for d in dest]})
    assert r.status_code == 202 and r.json()["nb_destinataires"] == 2
    historique = client.get("/api/boutique/carrousel/campagnes", headers=h).json()
    assert historique[0]["statut"] == "TERMINEE" and historique[0]["envoyes"] == 2

    # Corps envoyé à Meta : modèle « <base>_<nb cartes> », une carte par produit
    corps = envois[0]["template"]
    assert corps["name"] == "adlyn_carrousel_2"
    cartes = next(c for c in corps["components"] if c["type"] == "carousel")["cards"]
    assert len(cartes) == 2
    assert cartes[0]["components"][0]["parameters"][0]["image"]["link"] == "https://pub-test.r2.dev/photo.jpg"
    assert cartes[0]["components"][1]["parameters"][1]["text"] == "100 000 FCFA"
    assert cartes[0]["components"][2]["parameters"][0]["text"].startswith(f"{b['slug']}/produit/")
    assert client.get("/api/boutique/carrousel", headers=h).json()["mois_envoyes"] == 2

    # Accord retiré : le client n'est plus destinataire
    client.put(f"/api/clients/{cli['id']}", headers=h, json={**fiche, "accepte_whatsapp": False})
    assert [d["nom"] for d in client.get("/api/boutique/carrousel/destinataires", headers=h).json()] == ["Awa Kaboré"]


def test_boutique_de_demonstration_n_envoie_rien(client, super_admin, boutique_equipee, monkeypatch):
    _brancher_whatsapp(monkeypatch)
    envois = _capturer(monkeypatch)
    b, h, cli = boutique_equipee["boutique"], boutique_equipee["h"], boutique_equipee["client"]
    client.patch(f"/api/plateforme/boutiques/{b['id']}", headers=super_admin, json={"test": True})
    client.cookies.clear()
    produits = _preparer(client, boutique_equipee)
    client.put(f"/api/clients/{cli['id']}", headers=h, json={"nom": cli["nom"], "telephone": cli["telephone"],
                                                            "accepte_whatsapp": True})
    r = client.post("/api/boutique/carrousel/envoyer", headers=h, json={
        "produit_ids": produits, "message": "Test", "client_ids": [cli["id"]]})
    assert r.status_code == 202
    assert envois == []  # aucun appel à Meta
    assert client.get("/api/boutique/carrousel/campagnes", headers=h).json()[0]["resultats"][0]["statut"] == "NON_ENVOYE"
