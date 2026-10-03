"""Lot 25 — onglet « Usage » de la plateforme : historique des connexions (IP réelle),
accès réservé au super-administrateur, pastilles de présence, blocages d'IP (ce compte /
tous) et de comptes, levée des blocages, auto-blocage interdit, journal des actions,
contact public de la page « Accès momentanément suspendu »."""
import time

import pytest

import blocages_acces
import sessions_actives
from db import db

MDP = "motdepasse-123"
UA = "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0"


def _nettoyer(client):
    """Aucun blocage ne doit survivre à un test (il bloquerait les suivants)."""
    client.portal.call(lambda: db.usage_blocages.delete_many({}))
    blocages_acces.vider_cache()
    sessions_actives.vider_cache()


@pytest.fixture(autouse=True)
def propre(client):
    _nettoyer(client)
    yield
    _nettoyer(client)


def _ip(ip):
    """En-têtes d'une requête passée par le proxy de Render (adresse réelle du visiteur)."""
    return {"X-Forwarded-For": ip, "User-Agent": UA}


def _email_dg(b):
    # Le DG de la boutique de test n°N a pour e-mail gerantN@test.bf (conftest.py)
    return f"gerant{b['nom'].split()[-1]}@test.bf"


def _connexion(client, b, ip, email=None):
    r = client.post("/api/auth/login", headers=_ip(ip),
                    json={"code_boutique": b["code_marchand"], "identifiant": email or _email_dg(b), "password": MDP})
    client.cookies.clear()
    return r


def _jeton(client, b, ip):
    r = _connexion(client, b, ip)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", **_ip(ip)}


def _id_dg(client, h):
    return client.get("/api/auth/me", headers=h).json()["user"]["id"]


def _est_suspendu(r):
    return r.status_code == 403 and isinstance(r.json()["detail"], dict) \
        and r.json()["detail"]["code"] == "acces_suspendu"


def test_historique_ip_reelle_methode_et_boutique(client, nouvelle_boutique):
    b, _ = nouvelle_boutique()
    _jeton(client, b, "198.51.100.7")
    ligne = client.portal.call(lambda: db.usage_connexions.find_one({"ip": "198.51.100.7"}, sort=[("date", -1)]))
    assert ligne and ligne["etat"] == "reussie" and ligne["methode"] == "email"
    assert ligne["sid"] and ligne["appareil"] == "Chrome sur Windows"
    assert ligne["boutique_id"] == b["id"] and ligne["role"] == "dg"
    # Connexion par numéro de téléphone : méthode « telephone »
    client.portal.call(lambda: db.users.update_one({"email": _email_dg(b)}, {"$set": {"telephone": "+22670998877"}}))
    assert _connexion(client, b, "198.51.100.17", email="70 99 88 77").status_code == 200
    assert client.portal.call(lambda: db.usage_connexions.find_one({"ip": "198.51.100.17"}))["methode"] == "telephone"


def test_onglet_reserve_au_super_admin(client, super_admin, nouvelle_boutique):
    b, dg = nouvelle_boutique()
    for url in ("/api/plateforme/usage/connexions", "/api/plateforme/usage/blocages",
                "/api/plateforme/usage/journal", "/api/plateforme/usage/contact"):
        assert client.get(url, headers=dg).status_code == 403
    assert client.post("/api/plateforme/usage/blocages", headers=dg,
                       json={"type": "ip", "ip": "203.0.113.99"}).status_code == 403
    assert client.get("/api/plateforme/usage/connexions").status_code == 401
    _jeton(client, b, "198.51.100.8")
    r = client.get("/api/plateforme/usage/connexions", params={"q": "198.51.100.8"}, headers=super_admin)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["par_page"] == 50 and data["total"] == 1
    ligne = data["items"][0]
    assert ligne["ip"] == "198.51.100.8" and ligne["compte"]["identifiant"] == _email_dg(b)
    assert ligne["boutique"]["nom"] == b["nom"] and ligne["role_libelle"] == "DG"
    # Boutique neuve : 14 jours d'essai -> abonnement « actif (essai) »
    assert ligne["abonnement"]["statut"] == "actif" and ligne["abonnement"]["formule"] == "Essai gratuit"
    assert ligne["ip_etat"] == "autorisee" and ligne["presence"]["couleur"] == "vert"
    # Filtres : abonnement, boutique, période
    par = {"q": "198.51.100.8"}
    assert client.get("/api/plateforme/usage/connexions", params={**par, "abonnement": "expire"},
                      headers=super_admin).json()["total"] == 0
    assert client.get("/api/plateforme/usage/connexions", params={**par, "abonnement": "actif"},
                      headers=super_admin).json()["total"] == 1
    assert client.get("/api/plateforme/usage/connexions", params={**par, "boutique": b["code_marchand"]},
                      headers=super_admin).json()["total"] == 1
    assert client.get("/api/plateforme/usage/connexions", params={**par, "du": "2000-01-01", "au": "2000-01-02"},
                      headers=super_admin).json()["total"] == 0


