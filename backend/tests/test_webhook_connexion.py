"""Webhook de création des boutiques (HMAC, anti-rejeu, anti-plaisantins,
validation) et connexion par ID boutique + e-mail + mot de passe (cookie de session)."""
import json
import re
import time

import pytest

import envois_plateforme
from config import get_settings
from routes.webhooks import signature_attendue

SECRET = "secret-webhook-de-test"
_n = {"i": 0}


@pytest.fixture
def envois(monkeypatch):
    """Active le webhook et capture les e-mails / SMS au lieu de les envoyer."""
    monkeypatch.setattr(get_settings(), "webhook_boutiques_secret", SECRET)
    monkeypatch.setattr(get_settings(), "webhook_max_echecs_ip", 1000)
    boite: list[dict] = []

    async def faux_email(sujet, corps, destinataire):
        boite.append({"canal": "email", "sujet": sujet, "corps": corps, "a": destinataire})
        return "ENVOYE", ""

    async def faux_sms(telephone, texte):
        boite.append({"canal": "sms", "corps": texte, "a": telephone})
        return "ENVOYE", ""

    monkeypatch.setattr(envois_plateforme, "envoyer_email", faux_email)
    monkeypatch.setattr(envois_plateforme, "envoyer_sms", faux_sms)
    return boite


def demande(**extra):
    _n["i"] += 1
    i = _n["i"]
    return {"evenement_id": f"evt-{time.time_ns()}-{i}", "nom": f"Télécom Wendpanga {i}", "pays": "Burkina Faso",
            "ville": "Bobo-Dioulasso", "telephone": "20 97 00 00", "dg_nom": "Awa Ouédraogo",
            "dg_email": f"awa{i}-{time.time_ns()}@exemple.bf", "dg_telephone": "70 12 34 56", **extra}


def envoyer(client, contenu, secret=SECRET, horodatage=None, signature=None):
    corps = json.dumps(contenu).encode()
    ts = str(horodatage if horodatage is not None else int(time.time()))
    return client.post("/api/webhooks/boutiques", content=corps, headers={
        "Content-Type": "application/json", "X-Adlyn-Horodatage": ts,
        "X-Adlyn-Signature": signature or signature_attendue(secret, ts, corps)})


def mot_de_passe_recu(boite):
    email = next(m for m in reversed(boite) if m["canal"] == "email" and "Mot de passe provisoire" in m["corps"])
    return re.search(r"Mot de passe provisoire : (\S+)", email["corps"]).group(1)


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------
def test_webhook_ferme_sans_secret(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "webhook_boutiques_secret", None)
    assert envoyer(client, demande()).status_code == 503


def test_webhook_signature_et_horodatage(client, envois):
    assert envoyer(client, demande(), secret="mauvais-secret").status_code == 401
    assert envoyer(client, demande(), horodatage=int(time.time()) - 3600).status_code == 401
    assert envoyer(client, demande(), signature="sha256=00").status_code == 401
    # Corps modifié après signature : refusé
    d = demande()
    corps = json.dumps(d).encode()
    ts = str(int(time.time()))
    sig = signature_attendue(SECRET, ts, corps)
    r = client.post("/api/webhooks/boutiques", content=corps.replace(b"Bobo", b"Koud"), headers={
        "Content-Type": "application/json", "X-Adlyn-Horodatage": ts, "X-Adlyn-Signature": sig})
    assert r.status_code == 401


def test_webhook_creation_validation_et_connexion(client, super_admin, envois):
    d = demande()
    r = envoyer(client, d)
    assert r.status_code == 201, r.text
    rep = r.json()
    assert rep["resultat"] == "creee" and rep["statut"] == "EN_ATTENTE_VALIDATION"
    code = rep["code_boutique"]
    assert re.fullmatch(r"[A-Z0-9]{6}", code)
    # Le mot de passe n'est JAMAIS dans la réponse du webhook...
    mdp = mot_de_passe_recu(envois)
    assert mdp not in r.text
    # ... il est envoyé au DG par e-mail ET par SMS
    assert any(m["canal"] == "sms" and code in m["corps"] and m["a"] == d["dg_telephone"] for m in envois)
    assert any(m["canal"] == "email" and m["a"] == d["dg_email"] for m in envois)

    # Boutique invisible du public tant qu'elle n'est pas validée
    boutique = next(b for b in client.get("/api/plateforme/boutiques", headers=super_admin).json()
                    if b["code_marchand"] == code)
    assert boutique["validee"] is False and boutique["origine"] == "webhook"
    assert client.get(f"/api/public/b/{boutique['slug']}").status_code == 404
    assert code not in [b["code_marchand"] for b in client.get("/api/public/boutiques").json()]

    # Le DG se connecte avec l'ID boutique mais doit d'abord changer son mot de passe
    session = client.post("/api/auth/login", json={"code_boutique": code, "email": d["dg_email"], "password": mdp}).json()
    client.cookies.clear()
    h = {"Authorization": f"Bearer {session['access_token']}"}
    assert session["user"]["doit_changer_mot_de_passe"] is True
    # (tableau de bord : toujours actif, même pour une boutique neuve sans autre option)
    assert client.get("/api/tableau-de-bord", headers=h).status_code == 403
    r = client.post("/api/auth/mot-de-passe", headers=h, json={"ancien": mdp, "nouveau": "mon-nouveau-mdp"})
    assert r.status_code == 200
    client.cookies.clear()
    # L'ancien jeton est révoqué, le nouveau fonctionne
    assert client.get("/api/auth/me", headers=h).status_code == 401
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/tableau-de-bord", headers=h).status_code == 200
    # Boutique créée par le webhook : seules les options obligatoires sont actives
    assert client.get("/api/produits", headers=h).status_code == 403

    # Validation par le super-admin : la boutique devient publique
    assert client.post(f"/api/plateforme/boutiques/{boutique['id']}/valider", headers=super_admin).status_code == 200
    assert client.get(f"/api/public/b/{boutique['slug']}").status_code == 200

    # Journal consultable par le super-admin
    journal = client.get("/api/plateforme/webhooks/journal", headers=super_admin).json()
    assert journal["configure"] and any(x["resultat"] == "CREEE" and x["boutique_id"] == boutique["id"]
                                        for x in journal["lignes"])


