"""Maintenance de la plateforme : annonce de la déconnexion de tous les utilisateurs,
phases (annonce, verrouillage, maintenance), blocage des sessions et de la connexion,
réactivation, invalidation des anciennes sessions, annulation, routes non bloquées."""
from datetime import timedelta

import pytest

import maintenance_plateforme as service
from db import db

URL_ADMIN = "/api/plateforme/deconnexion-generale"
URL_ETAT = "/api/maintenance/etat"


@pytest.fixture(autouse=True)
def etat_vierge(client):
    """Chaque test part d'une plateforme sans maintenance, et la laisse ainsi
    (les autres fichiers de tests ne doivent jamais être bloqués)."""
    def _effacer():
        client.portal.call(lambda: db.maintenance_plateforme.delete_many({}))
        service.vider_cache()
    _effacer()
    yield
    _effacer()


def _aller_a(client, phase):
    """Recale les dates de l'annonce en cours pour se placer dans la phase voulue."""
    m = service.maintenant()
    if phase == "verrouillage":
        dates = (m - timedelta(minutes=2), m - timedelta(seconds=1), m + timedelta(minutes=1))
    else:  # maintenance : échéance tout juste passée
        dates = (m - timedelta(minutes=5), m - timedelta(minutes=1), m - timedelta(milliseconds=1))
    maj = dict(zip(("annonce_le", "debut_verrouillage", "echeance"), (d.isoformat() for d in dates)))
    client.portal.call(lambda: db.maintenance_plateforme.update_one({"_id": service.ID_ETAT}, {"$set": maj}))
    service.vider_cache()


def _annoncer(client, super_admin, **extra):
    corps = {"message": "Mise à jour importante de la base", **extra}
    return client.post(URL_ADMIN, headers=super_admin, json=corps)


@pytest.fixture
def equipe(client, nouvelle_boutique, connecter_membre):
    """Boutique avec son DG et un vendeur (commercial) connectés, + identifiants du DG."""
    b, h_dg = nouvelle_boutique()
    email_dg = client.get("/api/auth/me", headers=h_dg).json()["user"]["email"]
    email_v = f"vendeur-{b['code_marchand'].lower()}@test.bf"
    r = client.post("/api/boutique/equipe", headers=h_dg, json={
        "nom": "Vendeur", "email": email_v, "mot_de_passe": "motdepasse-123", "role": "commercial"})
    assert r.status_code == 201, r.text
    h_v, _ = connecter_membre(b["code_marchand"], email_v)
    return {"boutique": b, "h_dg": h_dg, "h_v": h_v, "email_dg": email_dg}


def _connexion_dg(client, equipe):
    r = client.post("/api/auth/login", json={"code_boutique": equipe["boutique"]["code_marchand"],
                                             "email": equipe["email_dg"], "password": "motdepasse-123"})
    client.cookies.clear()
    return r


# ---------------------------------------------------------------------------
# Annonce : validation, réservée au super-admin, calendrier
# ---------------------------------------------------------------------------
def test_etat_public_sans_maintenance(client):
    r = client.get(URL_ETAT)
    assert r.status_code == 200
    etat = r.json()
    assert etat["phase"] == "aucune" and etat["active"] is False and etat["maintenant_serveur"]
    assert "message" not in etat


@pytest.mark.parametrize("corps", [
    {"message": ""}, {"message": "   "}, {},
    {"message": "x", "duree_minutes": 0}, {"message": "x", "duree_minutes": 121},
    {"message": "x", "part_verrouillage": -1}, {"message": "x", "part_verrouillage": 101},
    {"message": "x" * 1001},
])
def test_validation_de_l_annonce(client, super_admin, corps):
    assert client.post(URL_ADMIN, headers=super_admin, json=corps).status_code == 422


def test_annonce_reservee_au_super_admin(client, equipe):
    assert client.post(URL_ADMIN, headers=equipe["h_dg"], json={"message": "x"}).status_code == 403
    assert client.get(URL_ADMIN, headers=equipe["h_dg"]).status_code == 403
    assert client.post(URL_ADMIN, json={"message": "x"}).status_code == 401


