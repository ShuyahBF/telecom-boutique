"""Configuration des tests : base MongoDB EN MÉMOIRE (mongomock) et stockage
local temporaire — aucun accès réseau, aucune donnée réelle touchée.
Les variables d'environnement sont posées AVANT l'import de l'application."""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="tlb-tests-")
os.environ.update({
    "MONGO_URL": "mongomock://",
    "STORAGE_BACKEND": "local",
    "UPLOADS_DIR": str(Path(_tmp) / "uploads"),
    "JWT_SECRET": "secret-de-test",
    "SUPER_ADMIN_EMAIL": "super@plateforme-test.bf",
    "SUPER_ADMIN_PASSWORD": "super-motdepasse",
    "PAWAPAY_API_TOKEN_SANDBOX": "",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_compteur = {"n": 0}


@pytest.fixture(scope="session")
def client():
    import server

    with TestClient(server.app) as c:  # "with" déclenche le démarrage (index, super-admin)
        yield c


@pytest.fixture(scope="session")
def super_admin(client):
    r = client.post("/api/auth/login", json={"email": "super@plateforme-test.bf", "password": "super-motdepasse"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def nouvelle_boutique(client, super_admin):
    """Crée une boutique + son gérant ; renvoie (boutique, en-têtes du gérant)."""
    def _creer(nom=None, **extra):
        _compteur["n"] += 1
        n = _compteur["n"]
        r = client.post("/api/plateforme/boutiques", headers=super_admin, json={
            "nom": nom or f"Boutique {n}", "ville": "Ouagadougou", "telephone": "25 00 00 00",
            "gerant_nom": f"Gérant {n}", "gerant_email": f"gerant{n}@test.bf",
            "gerant_mot_de_passe": "motdepasse-123", **extra})
        assert r.status_code == 201, r.text
        login = client.post("/api/auth/login", json={"email": f"gerant{n}@test.bf", "password": "motdepasse-123"})
        return r.json()["boutique"], {"Authorization": f"Bearer {login.json()['access_token']}"}
    return _creer


@pytest.fixture
def boutique_equipee(client, nouvelle_boutique):
    """Boutique avec une catégorie, un téléphone (stock 5), un service et un client."""
    b, h = nouvelle_boutique()
    cat = client.post("/api/categories", headers=h, json={"nom": "Smartphones"}).json()
    tel = client.post("/api/produits", headers=h, json={
        "reference": "T1", "nom": "Téléphone test", "categorie_id": cat["id"], "prix_vente": 100000,
        "prix_achat": 80000, "stock_initial": 5}).json()
    service = client.post("/api/produits", headers=h, json={
        "reference": "S1", "nom": "Main d'œuvre", "type_produit": "SER", "categorie_id": cat["id"],
        "prix_vente": 5000}).json()
    cli = client.post("/api/clients", headers=h, json={"nom": "Client Test", "telephone": "70 11 22 33",
                                                       "email": "client@test.bf"}).json()
    return {"boutique": b, "h": h, "cat": cat, "tel": tel, "service": service, "client": cli}
