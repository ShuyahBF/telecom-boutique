"""Règles d'accès des boutiques (adresses IP, appareils, liste blanche avec « * »)
et journal des connexions."""
import acces


def test_regles_pures():
    ip = lambda v, a="AUTORISER": {"type": "IP", "valeur": v, "action": a}  # noqa: E731
    app = lambda v, a="AUTORISER": {"type": "APPAREIL", "valeur": v, "action": a}  # noqa: E731
    assert acces.verdict([], "1.2.3.4", "")[0]  # aucune règle : tout le monde
    assert acces.verdict([ip("196.28.*")], "196.28.245.1", "")[0]
    assert not acces.verdict([ip("196.28.*")], "41.1.2.3", "")[0]  # hors liste blanche
    assert acces.verdict([ip("*")], "41.1.2.3", "")[0]  # « * » : tout le monde
    assert not acces.verdict([ip("*"), ip("41.1.2.3", "INTERDIRE")], "41.1.2.3", "")[0]  # l'interdiction l'emporte
    assert acces.verdict([app("ABCDEF1234567890")], "9.9.9.9", "ABCDEF1234567890")[0]  # appareil autorisé
    assert not acces.verdict([app("ABCDEF1234567890", "INTERDIRE")], "9.9.9.9", "ABCDEF1234567890")[0]


def _login(client, b, n, **en_tetes):
    return client.post("/api/auth/login", headers=en_tetes, json={
        "code_boutique": b["code_marchand"], "email": f"gerant{n}@test.bf", "password": "motdepasse-123"})


def test_journal_et_interdiction(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique()
    n = b["nom"].split()[-1]
    # Échec puis connexion réussie depuis 41.1.1.1 (en-tête du proxy)
    client.post("/api/auth/login", headers={"X-Forwarded-For": "41.1.1.1"}, json={
        "code_boutique": b["code_marchand"], "email": f"gerant{n}@test.bf", "password": "mauvais"})
    r = _login(client, b, n, **{"X-Forwarded-For": "41.1.1.1"})
    assert r.status_code == 200
    assert "adlyn_appareil=" in r.headers.get("set-cookie", "")  # l'appareil reçoit un identifiant
    client.cookies.clear()
    journal = client.get("/api/boutique/acces/journal", headers=h).json()["lignes"]
    assert [x["resultat"] for x in journal[:2]] == ["SUCCES", "ECHEC"] and journal[0]["ip"] == "41.1.1.1"

    # Le DG interdit cette adresse depuis la ligne du journal
    r = client.post(f"/api/boutique/acces/journal/{journal[0]['id']}/regle", headers={**h, "X-Forwarded-For": "10.0.0.5"},
                    json={"type": "IP", "action": "INTERDIRE"})
    assert r.status_code == 201, r.text
    r = _login(client, b, n, **{"X-Forwarded-For": "41.1.1.1"})
    assert r.status_code == 403 and "interdite" in r.json()["detail"]
    client.cookies.clear()
    assert client.get("/api/boutique/acces/journal", headers=h, params={"resultat": "BLOQUE"}).json()["lignes"]
    # Les requêtes d'une session déjà ouverte depuis cette adresse sont coupées aussi
    assert client.get("/api/produits", headers={**h, "X-Forwarded-For": "41.1.1.1"}).status_code == 403
    # Le super-admin n'est jamais bloqué
    assert client.get("/api/plateforme/boutiques", headers={**super_admin, "X-Forwarded-For": "41.1.1.1"}).status_code == 200


def test_liste_blanche_et_protection_du_dg(client, nouvelle_boutique):
    b, h = nouvelle_boutique()
    n = b["nom"].split()[-1]
    ici = {**h, "X-Forwarded-For": "196.28.10.20"}
    # Une liste blanche qui exclut le DG lui-même est refusée
    r = client.post("/api/boutique/acces/regles", headers=ici, json={"type": "IP", "valeur": "41.*", "action": "AUTORISER"})
    assert r.status_code == 400 and "bloquerait" in r.json()["detail"]
    assert client.post("/api/boutique/acces/regles", headers=ici,
                       json={"type": "IP", "valeur": "196.28.*", "action": "AUTORISER", "libelle": "Wifi boutique"}).status_code == 201
    # Hors de la liste blanche : refusé ; dedans : accepté
    assert _login(client, b, n, **{"X-Forwarded-For": "41.2.2.2"}).status_code == 403
    client.cookies.clear()
    assert _login(client, b, n, **{"X-Forwarded-For": "196.28.99.1"}).status_code == 200
    client.cookies.clear()
    # « * » dans la liste blanche : tout le monde
    client.post("/api/boutique/acces/regles", headers=ici, json={"type": "IP", "valeur": "*", "action": "AUTORISER"})
    assert _login(client, b, n, **{"X-Forwarded-For": "41.2.2.2"}).status_code == 200
    client.cookies.clear()
    # Valeurs invalides refusées ; réservé au DG
    assert client.post("/api/boutique/acces/regles", headers=ici, json={"type": "IP", "valeur": "abc;rm", "action": "INTERDIRE"}).status_code == 400
    regles = client.get("/api/boutique/acces", headers=ici).json()["regles"]
    assert {r["valeur"] for r in regles} == {"196.28.*", "*"}
    assert client.delete(f"/api/boutique/acces/regles/{regles[0]['id']}", headers=ici).status_code == 200
