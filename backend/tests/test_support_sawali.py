"""SAWALI lot 90 — relais du support SAWALI : requête signée (HMAC), identité de la boutique,
erreurs lisibles, routes réservées au personnel connecté. Aucun appel réseau réel (transport simulé)."""
import asyncio
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import HTTPException

import support_sawali as ss
from config import get_settings


@pytest.fixture
def reglages(monkeypatch):
    """Clé, émetteur et URL Liluvine de test (jamais de vraie clé)."""
    s = get_settings()
    monkeypatch.setattr(s, "liluvine_wa_hmac", "cle-test")
    monkeypatch.setattr(s, "liluvine_wa_emetteur", "adlyn")
    monkeypatch.setattr(s, "liluvine_wa_url", "https://api.exemple.test/api/webhook/liluvine-send")
    monkeypatch.delenv("SAWALI_API_URL", raising=False)
    return s


def _executer(coro):
    """Exécute une coroutine dans une boucle neuve (tests synchrones)."""
    return asyncio.new_event_loop().run_until_complete(coro)


def test_relais_signe(reglages, monkeypatch):
    """Le corps part signé avec la clé d'émetteur, vers l'adresse déduite de LILUVINE_WA_URL."""
    vus = {}

    def repondre(requete: httpx.Request):
        vus["url"] = str(requete.url)
        vus["entetes"] = requete.headers
        vus["corps"] = requete.content.decode()
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(ss, "_transport", httpx.MockTransport(repondre))
    r = _executer(ss.appeler_sawali("/support-plateforme/messages", {"utilisateur": {"id": "u1"}, "texte": "Bonjour"}))
    assert r == {"ok": True}
    assert vus["url"] == "https://api.exemple.test/api/support-plateforme/messages"
    h = vus["entetes"]
    attendu = hmac.new(b"cle-test", f"{h['X-Timestamp']}.{vus['corps']}".encode(), hashlib.sha256).hexdigest()
    assert h["X-Emetteur"] == "adlyn" and h["X-Signature"] == attendu
    assert json.loads(vus["corps"])["texte"] == "Bonjour"


def test_erreurs_lisibles(reglages, monkeypatch):
    """Sans clé : 503 ; support non activé chez SAWALI (403) : message clair ; jamais la clé dans l'erreur."""
    monkeypatch.setattr(reglages, "liluvine_wa_hmac", None)
    with pytest.raises(HTTPException) as e:
        _executer(ss.appeler_sawali("/x", {}))
    assert e.value.status_code == 503
    monkeypatch.setattr(reglages, "liluvine_wa_hmac", "cle-test")
    monkeypatch.setattr(ss, "_transport", httpx.MockTransport(lambda r: httpx.Response(403, json={})))
    with pytest.raises(HTTPException) as e:
        _executer(ss.appeler_sawali("/x", {}))
    assert "pas encore activé" in e.value.detail and "cle-test" not in e.value.detail


def test_routes_gerant_identite_boutique(client, nouvelle_boutique, reglages, monkeypatch):
    """Le gérant connecté écrit au support : l'identité envoyée porte le nom de SA boutique ; sans jeton : refus."""
    vus = {}

    def repondre(requete: httpx.Request):
        vus["corps"] = json.loads(requete.content.decode())
        return httpx.Response(200, json={"ok": True, "requete": {"numero": "SUP-1", "statut": "attente"}})

    monkeypatch.setattr(ss, "_transport", httpx.MockTransport(repondre))
    boutique, entetes = nouvelle_boutique(nom="Boutique Support")
    assert client.get("/api/support-sawali/etat", headers=entetes).json() == {"actif": True}
    r = client.post("/api/support-sawali/messages", headers=entetes, json={"texte": "  Besoin d'aide  "})
    assert r.status_code == 200, r.text
    u = vus["corps"]["utilisateur"]
    assert vus["corps"]["texte"] == "Besoin d'aide"
    assert u["contexte"] == "Boutique Support" and u["id"] and set(u) == {"id", "nom", "role", "contexte", "email", "telephone"}
    client.cookies.clear()
    assert client.get("/api/support-sawali/etat").status_code == 401
