"""Déconnexion après inactivité : réglages (bornes, plateforme, boutique, DG qui ne peut
que réduire), refus côté serveur après inactivité, activité qui prolonge la session,
rafraîchissements automatiques qui ne comptent pas, 0 = désactivée.
L'horloge du module est simulée : aucun test n'attend réellement."""
import time

import pytest

import inactivite

FOND = {"X-Adlyn-Fond": "1"}
MESSAGE = "Session expirée après inactivité. Reconnectez-vous."


@pytest.fixture
def horloge(monkeypatch, client, super_admin):
    """Horloge contrôlée ; la durée de la plateforme est remise à 0 après le test."""
    debut = time.time()
    etat = {"t": debut}
    monkeypatch.setattr(inactivite, "_maintenant", lambda: etat["t"])
    inactivite.vider_cache()

    def avancer(secondes):
        etat["t"] += secondes

    yield avancer
    etat["t"] = debut  # retour à l'heure de départ : la session du super-admin est encore active
    client.put("/api/plateforme/parametres/inactivite", headers=super_admin, json={"secondes": 0})
    inactivite.vider_cache()


def _plateforme(client, super_admin, secondes):
    return client.put("/api/plateforme/parametres/inactivite", headers=super_admin, json={"secondes": secondes})


def test_bornes_des_reglages(client, super_admin, nouvelle_boutique, horloge):
    b, h = nouvelle_boutique(test=True)
    for valeur in (-1, 30, 59, 86_401):
        assert _plateforme(client, super_admin, valeur).status_code == 400
        assert client.put(f"/api/plateforme/boutiques/{b['id']}/inactivite", headers=super_admin,
                          json={"secondes": valeur}).status_code == 400
    assert _plateforme(client, super_admin, 60).json()["secondes"] == 60
    assert _plateforme(client, super_admin, 86_400).json()["secondes"] == 86_400
    assert _plateforme(client, super_admin, 0).json()["secondes"] == 0
    # Réservé au super-administrateur
    assert client.put("/api/plateforme/parametres/inactivite", headers=h, json={"secondes": 600}).status_code == 403


def test_dg_peut_seulement_reduire(client, super_admin, nouvelle_boutique, connecter_membre, horloge):
    b, h = nouvelle_boutique(test=True)
    _plateforme(client, super_admin, 1800)
    # Plus long que la plateforme, ou désactivé : refusé
    assert client.put("/api/boutique/inactivite", headers=h, json={"secondes": 3600}).status_code == 400
    assert client.put("/api/boutique/inactivite", headers=h, json={"secondes": 0}).status_code == 400
    r = client.put("/api/boutique/inactivite", headers=h, json={"secondes": 600})
    assert r.status_code == 200 and r.json()["effective"] == 600
    assert client.get("/api/auth/inactivite", headers=h).json() == {"secondes": 600, "avertissement_secondes": 60}
    # Valeur propre à la boutique (super-admin) plus courte que celle du DG : la plus courte l'emporte
    r = client.put(f"/api/plateforme/boutiques/{b['id']}/inactivite", headers=super_admin, json={"secondes": 300})
    assert r.status_code == 200 and r.json()["effective"] == 300
    assert client.put("/api/boutique/inactivite", headers=h, json={"secondes": 400}).status_code == 400
    # Retour à la valeur de la plateforme (None), puis le DG retire son réglage
    client.put(f"/api/plateforme/boutiques/{b['id']}/inactivite", headers=super_admin, json={"secondes": None})
    assert client.put("/api/boutique/inactivite", headers=h, json={"secondes": None}).json()["effective"] == 1800
    # Un membre non DG ne règle rien
    email = f"inact{time.time_ns() % 100000}@test.bf"
    client.post("/api/boutique/equipe", headers=h, json={"nom": "Vendeur", "email": email, "role": "commercial",
                                                          "mot_de_passe": "provisoire-123"})
    hv, _ = connecter_membre(b["code_marchand"], email, "provisoire-123", "nouveau-mdp-456")
    assert client.put("/api/boutique/inactivite", headers=hv, json={"secondes": 120}).status_code == 403
    # Durée courte : avertissement à 20 %
    client.put("/api/boutique/inactivite", headers=h, json={"secondes": 120})
    assert client.get("/api/auth/inactivite", headers=hv).json() == {"secondes": 120, "avertissement_secondes": 24}


def test_refus_serveur_apres_inactivite_et_activite_qui_prolonge(client, super_admin, nouvelle_boutique, horloge):
    _, h = nouvelle_boutique(test=True)
    _plateforme(client, super_admin, 300)
    assert client.get("/api/auth/me", headers=h).status_code == 200  # 1re requête : début du suivi
    # Activité régulière (toutes les 4 minutes) : la session dure bien plus que 5 minutes
    for _ in range(5):
        horloge(240)
        assert client.post("/api/auth/activite", headers=h).status_code == 200
    # Les rafraîchissements automatiques ne prolongent pas la session...
    horloge(240)
    assert client.get("/api/auth/me", headers={**h, **FOND}).status_code == 200
    horloge(200)  # 440 s sans activité réelle (> 300 + 60 de marge)
    r = client.get("/api/auth/me", headers={**h, **FOND})
    assert r.status_code == 401 and r.json()["detail"] == MESSAGE
    # ... et la session reste fermée, même avec une activité ensuite
    assert client.post("/api/auth/activite", headers=h).status_code == 401


def test_super_admin_soumis_a_la_regle_de_la_plateforme(client, super_admin, horloge):
    r = client.post("/api/auth/login", json={"email": "super@plateforme-test.bf", "password": "super-motdepasse"})
    client.cookies.clear()
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    _plateforme(client, super_admin, 60)
    assert client.get("/api/auth/me", headers=h).status_code == 200
    horloge(121)
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_zero_desactive(client, super_admin, nouvelle_boutique, horloge):
    _, h = nouvelle_boutique(test=True)
    _plateforme(client, super_admin, 0)
    assert client.get("/api/auth/me", headers=h).status_code == 200
    horloge(86_400 * 3)
    assert client.get("/api/auth/me", headers={**h, **FOND}).status_code == 200
    assert client.get("/api/auth/inactivite", headers=h).json() == {"secondes": 0, "avertissement_secondes": 0}
