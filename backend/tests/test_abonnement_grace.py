"""Période de grâce après une échéance impayée (3 jours par défaut, réglable par boutique),
bouton « Renouveler la grâce (+3 j) » limité à 3 fois, coupure automatique côté serveur,
routes de paiement toujours ouvertes, super-admin et boutiques de test jamais coupés."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import abonnement_grace
from abonnements import aujourd_hui
from config import get_settings

AUJ = aujourd_hui()
MESSAGE = "Abonnement expiré"


def fixer_echeance(client, super_admin, b, jours):
    r = client.patch(f"/api/plateforme/abonnements/boutiques/{b['id']}", headers=super_admin,
                     json={"echeance": (AUJ + timedelta(days=jours)).isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def coupe(r) -> bool:
    return r.status_code == 403 and r.json()["detail"].startswith(MESSAGE)


def test_grace_par_defaut_puis_coupure(client, super_admin, nouvelle_boutique, connecter_membre):
    b, h = nouvelle_boutique()
    email = f"vendeur-grace-{b['code_marchand'].lower()}@test.bf"
    client.post("/api/boutique/equipe", headers=h, json={"nom": "Vendeur", "email": email,
                                                          "mot_de_passe": "motdepasse-123", "role": "commercial"})
    hc, _ = connecter_membre(b["code_marchand"], email)
    # Échéance dépassée de 3 jours : dernier jour de grâce (3 jours par défaut), accès normal
    e = fixer_echeance(client, super_admin, b, -3)
    assert e["grace"]["en_grace"] and e["grace"]["jours_grace_restants"] == 1 and not e["grace"]["coupe"]
    assert client.get("/api/produits", headers=h).status_code == 200
    me = client.get("/api/auth/me", headers=hc).json()
    assert me["boutique"]["abonnement_grace"]["en_grace"] is True
    # Échéance dépassée de 4 jours : grâce terminée, DG et vendeur coupés côté serveur
    fixer_echeance(client, super_admin, b, -4)
    for entetes in (h, hc):
        r = client.get("/api/produits", headers=entetes)
        assert coupe(r), r.text
        assert r.headers.get("x-adlyn-code") == "ABONNEMENT_EXPIRE"
    # Profil minimal toujours lisible : le site sait qu'il doit afficher l'écran « Abonnement expiré »
    me = client.get("/api/auth/me", headers=hc)
    assert me.status_code == 200 and me.json()["boutique"]["abonnement_grace"]["coupe"] is True


def test_routes_de_paiement_restent_ouvertes_et_paiement_rend_l_acces(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique()
    fixer_echeance(client, super_admin, b, -10)
    assert coupe(client.get("/api/clients", headers=h))
    # Page Abonnement, factures SMS, profil : ouverts pour pouvoir payer
    r = client.get("/api/boutique/abonnement", headers=h)
    assert r.status_code == 200 and r.json()["etat"]["grace"]["coupe"] is True
    assert client.get("/api/boutique/sms/factures", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 200
    # Paiement (PawaPay non configuré dans les tests : 503, mais pas « Abonnement expiré »)
    assert client.post("/api/boutique/abonnement/payer", headers=h, json={"formule": "MENSUEL"}).status_code == 503
    # Paiement reçu : nouvelle échéance, accès rendu
    r = client.post(f"/api/plateforme/abonnements/boutiques/{b['id']}/paiements", headers=super_admin,
                    json={"formule": "MENSUEL", "mode": "ESPECES"})
    assert r.status_code == 201, r.text
    assert client.get("/api/clients", headers=h).status_code == 200
    assert client.post("/api/auth/logout", headers=h).status_code == 200


def test_super_admin_et_boutique_de_test_jamais_coupes(client, super_admin, nouvelle_boutique):
    b, _ = nouvelle_boutique()
    fixer_echeance(client, super_admin, b, -20)
    assert client.get("/api/produits", headers={**super_admin, "X-Boutique-Id": b["id"]}).status_code == 200
    interne, hi = nouvelle_boutique(test=True)
    e = fixer_echeance(client, super_admin, interne, -20)
    assert e["grace"]["applicable"] is False and e["grace"]["coupe"] is False
    assert client.get("/api/produits", headers=hi).status_code == 200


def test_reglage_par_boutique(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique()
    url = f"/api/plateforme/abonnements/boutiques/{b['id']}/grace"
    assert client.get(url, headers=super_admin).json()["jours_grace"] == 3  # défaut
    for invalide in (-1, 31):
        assert client.put(url, headers=super_admin, json={"jours": invalide}).status_code == 400
    assert client.put(url, headers=h, json={"jours": 10}).status_code == 403  # réservé au super-admin
    fixer_echeance(client, super_admin, b, -8)
    assert coupe(client.get("/api/produits", headers=h))
    r = client.put(url, headers=super_admin, json={"jours": 10})
    assert r.status_code == 200 and r.json()["jours_grace"] == 10 and r.json()["jours_grace_restants"] == 3
    assert client.get("/api/produits", headers=h).status_code == 200
    # 0 jour : coupure dès le lendemain de l'échéance
    client.put(url, headers=super_admin, json={"jours": 0})
    fixer_echeance(client, super_admin, b, -1)
    assert coupe(client.get("/api/produits", headers=h))
    # Retour à la valeur par défaut, modification journalisée
    r = client.put(url, headers=super_admin, json={"jours": None})
    assert r.json()["jours_grace"] == 3 and r.json()["grace_jours_boutique"] is None
    assert [l["action"] for l in r.json()["journal"]] == ["DELAI_MODIFIE"] * 3


def test_renouveler_la_grace_trois_fois_au_plus(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique()
    url = f"/api/plateforme/abonnements/boutiques/{b['id']}/grace/renouveler"
    # Abonnement pas encore expiré : rien à renouveler
    assert client.post(url, headers=super_admin).status_code == 400
    fixer_echeance(client, super_admin, b, -5)
    assert coupe(client.get("/api/produits", headers=h))
    r = client.post(url, headers=super_admin)
    assert r.status_code == 200 and r.json()["prolongations"] == 1 and r.json()["jours_grace_restants"] == 2
    assert client.get("/api/produits", headers=h).status_code == 200
    assert client.post(url, headers=h).status_code == 403  # réservé au super-admin
    assert client.post(url, headers=super_admin).json()["prolongations"] == 2
    r = client.post(url, headers=super_admin)
    assert r.json()["prolongations"] == 3 and r.json()["prolongation_possible"] is False
    r = client.post(url, headers=super_admin)
    assert r.status_code == 400 and "3 fois" in r.json()["detail"]
    journal = client.get(f"/api/plateforme/abonnements/boutiques/{b['id']}/grace", headers=super_admin).json()["journal"]
    assert [l["numero"] for l in journal if l["action"] == "GRACE_RENOUVELEE"] == [3, 2, 1]
    # Nouvelle échéance (paiement, correction) : le compteur repart de zéro
    fixer_echeance(client, super_admin, b, -6)
    assert client.post(url, headers=super_admin).json()["prolongations"] == 1


def test_coupure_a_l_heure_exacte(client, super_admin, nouvelle_boutique, monkeypatch):
    b, h = nouvelle_boutique()
    fixer_echeance(client, super_admin, b, -3)  # aujourd'hui = dernier jour de grâce
    tz = ZoneInfo(get_settings().fuseau_horaire)
    minuit = datetime.combine(AUJ + timedelta(days=1), time(0), tz)
    monkeypatch.setattr(abonnement_grace, "_maintenant", lambda: minuit - timedelta(seconds=1))
    assert client.get("/api/produits", headers=h).status_code == 200
    # Même session, une seconde plus tard : coupée sans avoir à se reconnecter
    monkeypatch.setattr(abonnement_grace, "_maintenant", lambda: minuit)
    assert coupe(client.get("/api/produits", headers=h))
