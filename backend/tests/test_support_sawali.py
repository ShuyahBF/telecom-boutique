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


# ---------------------------------------------------------------------------------------------------------------
# SAWALI lot 93 — pictogrammes de la fenêtre d'assistance : photo / document, note vocale, média
# ---------------------------------------------------------------------------------------------------------------
JPEG93 = b"\xff\xd8\xff\xe0" + b"\x00" * 32 + b"\xff\xd9"


def test_pictos_fichier_transcription_media(client, nouvelle_boutique, reglages, monkeypatch):
    """Photo relayée signée (avec la boutique), note vocale transcrite, média renvoyé au navigateur avec son type."""
    import base64
    vus = []

    def repondre(r: httpx.Request):
        corps = json.loads(r.content.decode())
        vus.append((r.url.path, corps))
        if r.url.path.endswith("/fichier"):
            return httpx.Response(200, json={"ok": True, "message": {"id": "m1", "media": {"genre": "image"}}})
        if r.url.path.endswith("/transcrire"):
            return httpx.Response(200, json={"ok": True, "texte": "Bonjour"})
        return httpx.Response(200, json={"type": "image/jpeg", "nom": "a.jpg", "contenu": base64.b64encode(JPEG93).decode()})

    monkeypatch.setattr(ss, "_transport", httpx.MockTransport(repondre))
    _boutique, entetes = nouvelle_boutique(nom="Boutique Pictos")
    data = "data:image/jpeg;base64," + base64.b64encode(JPEG93).decode()
    r = client.post("/api/support-sawali/fichier", headers=entetes, json={"fichier": data, "nom": "a.jpg", "legende": " Voici "})
    assert r.status_code == 200, r.text
    assert vus[-1][0] == "/api/support-plateforme/fichier" and vus[-1][1]["legende"] == "Voici"
    assert vus[-1][1]["utilisateur"]["contexte"] == "Boutique Pictos"
    t = client.post("/api/support-sawali/transcrire", headers=entetes, json={"audio": "data:audio/webm;base64,QUJDREVGR0g="})
    assert t.json()["texte"] == "Bonjour"
    m = client.get("/api/support-sawali/media/m1", headers=entetes)
    assert m.status_code == 200 and m.content == JPEG93 and m.headers["content-type"] == "image/jpeg"
    # Refus de SAWALI (type non accepté) transmis tel quel
    monkeypatch.setattr(ss, "_transport", httpx.MockTransport(lambda r: httpx.Response(415, json={"detail": "Type de fichier non accepté"})))
    r = client.post("/api/support-sawali/fichier", headers=entetes, json={"fichier": "data:application/x-msdownload;base64,TVo=AAAA", "nom": "x.exe"})
    assert r.status_code == 415 and r.json()["detail"] == "Type de fichier non accepté"