def test_annonce_et_calendrier_par_defaut(client, super_admin):
    r = _annoncer(client, super_admin)
    assert r.status_code == 200, r.text
    etat = r.json()
    assert etat["phase"] == "annonce" and etat["duree_minutes"] == 5 and etat["part_verrouillage"] == 80
    # 5 minutes dont 80 % verrouillées : 1 minute de modale fermable, puis 4 minutes de verrouillage
    debut = service._date(etat["annonce_le"])
    assert service._date(etat["debut_verrouillage"]) - debut == timedelta(minutes=1)
    assert service._date(etat["echeance"]) - debut == timedelta(minutes=5)
    assert 290 <= etat["secondes_restantes"] <= 300
    assert etat["journal"][0]["action"] == "ANNONCE" and etat["annonce_par"]["email"] == "super@plateforme-test.bf"
    # État public : le message, l'heure du serveur, mais ni l'auteur ni le journal
    public = client.get(URL_ETAT).json()
    assert public["message"] == "Mise à jour importante de la base" and public["maintenant_serveur"]
    assert "annonce_par" not in public and "journal" not in public
    # Une seule annonce à la fois
    assert _annoncer(client, super_admin).status_code == 409


def test_calendrier_personnalise(client, super_admin):
    etat = _annoncer(client, super_admin, duree_minutes=10, part_verrouillage=50).json()
    debut = service._date(etat["annonce_le"])
    assert service._date(etat["debut_verrouillage"]) - debut == timedelta(minutes=5)
    assert service._date(etat["echeance"]) - debut == timedelta(minutes=10)


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------
def test_phases_avant_l_echeance_rien_n_est_bloque(client, super_admin, equipe):
    _annoncer(client, super_admin)
    assert client.get("/api/auth/me", headers=equipe["h_dg"]).status_code == 200
    _aller_a(client, "verrouillage")
    assert client.get(URL_ETAT).json()["phase"] == "verrouillage"
    # Écran verrouillé côté site, mais le serveur répond encore (déconnexion à l'échéance)
    assert client.get("/api/auth/me", headers=equipe["h_v"]).status_code == 200


def test_apres_echeance_dg_et_vendeur_refuses_super_admin_autorise(client, super_admin, equipe):
    _annoncer(client, super_admin)
    _aller_a(client, "maintenance")
    etat = client.get(URL_ETAT).json()
    assert etat["phase"] == "maintenance" and etat["secondes_restantes"] == 0
    for h in (equipe["h_dg"], equipe["h_v"]):
        r = client.get("/api/auth/me", headers=h)
        assert r.status_code == 503 and "maintenance" in r.json()["detail"].lower()
        assert client.get("/api/produits", headers=h).status_code == 503
    # Le super-administrateur n'est jamais bloqué (y compris dans une boutique)
    assert client.get("/api/auth/me", headers=super_admin).status_code == 200
    assert client.get("/api/plateforme/boutiques", headers=super_admin).status_code == 200
    assert client.get("/api/produits", headers={**super_admin, "X-Boutique-Id": equipe["boutique"]["id"]}).status_code == 200


def test_connexion_refusee_pendant_la_maintenance(client, super_admin, equipe):
    _annoncer(client, super_admin)
    _aller_a(client, "maintenance")
    r = _connexion_dg(client, equipe)
    assert r.status_code == 503 and "maintenance" in r.json()["detail"].lower()
    # Mot de passe oublié (code par WhatsApp / SMS / e-mail) : refusé aussi
    corps = {"code_boutique": equipe["boutique"]["code_marchand"], "identifiant": equipe["email_dg"]}
    assert client.post("/api/auth/mot-de-passe-oublie", json=corps).status_code == 503
    assert client.post("/api/auth/mot-de-passe-oublie/confirmer",
                       json={**corps, "code": "123456", "nouveau": "nouveau-mdp-789"}).status_code == 503
    # Le super-administrateur se connecte normalement
    r = client.post("/api/auth/login", json={"email": "super@plateforme-test.bf", "password": "super-motdepasse"})
    client.cookies.clear()
    assert r.status_code == 200