def test_webhook_rejeu_et_boutique_existante(client, envois):
    d = demande()
    assert envoyer(client, d).status_code == 201
    # Même événement renvoyé (rejeu) : refusé
    assert envoyer(client, d).status_code == 409
    # Même nom (casse/accents différents), autre événement : ignoré, rien de créé
    autre = demande(nom=d["nom"].upper().replace("É", "E"))
    r = envoyer(client, autre)
    assert r.status_code == 200 and r.json()["resultat"] == "ignoree"
    assert "code_boutique" not in r.json()
    # Même e-mail de DG : ignoré aussi
    assert envoyer(client, demande(dg_email=d["dg_email"])).json()["resultat"] == "ignoree"


@pytest.mark.parametrize("champs", [
    {"nom": "test"}, {"nom": "aaaaaaa"}, {"nom": "12345"}, {"nom": "Voir https://pub.example"},
    {"dg_email": "x@yopmail.com"}, {"dg_telephone": "12"}, {"dg_nom": "xx"}, {"champ_inconnu": 1},
])
def test_webhook_anti_plaisantins(client, envois, champs):
    assert envoyer(client, demande(**champs)).status_code == 422


def test_webhook_quota_et_blocage_ip(client, envois, monkeypatch):
    monkeypatch.setattr(get_settings(), "webhook_quota_jour", 0)
    assert envoyer(client, demande()).status_code == 429
    # Trop d'appels refusés depuis la même adresse : bloquée
    monkeypatch.setattr(get_settings(), "webhook_max_echecs_ip", 0)
    assert envoyer(client, demande()).status_code == 429


def test_renvoi_des_identifiants(client, super_admin, envois):
    code = envoyer(client, demande()).json()["code_boutique"]
    premier = mot_de_passe_recu(envois)
    b = next(x for x in client.get("/api/plateforme/boutiques", headers=super_admin).json() if x["code_marchand"] == code)
    r = client.post(f"/api/plateforme/boutiques/{b['id']}/renvoyer-identifiants", headers=super_admin)
    assert r.status_code == 200 and r.json()["email"] == "ENVOYE" and "mot" not in r.text.lower()
    assert mot_de_passe_recu(envois) != premier


# ---------------------------------------------------------------------------
# Connexion : ID boutique + e-mail + mot de passe, session par cookie
# ---------------------------------------------------------------------------
def test_connexion_exige_l_id_boutique(client, nouvelle_boutique):
    b, _ = nouvelle_boutique()
    n = b["nom"].split()[-1]
    email = f"gerant{n}@test.bf"
    base = {"email": email, "password": "motdepasse-123"}
    assert client.post("/api/auth/login", json=base).status_code == 401  # sans ID boutique
    assert client.post("/api/auth/login", json={**base, "code_boutique": "ZZZZZZ"}).status_code == 401
    ok = client.post("/api/auth/login", json={**base, "code_boutique": b["code_marchand"].lower()})
    assert ok.status_code == 200  # la casse de l'ID ne compte pas
    client.cookies.clear()


def test_session_par_cookie(client, nouvelle_boutique):
    b, _ = nouvelle_boutique()
    n = b["nom"].split()[-1]
    r = client.post("/api/auth/login", json={"code_boutique": b["code_marchand"], "email": f"gerant{n}@test.bf",
                                             "password": "motdepasse-123"})
    cookie = r.headers["set-cookie"]
    assert "adlyn_session=" in cookie and "HttpOnly" in cookie
    assert "motdepasse-123" not in cookie  # jamais le mot de passe
    # Le navigateur se reconnecte avec le seul cookie
    assert client.get("/api/auth/me").json()["boutique"]["id"] == b["id"]
    # Écriture via cookie sans l'en-tête du site : refusée (CSRF)
    assert client.post("/api/categories", json={"nom": "Rayon cookie"}).status_code == 403
    assert client.post("/api/categories", json={"nom": "Rayon cookie"}, headers={"X-Adlyn": "1"}).status_code == 201
    # Déconnexion : cookie effacé
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()


def test_anti_force_brute(client, nouvelle_boutique):
    b, _ = nouvelle_boutique()
    n = b["nom"].split()[-1]
    essai = {"code_boutique": b["code_marchand"], "email": f"gerant{n}@test.bf", "password": "faux-mot-de-passe"}
    for _ in range(10):
        assert client.post("/api/auth/login", json=essai).status_code == 401
    # Même le bon mot de passe est bloqué pendant 15 minutes
    assert client.post("/api/auth/login", json={**essai, "password": "motdepasse-123"}).status_code == 429
