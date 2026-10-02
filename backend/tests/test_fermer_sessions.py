"""Fermeture des sessions d'un compte SANS changer son mot de passe ni le désactiver :
par le DG (membre de sa boutique), par chacun (ses autres appareils), par le
super-administrateur (un compte ou toute une boutique), et journalisation.
Boutiques « internes » (test=True) : aucun message n'est envoyé."""
import time

MESSAGE_ADMIN = "Votre session a été fermée par un administrateur. Reconnectez-vous."
_n = {"i": 0}


def _membre(client, h, role="commercial"):
    """Crée un membre (mot de passe provisoire connu) ; renvoie (fiche, e-mail)."""
    _n["i"] += 1
    email = f"sess{_n['i']}-{time.time_ns() % 100000}@test.bf"
    r = client.post("/api/boutique/equipe", headers=h, json={
        "nom": f"Membre {_n['i']}", "email": email, "role": role, "mot_de_passe": "provisoire-123"})
    assert r.status_code == 201, r.text
    return r.json(), email


def _connexion(client, code, email, mot_de_passe):
    r = client.post("/api/auth/login", json={"code_boutique": code, "email": email, "password": mot_de_passe})
    client.cookies.clear()
    return r


def _journal(client, h):
    return client.get("/api/boutique/equipe/journal-identifiants", headers=h).json()


def test_dg_ferme_les_sessions_d_un_membre(client, nouvelle_boutique, connecter_membre):
    b, h = nouvelle_boutique(test=True)
    membre, email = _membre(client, h)
    hm, _ = connecter_membre(b["code_marchand"], email, "provisoire-123", "nouveau-mdp-456")
    assert client.get("/api/auth/me", headers=hm).status_code == 200

    r = client.post(f"/api/boutique/equipe/{membre['id']}/fermer-sessions", headers=h)
    assert r.status_code == 200, r.text
    # Ancien jeton refusé, avec le message dédié
    r = client.get("/api/auth/me", headers=hm)
    assert r.status_code == 401
    assert r.json()["detail"] == MESSAGE_ADMIN
    # Mot de passe inchangé et compte toujours actif : il se reconnecte normalement
    r = _connexion(client, b["code_marchand"], email, "nouveau-mdp-456")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["actif"] is True
    assert "sessions_fermees_par_admin_le" not in r.json()["user"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200
    # Le DG reste connecté
    assert client.get("/api/auth/me", headers=h).status_code == 200
    # Journal : qui, cible, IP
    ligne = next(l for l in _journal(client, h) if l["action"] == "SESSIONS_FERMEES")
    assert ligne["user_id"] == membre["id"] and ligne["par_role"] == "dg" and ligne["ip"]


def test_dg_ne_vise_pas_un_membre_d_une_autre_boutique_ni_lui_meme(client, nouvelle_boutique):
    _, h1 = nouvelle_boutique(test=True)
    b2, h2 = nouvelle_boutique(test=True)
    autre, _ = _membre(client, h2)
    assert client.post(f"/api/boutique/equipe/{autre['id']}/fermer-sessions", headers=h1).status_code == 404
    moi = client.get("/api/auth/me", headers=h1).json()["user"]
    assert client.post(f"/api/boutique/equipe/{moi['id']}/fermer-sessions", headers=h1).status_code == 400
    assert client.get("/api/auth/me", headers=h1).status_code == 200


def test_non_dg_refuse(client, nouvelle_boutique, connecter_membre):
    b, h = nouvelle_boutique(test=True)
    commercial, email = _membre(client, h)
    cible, _ = _membre(client, h, role="technicien")
    hc, _ = connecter_membre(b["code_marchand"], email, "provisoire-123", "nouveau-mdp-456")
    assert client.post(f"/api/boutique/equipe/{cible['id']}/fermer-sessions", headers=hc).status_code == 403
    # Ni les routes du super-administrateur
    assert client.post(f"/api/plateforme/boutiques/{b['id']}/fermer-sessions", headers=hc).status_code == 403


def test_autres_appareils_garde_la_session_courante(client, nouvelle_boutique):
    b, h = nouvelle_boutique(test=True)
    moi = client.get("/api/auth/me", headers=h).json()["user"]
    # Deuxième appareil
    r = _connexion(client, b["code_marchand"], moi["email"], "motdepasse-123")
    h_autre = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/auth/sessions/fermer-autres", headers=h)
    assert r.status_code == 200, r.text
    h_neuf = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=h_neuf).status_code == 200
    r_autre = client.get("/api/auth/me", headers=h_autre)
    assert r_autre.status_code == 401
    assert r_autre.json()["detail"] != MESSAGE_ADMIN  # fermé par soi-même, pas par un administrateur
    client.cookies.clear()  # cookie de session reposé pour le site : inutile ici (jetons Bearer)
    assert any(l["action"] == "SESSIONS_AUTRES_FERMEES" and l["par_id"] == moi["id"] for l in _journal(client, h_neuf))