def test_reactivation_et_sessions_anterieures_invalides(client, super_admin, equipe):
    _annoncer(client, super_admin)
    # Réactivation impossible avant l'échéance (il faut annuler)
    assert client.post(f"{URL_ADMIN}/reactiver", headers=super_admin).status_code == 409
    _aller_a(client, "maintenance")
    # Une nouvelle annonce exige d'abord la réactivation
    assert _annoncer(client, super_admin).status_code == 409
    r = client.post(f"{URL_ADMIN}/reactiver", headers=super_admin)
    assert r.status_code == 200, r.text
    etat = r.json()
    assert etat["phase"] == "aucune" and etat["sessions_valides_apres"]
    assert [j["action"] for j in etat["journal"][:2]] == ["REACTIVATION", "ANNONCE"]
    assert client.get(URL_ETAT).json()["phase"] == "aucune"
    # Les sessions ouvertes avant l'échéance restent invalides : chacun se reconnecte
    for h in (equipe["h_dg"], equipe["h_v"]):
        r = client.get("/api/auth/me", headers=h)
        assert r.status_code == 401 and "reconnectez" in r.json()["detail"]
    r = _connexion_dg(client, equipe)
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200
    # Le super-administrateur garde sa session
    assert client.get("/api/auth/me", headers=super_admin).status_code == 200


def test_annulation_avant_echeance_personne_n_est_deconnecte(client, super_admin, equipe):
    assert client.post(f"{URL_ADMIN}/annuler", headers=super_admin).status_code == 409  # rien à annuler
    _annoncer(client, super_admin)
    _aller_a(client, "verrouillage")
    r = client.post(f"{URL_ADMIN}/annuler", headers=super_admin)
    assert r.status_code == 200 and r.json()["phase"] == "aucune"
    assert r.json()["journal"][0]["action"] == "ANNULATION"
    assert client.get(URL_ETAT).json()["phase"] == "aucune"
    for h in (equipe["h_dg"], equipe["h_v"]):
        assert client.get("/api/auth/me", headers=h).status_code == 200
    # Après l'échéance, on ne peut plus annuler : il faut réactiver
    _annoncer(client, super_admin)
    _aller_a(client, "maintenance")
    assert client.post(f"{URL_ADMIN}/annuler", headers=super_admin).status_code == 409


def test_webhooks_et_site_public_non_bloques(client, super_admin, nouvelle_boutique):
    b, _ = nouvelle_boutique(options_par_defaut=True)
    jeton = client.post(f"/api/plateforme/caisse-aizenta/boutiques/{b['id']}/jeton", headers=super_admin).json()["jeton"]
    _annoncer(client, super_admin)
    _aller_a(client, "maintenance")
    # Webhook de la Caisse Aizenta (jeton de la boutique) : reçu normalement
    client.portal.call(lambda: db.caisse_receptions.delete_many({}))
    envoi = {"version": 1, "code_boutique": b["code_marchand"], "source": "Loois", "base": "AIZ_TEST",
             "genere_le": "2026-09-30T18:00:00Z", "periode": {"du": "2026-09-01", "au": "2026-09-30"},
             "operations": [{"id": "MNT-1", "date_heure": "2026-09-15T09:00:00", "montant": 1000, "caissier": "AWA",
                             "mode_paiement": "ESPECES", "mode_paiement_code": "1", "mode_paiement_libelle": "Espèces"}]}
    r = client.post("/api/webhooks/caisse-aizenta", headers={"Authorization": f"Bearer {jeton}"}, json=envoi)
    assert r.status_code == 200, r.text
    # Webhook PawaPay : répond selon son propre secret, jamais « maintenance »
    assert client.post("/api/paiements/webhooks/depots/faux-secret", json={}).status_code == 403
    # Portail public, catalogue public, santé du serveur
    assert client.get("/api/public/boutiques").status_code == 200
    assert client.get(f"/api/public/b/{b['slug']}").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get(URL_ETAT).status_code == 200
