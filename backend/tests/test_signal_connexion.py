"""Lot 39 — connexions et visites signalées à SAWALI (alerte WhatsApp du propriétaire).

Vérifie : requête signée (HMAC) correcte, signal envoyé à la connexion, visites limitées
à 1 / 30 min par visiteur ou IP, robots ignorés, rien si SAWALI n'est pas configuré,
aucune exception si SAWALI est injoignable. Aucun appel réseau réel (transport simulé)."""
import asyncio
import hashlib
import hmac
import json
import time

import httpx
import pytest
from starlette.requests import Request

import signal_connexion as sc
from config import get_settings

NAVIGATEUR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"


@pytest.fixture
def reglages(monkeypatch):
    """Clé, émetteur et adresses de test (jamais de vraie clé) ; signal réactivé pour ces tests."""
    s = get_settings()
    monkeypatch.setenv("SIGNAL_CONNEXIONS_SAWALI", "1")
    monkeypatch.setattr(s, "liluvine_wa_hmac", "cle-test")
    monkeypatch.setattr(s, "liluvine_wa_emetteur", "adlyn")
    monkeypatch.setattr(s, "liluvine_wa_url", "https://api.exemple.test/api/webhook/liluvine-send")
    monkeypatch.setattr(s, "frontend_origin", "https://adlynservice.com,https://www.adlynservice.com")
    monkeypatch.delenv("SAWALI_API_URL", raising=False)
    sc._dernieres_visites.clear()
    return s


def _requete(entetes=None, ip="10.0.0.9"):
    """Fausse requête HTTP (en-têtes + adresse de l'appelant)."""
    brut = [(k.lower().encode(), v.encode()) for k, v in (entetes or {}).items()]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": brut, "client": (ip, 1234),
                    "query_string": b""})


def _executer(coro):
    """Exécute une coroutine dans une boucle neuve (tests synchrones)."""
    return asyncio.new_event_loop().run_until_complete(coro)


def test_envoi_signe(reglages, monkeypatch):
    """Le corps part vers /api/webhook/plateforme-connexion, signé avec la clé d'émetteur."""
    vus = {}

    def repondre(requete: httpx.Request):
        vus["url"], vus["entetes"], vus["corps"] = str(requete.url), requete.headers, requete.content.decode()
        return httpx.Response(200, json={"ok": True, "alerte": True, "raison": None})

    monkeypatch.setattr(sc, "_transport", httpx.MockTransport(repondre))
    req = _requete({"X-Forwarded-For": "41.203.1.2, 10.1.1.1", "User-Agent": NAVIGATEUR})
    corps = sc.construire_corps("connexion", req, utilisateur="Awa (DG) · Télécom X", telephone="+226 70 12 34 56",
                                role="boutique", page="/connexion")
    r = _executer(sc.envoyer(corps))
    assert r == {"ok": True, "alerte": True, "raison": None}
    assert vus["url"] == "https://api.exemple.test/api/webhook/plateforme-connexion"
    h = vus["entetes"]
    attendu = hmac.new(b"cle-test", f"{h['X-Timestamp']}.{vus['corps']}".encode(), hashlib.sha256).hexdigest()
    assert h["X-Emetteur"] == "adlyn" and h["X-Signature"] == attendu
    assert abs(int(h["X-Timestamp"]) - time.time()) < 10
    envoye = json.loads(vus["corps"])
    # IP réelle = premier élément de X-Forwarded-For ; téléphone réduit aux chiffres ; site public
    assert envoye["type"] == "connexion" and envoye["ip"] == "41.203.1.2"
    assert envoye["telephone"] == "22670123456" and envoye["url_site"] == "https://adlynservice.com"
    assert envoye["agent"] == NAVIGATEUR and envoye["le"].endswith("Z")
    # Aucun secret dans le corps
    assert "cle-test" not in vus["corps"] and "password" not in vus["corps"]


def test_rien_si_non_configure(reglages, monkeypatch):
    """Sans clé SAWALI, ou interrupteur coupé : aucun appel."""
    appels = []
    monkeypatch.setattr(sc, "_transport", httpx.MockTransport(lambda r: appels.append(r) or httpx.Response(200, json={})))
    monkeypatch.setattr(reglages, "liluvine_wa_hmac", None)
    assert _executer(sc.envoyer({"type": "connexion"})) is None
    monkeypatch.setattr(reglages, "liluvine_wa_hmac", "cle-test")
    monkeypatch.setenv("SIGNAL_CONNEXIONS_SAWALI", "0")
    assert _executer(sc.envoyer({"type": "connexion"})) is None
    assert appels == []


def test_sawali_injoignable_sans_exception(reglages, monkeypatch):
    """Réseau coupé, délai dépassé, erreur 500 ou réponse illisible : None, jamais d'exception."""
    def coupe(r):
        raise httpx.ConnectError("injoignable")

    def lent(r):
        raise httpx.ReadTimeout("trop lent")

    for transport in (coupe, lent, lambda r: httpx.Response(500, text="panne"),
                      lambda r: httpx.Response(200, text="pas du json")):
        monkeypatch.setattr(sc, "_transport", httpx.MockTransport(transport))
        assert _executer(sc.envoyer(sc.construire_corps("visite", _requete()))) is None
    # Planification hors boucle asyncio : ignorée sans erreur
    sc.planifier({"type": "connexion"})