def test_presence_vert_orange_rouge(client, super_admin, nouvelle_boutique):
    b, _ = nouvelle_boutique()
    _jeton(client, b, "198.51.100.9")
    sid = client.portal.call(lambda: db.usage_connexions.find_one({"ip": "198.51.100.9"}))["sid"]
    fond = {**super_admin, "X-Adlyn-Fond": "1"}

    def couleur(il_y_a):
        client.portal.call(lambda: db.sessions_activite.update_one(
            {"_id": sid}, {"$set": {"activite_le": time.time() - il_y_a}}))
        r = client.get("/api/plateforme/usage/presence", params={"sids": sid}, headers=fond)
        assert r.status_code == 200
        return r.json()["presence"][sid]["couleur"]

    assert couleur(60) == "vert"
    assert couleur(7 * 60) == "orange"
    assert couleur(11 * 60) == "rouge"
    client.portal.call(lambda: db.sessions_activite.update_one({"_id": sid}, {"$set": {"fermee": True}}))
    assert couleur(10) == "rouge"  # déconnecté


def test_blocage_ip_pour_tous_les_comptes(client, super_admin, nouvelle_boutique):
    ip = "203.0.113.10"
    a, _ = nouvelle_boutique()
    b, _ = nouvelle_boutique()
    session_a = _jeton(client, a, ip)
    assert client.get("/api/auth/me", headers=session_a).status_code == 200
    r = client.post("/api/plateforme/usage/blocages", headers=super_admin,
                    json={"type": "ip", "ip": ip, "tous_comptes": True, "libelle": "Cybercafé test"})
    assert r.status_code == 200, r.text
    assert r.json()["portee"] == "tous" and r.json()["sessions_fermees"] >= 1
    # Session en cours fermée : la requête suivante reçoit la page « accès suspendu »
    r = client.get("/api/auth/me", headers=session_a)
    assert _est_suspendu(r) and "Contactez l'Administrateur" in r.json()["detail"]["message"]
    # Nouvelle connexion refusée, pour les DEUX boutiques, et tentative notée « refusée »
    assert _est_suspendu(_connexion(client, a, ip))
    assert _est_suspendu(_connexion(client, b, ip))
    assert client.portal.call(lambda: db.usage_connexions.find_one(
        {"boutique_id": b["id"], "etat": "refusee", "motif": "ip"}))
    # Demande d'ouverture de boutique (lien de parrainage) depuis cette IP : refusée aussi
    r = client.post(f"/api/public/parrainage/{a['code_marchand']}/demande", headers=_ip(ip), json={
        "nom": "Boutique Refusée", "ville": "Ouagadougou", "dg_nom": "Awa Test", "dg_email": "awa@exemple.bf",
        "dg_telephone": "+22670112233", "accepte_invitation": True, "accepte_conditions": True})
    assert _est_suspendu(r)
    # Depuis une autre IP : connexion normale
    assert _connexion(client, a, "203.0.113.11").status_code == 200
    # Le tableau affiche l'IP bloquée pour tous, et les lignes refusées
    lignes = client.get("/api/plateforme/usage/connexions", params={"q": ip}, headers=super_admin).json()["items"]
    assert lignes and all(ligne["ip_etat"] == "bloquee_tous" for ligne in lignes)
    assert any(ligne["etat"] == "refusee" for ligne in lignes)
    refusees = client.get("/api/plateforme/usage/connexions", params={"q": ip, "etat": "refusee"},
                          headers=super_admin).json()
    assert refusees["total"] >= 3 and all(ligne["etat"] == "refusee" for ligne in refusees["items"])
    # Autoriser : le blocage est levé, la connexion redevient possible
    r = client.post("/api/plateforme/usage/autoriser", headers=super_admin, json={"type": "ip", "ip": ip})
    assert r.status_code == 200 and r.json()["leves"] == 1
    assert _connexion(client, a, ip).status_code == 200
    # L'ancienne session (fermée) demande simplement de se reconnecter
    r = client.get("/api/auth/me", headers=session_a)
    assert r.status_code == 401 and "reconnectez-vous" in r.json()["detail"]


def test_blocage_ip_pour_ce_compte_seulement(client, super_admin, nouvelle_boutique):
    ip = "203.0.113.20"
    a, ha = nouvelle_boutique()
    b, _ = nouvelle_boutique()
    r = client.post("/api/plateforme/usage/blocages", headers=super_admin,
                    json={"type": "ip", "ip": ip, "user_id": _id_dg(client, ha), "tous_comptes": False})
    assert r.status_code == 200 and r.json()["portee"] == "compte"
    assert _est_suspendu(_connexion(client, a, ip))
    assert _connexion(client, b, ip).status_code == 200
    assert _connexion(client, a, "203.0.113.21").status_code == 200
    # Liste « Blocages en cours » (compte et boutique visés) puis levée
    liste = client.get("/api/plateforme/usage/blocages", headers=super_admin).json()["blocages"]
    assert len(liste) == 1 and liste[0]["boutique_nom"] == a["nom"]
    assert client.post(f"/api/plateforme/usage/blocages/{liste[0]['id']}/lever",
                       headers=super_admin).status_code == 200
    assert _connexion(client, a, ip).status_code == 200
    assert client.get("/api/plateforme/usage/blocages", headers=super_admin).json()["blocages"] == []