def test_super_admin_ferme_un_compte_puis_toute_la_boutique(client, super_admin, nouvelle_boutique, connecter_membre):
    b, h = nouvelle_boutique(test=True)
    membre, email = _membre(client, h)
    hm, _ = connecter_membre(b["code_marchand"], email, "provisoire-123", "nouveau-mdp-456")
    # Autre boutique : ne doit pas être touchée
    _, h_autre = nouvelle_boutique(test=True)

    comptes = client.get(f"/api/plateforme/boutiques/{b['id']}/comptes", headers=super_admin)
    assert comptes.status_code == 200
    assert {c["id"] for c in comptes.json()} >= {membre["id"]}
    assert all("password_hash" not in c for c in comptes.json())

    # Un compte : le membre, pas le DG
    r = client.post(f"/api/plateforme/boutiques/{b['id']}/comptes/{membre['id']}/fermer-sessions", headers=super_admin)
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me", headers=hm).json()["detail"] == MESSAGE_ADMIN
    assert client.get("/api/auth/me", headers=h).status_code == 200
    # Compte d'une autre boutique via cette boutique : refusé
    autre_membre, _ = _membre(client, h_autre)
    assert client.post(f"/api/plateforme/boutiques/{b['id']}/comptes/{autre_membre['id']}/fermer-sessions",
                       headers=super_admin).status_code == 404
    # Ses propres sessions : refusé
    sa = client.get("/api/auth/me", headers=super_admin).json()["user"]
    assert client.post(f"/api/plateforme/boutiques/{b['id']}/comptes/{sa['id']}/fermer-sessions",
                       headers=super_admin).status_code == 400

    # Toute la boutique
    r = client.post(f"/api/plateforme/boutiques/{b['id']}/fermer-sessions", headers=super_admin)
    assert r.status_code == 200, r.text
    assert r.json()["nb_comptes"] == 2
    assert client.get("/api/auth/me", headers=h).json()["detail"] == MESSAGE_ADMIN
    # Le super-administrateur et l'autre boutique restent connectés
    assert client.get("/api/auth/me", headers=super_admin).status_code == 200
    assert client.get("/api/auth/me", headers=h_autre).status_code == 200
    # Le DG se reconnecte avec le même mot de passe
    dg_email = next(c["email"] for c in comptes.json() if c["role"] == "dg")
    assert _connexion(client, b["code_marchand"], dg_email, "motdepasse-123").status_code == 200

    # Journal (visible par l'administrateur)
    journal = client.get(f"/api/plateforme/journal-identifiants?boutique_id={b['id']}", headers=super_admin).json()
    actions = [l["action"] for l in journal]
    assert "SESSIONS_FERMEES" in actions and "SESSIONS_BOUTIQUE_FERMEES" in actions
    ligne = next(l for l in journal if l["action"] == "SESSIONS_BOUTIQUE_FERMEES")
    assert ligne["par_role"] == "super_admin" and ligne["details"]["nb_comptes"] == 2 and ligne["ip"]


def test_boutique_inconnue(client, super_admin):
    assert client.post("/api/plateforme/boutiques/inconnue/fermer-sessions", headers=super_admin).status_code == 404
    assert client.get("/api/plateforme/boutiques/inconnue/comptes", headers=super_admin).status_code == 404