def test_connexion_signalee_au_login(client, reglages, monkeypatch):
    """Connexion réussie (/auth/login) : un signal « connexion » signé part en arrière-plan."""
    recus = []

    def repondre(requete: httpx.Request):
        recus.append({"entetes": requete.headers, "corps": requete.content.decode()})
        return httpx.Response(200, json={"ok": True, "alerte": True, "raison": None})

    monkeypatch.setattr(sc, "_transport", httpx.MockTransport(repondre))
    # Mauvais mot de passe : aucun signal
    r = client.post("/api/auth/login", json={"email": "super@plateforme-test.bf", "password": "faux"},
                    headers={"User-Agent": NAVIGATEUR})
    assert r.status_code == 401
    r = client.post("/api/auth/login", json={"email": "super@plateforme-test.bf", "password": "super-motdepasse"},
                    headers={"User-Agent": NAVIGATEUR, "X-Forwarded-For": "41.203.5.6"})
    assert r.status_code == 200
    client.cookies.clear()
    fin = time.time() + 3
    while not recus and time.time() < fin:  # l'envoi part en tâche de fond
        time.sleep(0.05)
    assert len(recus) == 1
    h, brut = recus[0]["entetes"], recus[0]["corps"]
    assert h["X-Signature"] == hmac.new(b"cle-test", f"{h['X-Timestamp']}.{brut}".encode(), hashlib.sha256).hexdigest()
    corps = json.loads(brut)
    assert corps["type"] == "connexion" and corps["role"] == "admin" and corps["ip"] == "41.203.5.6"
    assert "Super-administrateur" in corps["utilisateur"]
    assert "super-motdepasse" not in brut


def test_connexion_personnel_et_client(reglages, monkeypatch):
    """Libellés envoyés : personnel (nom, rôle, boutique, téléphone) et client de « Mon espace »."""
    corps_vus = []
    monkeypatch.setattr(sc, "planifier", corps_vus.append)
    req = _requete({"User-Agent": NAVIGATEUR})
    sc.signaler_connexion_personnel(req, {"nom": "Awa Ouédraogo", "role": "dg", "telephone": "70 12 34 56",
                                          "password_hash": "x"}, {"nom": "Télécom Wendpanga"})
    sc.signaler_connexion_client(req, {"nom": "Issa", "telephone": "+22676000000"}, {"nom": "Télécom Wendpanga"})
    p, c = corps_vus
    assert p["utilisateur"] == "Awa Ouédraogo (DG) · Télécom Wendpanga" and p["role"] == "boutique"
    assert p["telephone"] == "70123456" and "password_hash" not in json.dumps(p)
    assert c["role"] == "client" and c["telephone"] == "22676000000" and c["utilisateur"].startswith("Issa (client)")
    assert p["ip"] == "10.0.0.9"  # sans X-Forwarded-For : adresse de la connexion


def test_visites_limitees(client, reglages, monkeypatch):
    """1 visite signalée / 30 min par visiteur ou par IP ; robots et personnes connectées ignorés."""
    corps_vus = []
    monkeypatch.setattr(sc, "planifier", corps_vus.append)
    entetes = {"User-Agent": NAVIGATEUR, "X-Forwarded-For": "41.1.1.1"}
    r = client.post("/api/presence/visite", json={"visiteur": "abc123", "page": "/boutique/x"}, headers=entetes)
    assert r.json() == {"ok": True, "signale": True}
    assert corps_vus[0]["type"] == "visite" and corps_vus[0]["visiteur"] == "abc123"
    assert corps_vus[0]["page"] == "/boutique/x" and corps_vus[0]["utilisateur"] is None
    # Même visiteur (autre IP) puis même IP (autre visiteur) : ignorés
    r = client.post("/api/presence/visite", json={"visiteur": "abc123"}, headers={**entetes, "X-Forwarded-For": "41.2.2.2"})
    assert r.json()["signale"] is False
    r = client.post("/api/presence/visite", json={"visiteur": "autre"}, headers=entetes)
    assert r.json()["signale"] is False
    # Robot évident : ignoré
    r = client.post("/api/presence/visite", json={"visiteur": "robot1"},
                    headers={"User-Agent": "Googlebot/2.1", "X-Forwarded-For": "66.249.1.1"})
    assert r.json()["signale"] is False
    assert len(corps_vus) == 1
    # 30 minutes plus tard : de nouveau signalé
    assert sc.visite_autorisee("abc123", "41.1.1.1", time.time() + sc.INTERVALLE_VISITES + 1)


def test_visite_rien_si_non_configure(client, reglages, monkeypatch):
    """Sans clé SAWALI : la route répond, mais rien n'est signalé."""
    corps_vus = []
    monkeypatch.setattr(sc, "planifier", corps_vus.append)
    monkeypatch.setattr(reglages, "liluvine_wa_hmac", None)
    r = client.post("/api/presence/visite", json={"visiteur": "zz9"}, headers={"User-Agent": NAVIGATEUR})
    assert r.status_code == 200 and r.json()["signale"] is False and corps_vus == []
