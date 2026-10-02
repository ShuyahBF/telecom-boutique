"""Sessions simultanées limitées : 5 par compte par défaut (réglable de 1 à 20), la plus
ancienne fermée à la connexion suivante avec un message clair, liste et fermeture d'une
session (Mon compte et super-admin), déconnexion qui libère la place.
L'horloge du module est simulée : aucun test n'attend réellement."""
import time

import pytest

import sessions_actives

MESSAGE_LIMITE = "Session fermée : nombre maximal d'appareils atteint pour ce compte."


@pytest.fixture
def horloge(monkeypatch, client, super_admin):
    etat = {"t": time.time()}
    monkeypatch.setattr(sessions_actives, "_maintenant", lambda: etat["t"])
    sessions_actives.vider_cache()

    def avancer(secondes=5):
        etat["t"] += secondes

    yield avancer
    client.put("/api/plateforme/parametres/sessions", headers=super_admin, json={"valeur": 5})
    sessions_actives.vider_cache()


def _connexion(client, b, email, agent="Mozilla/5.0 (Linux; Android 14) Chrome/120.0 Mobile Safari/537.36"):
    r = client.post("/api/auth/login", headers={"User-Agent": agent},
                    json={"code_boutique": b["code_marchand"], "email": email, "password": "motdepasse-123"})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()


def _email_dg(client, h):
    return client.get("/api/auth/me", headers=h).json()["user"]["email"]


def test_sixieme_connexion_ferme_la_plus_ancienne(client, nouvelle_boutique, horloge):
    b, h0 = nouvelle_boutique()  # 1re session : celle de la création de la boutique
    email = f"gerant{_numero(b)}@test.bf"
    jetons = [h0]
    for _ in range(4):  # 2e à 5e connexions : rien n'est fermé
        horloge()
        h, session = _connexion(client, b, email)
        assert session["sessions_fermees"] == 0
        jetons.append(h)
    # Le 1er appareil reste actif (sa dernière activité est mise à jour)
    horloge(120)
    assert client.get("/api/auth/me", headers=jetons[0]).status_code == 200
    horloge()
    h6, session = _connexion(client, b, email)
    assert session["sessions_fermees"] == 1
    # La session dont la DERNIÈRE ACTIVITÉ est la plus ancienne (la 2e) est fermée, avec le message
    r = client.get("/api/auth/me", headers=jetons[1])
    assert r.status_code == 401 and r.json()["detail"] == MESSAGE_LIMITE
    for h in (jetons[0], *jetons[2:], h6):
        assert client.get("/api/auth/me", headers=h).status_code == 200
    assert len(client.get("/api/auth/sessions", headers=h6).json()["sessions"]) == 5


def _numero(b):
    # Le DG de la boutique de test n°N a pour e-mail gerantN@test.bf (conftest.py)
    return b["nom"].split()[-1]


def test_liste_et_fermeture_d_une_session(client, nouvelle_boutique, horloge):
    b, _ = nouvelle_boutique()
    email = f"gerant{_numero(b)}@test.bf"
    h1, _ = _connexion(client, b, email, agent="Mozilla/5.0 (Windows NT 10.0) Firefox/128.0")
    horloge()
    h2, _ = _connexion(client, b, email)
    sessions = client.get("/api/auth/sessions", headers=h2).json()["sessions"]
    courante = next(s for s in sessions if s["courante"])
    autre = next(s for s in sessions if s["appareil"] == "Firefox sur Windows")
    assert courante["appareil"] == "Chrome sur Android" and courante["ip"] and courante["ouverte_le"]
    assert autre["derniere_activite"] and not autre["courante"]
    # Fermer la session de cet appareil : refusé (utiliser Déconnexion)
    assert client.post(f"/api/auth/sessions/{courante['id']}/fermer", headers=h2).status_code == 400
    # Un autre compte ne peut pas fermer cette session
    _, h_autre = nouvelle_boutique()
    assert client.post(f"/api/auth/sessions/{autre['id']}/fermer", headers=h_autre).status_code == 404
    r = client.post(f"/api/auth/sessions/{autre['id']}/fermer", headers=h2)
    assert r.status_code == 200 and "Firefox" in r.json()["message"]
    r = client.get("/api/auth/me", headers=h1)
    assert r.status_code == 401 and "autre appareil" in r.json()["detail"]
    assert client.post(f"/api/auth/sessions/{autre['id']}/fermer", headers=h2).status_code == 404
    # Déconnexion : la session libère sa place
    nb = len(client.get("/api/auth/sessions", headers=h2).json()["sessions"])
    h3, _ = _connexion(client, b, email)
    assert len(client.get("/api/auth/sessions", headers=h2).json()["sessions"]) == nb + 1
    client.post("/api/auth/logout", headers=h3)
    assert len(client.get("/api/auth/sessions", headers=h2).json()["sessions"]) == nb


def test_super_admin_voit_et_ferme_une_session(client, super_admin, nouvelle_boutique, horloge):
    b, h = nouvelle_boutique()
    email = f"gerant{_numero(b)}@test.bf"
    h2, session = _connexion(client, b, email)
    dg_id = session["user"]["id"]
    url = f"/api/plateforme/boutiques/{b['id']}/sessions"
    assert client.get(url, headers=h).status_code == 403
    donnees = client.get(url, headers=super_admin).json()
    assert donnees["comptes"][dg_id]["nb"] == 2 and donnees["limite"] == 5
    cible = next(s for s in donnees["comptes"][dg_id]["sessions"] if s["derniere_activite"])
    # Une session d'une autre boutique n'est pas fermable depuis celle-ci
    autre, _ = nouvelle_boutique()
    assert client.post(f"/api/plateforme/boutiques/{autre['id']}/sessions/{cible['id']}/fermer",
                       headers=super_admin).status_code == 404
    r = client.post(f"{url}/{cible['id']}/fermer", headers=super_admin)
    assert r.status_code == 200, r.text
    statuts = sorted(client.get("/api/auth/me", headers=x).status_code for x in (h, h2))
    assert statuts == [200, 401]
    assert client.get(url, headers=super_admin).json()["comptes"][dg_id]["nb"] == 1
    journal = client.get("/api/plateforme/journal-identifiants", headers=super_admin,
                         params={"boutique_id": b["id"]}).json()
    assert any(l["action"] == "SESSION_FERMEE_ADMIN" for l in journal)


def test_reglage_du_maximum(client, super_admin, nouvelle_boutique, horloge):
    url = "/api/plateforme/parametres/sessions"
    assert client.get(url, headers=super_admin).json() == {"valeur": 5, "min": 1, "max": 20}
    for invalide in (0, 21):
        assert client.put(url, headers=super_admin, json={"valeur": invalide}).status_code == 400
    b, h = nouvelle_boutique()
    assert client.put(url, headers=h, json={"valeur": 3}).status_code == 403
    assert client.put(url, headers=super_admin, json={"valeur": 20}).json()["valeur"] == 20
    assert client.put(url, headers=super_admin, json={"valeur": 1}).json()["valeur"] == 1
    horloge()
    h2, session = _connexion(client, b, f"gerant{_numero(b)}@test.bf")
    assert session["sessions_fermees"] == 1
    assert client.get("/api/auth/me", headers=h).json()["detail"] == MESSAGE_LIMITE
    assert client.get("/api/auth/me", headers=h2).status_code == 200