def test_blocage_du_compte(client, super_admin, nouvelle_boutique):
    a, ha = nouvelle_boutique()
    uid = _id_dg(client, ha)
    session = _jeton(client, a, "203.0.113.30")
    r = client.post("/api/plateforme/usage/blocages", headers=super_admin, json={"type": "compte", "user_id": uid})
    assert r.status_code == 200, r.text
    assert _est_suspendu(client.get("/api/auth/me", headers=session))
    assert _est_suspendu(client.get("/api/auth/me", headers=ha))  # toutes ses sessions
    assert _est_suspendu(_connexion(client, a, "203.0.113.31"))
    assert client.portal.call(lambda: db.usage_connexions.find_one({"user_id": uid, "etat": "refusee",
                                                                    "motif": "compte"}))
    assert client.post("/api/plateforme/usage/blocages", headers=super_admin,
                       json={"type": "compte", "user_id": uid}).status_code == 409
    r = client.post("/api/plateforme/usage/autoriser", headers=super_admin, json={"type": "compte", "user_id": uid})
    assert r.json()["leves"] == 1
    assert _connexion(client, a, "203.0.113.31").status_code == 200


def test_super_admin_ne_peut_pas_se_bloquer(client, super_admin):
    admin_id = client.get("/api/auth/me", headers=super_admin).json()["user"]["id"]
    r = client.post("/api/plateforme/usage/blocages", headers=super_admin, json={"type": "compte", "user_id": admin_id})
    assert r.status_code == 400 and "super-administrateur" in r.json()["detail"]
    r = client.post("/api/plateforme/usage/blocages", headers=super_admin,
                    json={"type": "ip", "ip": "203.0.113.40", "user_id": admin_id, "tous_comptes": False})
    assert r.status_code == 400
    # Son adresse IP actuelle (vue derrière le proxy) ne peut pas être bloquée
    r = client.post("/api/plateforme/usage/blocages", headers={**super_admin, **_ip("203.0.113.41")},
                    json={"type": "ip", "ip": "203.0.113.41", "tous_comptes": True})
    assert r.status_code == 400 and "vous-même" in r.json()["detail"]
    # Adresse invalide ou motif « * » : refusé
    assert client.post("/api/plateforme/usage/blocages", headers=super_admin,
                       json={"type": "ip", "ip": "203.0.*"}).status_code == 400
    # Une IP bloquée pour tous ne bloque jamais le super-administrateur
    assert client.post("/api/plateforme/usage/blocages", headers=super_admin,
                       json={"type": "ip", "ip": "203.0.113.42"}).status_code == 200
    r = client.post("/api/auth/login", headers=_ip("203.0.113.42"),
                    json={"identifiant": "super@plateforme-test.bf", "password": "super-motdepasse"})
    client.cookies.clear()
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}", **_ip("203.0.113.42")}
    assert client.get("/api/plateforme/usage/blocages", headers=h).status_code == 200
    client.post("/api/auth/logout", headers=h)  # libère la place (sessions simultanées limitées)
    assert client.portal.call(lambda: db.usage_blocages.count_documents({"type": "compte"})) == 0


def test_journal_des_actions_et_contact(client, super_admin, nouvelle_boutique):
    b, ha = nouvelle_boutique()
    uid = _id_dg(client, ha)
    client.post("/api/plateforme/usage/blocages", headers=super_admin,
                json={"type": "compte", "user_id": uid, "motif": "Essai"})
    client.post("/api/plateforme/usage/autoriser", headers=super_admin, json={"type": "compte", "user_id": uid})
    actions = client.get("/api/plateforme/usage/journal", headers=super_admin).json()["actions"]
    noms = [x["action"] for x in actions]
    assert "Compte bloqué" in noms and "Blocage levé (accès autorisé)" in noms
    assert all(x["par"] == "super@plateforme-test.bf" and x["date"] for x in actions)
    # Contact de la page de blocage : réglé par le super-admin, lisible sans connexion
    assert client.get("/api/acces-suspendu/contact").json() == {"email": "", "whatsapp": ""}
    assert client.put("/api/plateforme/usage/contact", headers=super_admin,
                      json={"email": "pas-un-email"}).status_code == 400
    # Le DG (ses anciennes sessions ont été fermées par le blocage : il se reconnecte) : 403
    dg = _jeton(client, b, "198.51.100.50")
    assert client.put("/api/plateforme/usage/contact", headers=dg, json={"email": "a@b.bf"}).status_code == 403
    r = client.put("/api/plateforme/usage/contact", headers=super_admin,
                   json={"email": "contact@exemple.bf", "whatsapp": "+226 70 00 00 00"})
    assert r.status_code == 200
    assert client.get("/api/acces-suspendu/contact").json() == {"email": "contact@exemple.bf",
                                                                 "whatsapp": "+226 70 00 00 00"}
    client.portal.call(lambda: db.parametres_plateforme.delete_many({"_id": blocages_acces.ID_CONTACT}))
