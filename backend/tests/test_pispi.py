"""Encaissement PI-SPI : paramètres de la boutique, bloc imprimé, règlement « PISPI »,
transactions et connecteurs (seul le manuel est actif, aucune API bancaire appelée)."""
import asyncio
import io

import pytest

import pispi_connecteur as pispi
from config import get_settings
from db import db

QR_BANQUE = "000201010211TEXTE-QR-FOURNI-PAR-LA-BANQUE"


def _facture_validee(client, a):
    f = client.post("/api/documents", headers=a["h"], json={
        "client_id": a["client"]["id"], "lignes": [{"produit_id": a["service"]["id"], "quantite": 2}]}).json()
    return client.post(f"/api/documents/{f['id']}/valider", headers=a["h"]).json()


def test_parametres_et_bloc_imprime(client, boutique_equipee):
    a = boutique_equipee
    p = client.get("/api/boutique/pispi", headers=a["h"]).json()
    assert p["actif"] is False and p["connecteur"]["code"] == "manuel" and p["imprimable"] is False
    # Activation refusée sans QR (texte ou image)
    r = client.put("/api/boutique/pispi", headers=a["h"], json={"actif": True, "banque": "UBA"})
    assert r.status_code == 400
    r = client.put("/api/boutique/pispi", headers=a["h"], json={
        "actif": True, "banque": "BSIC", "titulaire": "Boutique Test", "adresse_paiement": "alias-test",
        "qr_contenu": QR_BANQUE})
    assert r.status_code == 200 and r.json()["imprimable"] is True
    # Le QR de la banque est renvoyé TEL QUEL dans le bloc imprimé (avec la consigne par défaut)
    fac = _facture_validee(client, a)
    bloc = client.get(f"/api/documents/{fac['id']}/qr", headers=a["h"]).json()["pispi"]
    assert bloc["qr_contenu"] == QR_BANQUE and bloc["consigne"] == pispi.CONSIGNE_DEFAUT
    # « Autre » banque : son nom est obligatoire
    r = client.put("/api/boutique/pispi", headers=a["h"], json={"actif": False, "banque": "Autre"})
    assert r.status_code == 400


def test_image_du_qr(client, boutique_equipee):
    a = boutique_equipee
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    r = client.post("/api/boutique/pispi/qr-image", headers=a["h"],
                    files={"fichier": ("qr.png", io.BytesIO(png), "image/png")})
    assert r.status_code == 200 and r.json()["qr_image_url"]
    trop = client.post("/api/boutique/pispi/qr-image", headers=a["h"],
                       files={"fichier": ("qr.png", io.BytesIO(b"0" * (1024 * 1024 + 1)), "image/png")})
    assert trop.status_code == 400
    assert client.post("/api/boutique/pispi/qr-image", headers=a["h"],
                       files={"fichier": ("qr.gif", io.BytesIO(b"GIF"), "image/gif")}).status_code == 400
    r = client.put("/api/boutique/pispi", headers=a["h"], json={"actif": True, "banque": "UBA"})
    assert r.status_code == 200 and r.json()["imprimable"] is True


def test_reglement_pispi_et_transactions(client, boutique_equipee):
    a = boutique_equipee
    fac = _facture_validee(client, a)
    assert "PISPI" in client.get("/api/documents/modes-reglement", headers=a["h"]).json()
    # Référence bancaire obligatoire
    r = client.post(f"/api/documents/{fac['id']}/reglements", headers=a["h"], json={"montant": 4000, "mode": "PISPI"})
    assert r.status_code == 400
    r = client.post(f"/api/documents/{fac['id']}/reglements", headers=a["h"],
                    json={"montant": 4000, "mode": "PISPI", "reference": "BQ-123"})
    assert r.status_code == 200 and r.json()["reste_a_payer"] == fac["total_ttc"] - 4000
    tr = client.get("/api/boutique/pispi/transactions", headers=a["h"]).json()
    assert len(tr) == 1 and tr[0]["statut"] == "rapproche" and tr[0]["source"] == "manuel"
    assert tr[0]["reference"] == fac["numero"] and tr[0]["reference_bancaire"] == "BQ-123"
    # Suppression du règlement : transaction « rejete », trace gardée
    reg_id = r.json()["reglements"][-1]["id"]
    client.delete(f"/api/documents/{fac['id']}/reglements/{reg_id}", headers=a["h"])
    tr = client.get("/api/boutique/pispi/transactions", headers=a["h"]).json()
    assert tr[0]["statut"] == "rejete"


def test_transactions_cloisonnees(client, nouvelle_boutique, boutique_equipee):
    a = boutique_equipee
    fac = _facture_validee(client, a)
    client.post(f"/api/documents/{fac['id']}/reglements", headers=a["h"],
                json={"montant": 1000, "mode": "PISPI", "reference": "X"})
    _, h2 = nouvelle_boutique()
    assert client.get("/api/boutique/pispi/transactions", headers=h2).json() == []


def test_notification_desactivee_et_connecteurs(monkeypatch, client):
    assert client.post("/api/pispi/notification", content=b"{}").status_code == 503
    assert pispi.connecteur_actif().code == "manuel"
    # Connecteurs bancaires : emplacements prêts, mais « non disponible » (aucune API appelée)
    for code in ("ecobank", "uba", "bsic", "ibbank"):
        monkeypatch.setattr(get_settings(), "pispi_fournisseur", code)
        c = pispi.connecteur_actif()
        assert c.code == code
        with pytest.raises(pispi.ConnecteurIndisponible):
            asyncio.run(c.demander_paiement("FAC-1", 1000))
    # Même avec des variables saisies, la notification reste fermée (aucun connecteur automatique)
    monkeypatch.setattr(get_settings(), "pispi_api_url", "https://exemple.invalid")
    monkeypatch.setattr(get_settings(), "pispi_client_id", "id")
    monkeypatch.setattr(get_settings(), "pispi_client_secret", "secret")
    assert pispi.notifications_actives() is False
    assert client.post("/api/pispi/notification", content=b"{}").status_code == 503
