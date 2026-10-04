"""Transmission WA : ordre de priorité WABA boutique > WABA plateforme > Liluvine,
signature HMAC du corps exact, nouvel essai unique (même id) sur erreur réseau ou 5xx,
pas de nouvel essai sur 4xx, désactivation propre sans variables, routes super-admin.
Aucun appel réseau réel : httpx est remplacé par un transport simulé."""
import asyncio
import hashlib
import hmac
import json

import httpx
import pytest

import envois_plateforme as envois
import transmission_wa as tw
from config import get_settings

CLE = "cle-hmac-de-test"
URL = "https://sawali.test/api/webhook/liluvine-send"


@pytest.fixture
def reglages(client, monkeypatch):
    """Plateforme sans WABA, transmission Liluvine configurée (valeurs de test)."""
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_access_token", None)
    monkeypatch.setattr(s, "whatsapp_phone_number_id", None)
    monkeypatch.setattr(s, "liluvine_wa_url", URL)
    monkeypatch.setattr(s, "liluvine_wa_hmac", CLE)
    monkeypatch.setattr(s, "liluvine_wa_emetteur", "adlyn")
    return s


@pytest.fixture
def sawali(monkeypatch):
    """Remplace httpx.AsyncClient du module par un client à transport simulé.
    `reponses` : liste de codes HTTP (ou d'exceptions) renvoyés dans l'ordre."""
    etat = {"reponses": [200], "requetes": []}

    def gerer(requete: httpx.Request):
        etat["requetes"].append(requete)
        r = etat["reponses"].pop(0) if etat["reponses"] else 200
        if isinstance(r, Exception):
            raise r
        corps = {"ok": True, "id": json.loads(requete.content)["id"], "message_id": "wamid.TEST"} if r == 200 \
            else {"detail": "refus"}
        return httpx.Response(r, json=corps)

    vrai_client = httpx.AsyncClient
    monkeypatch.setattr(tw.httpx, "AsyncClient",
                        lambda **kw: vrai_client(transport=httpx.MockTransport(gerer), **kw))
    return etat


def envoyer(*args, **kw):
    return asyncio.run(tw.envoyer_whatsapp(*args, **kw))


def test_signature_hmac_sur_le_corps_exact(reglages, sawali):
    res = envoyer("+226 70 00 00 00", "Bonjour", boutique={"nom": "Boutique Test"})
    assert res == {"ok": True, "canal": "liluvine", "message_id": "wamid.TEST", "erreur": None, "statut": "ENVOYE"}
    req = sawali["requetes"][0]
    attendu = hmac.new(CLE.encode(), req.headers["X-Timestamp"].encode() + b"." + req.content,
                       hashlib.sha256).hexdigest()
    assert req.headers["X-Signature"] == attendu
    assert req.headers["X-Emetteur"] == "adlyn"
    corps = json.loads(req.content)
    assert corps["to"] == "+22670000000" and corps["message"] == "Bonjour"
    assert corps["source"] == "adLyn — Boutique Test" and len(corps["id"]) == 36


def test_source_par_defaut_sans_boutique(reglages, sawali):
    envoyer("+22670000000", "Bonjour")
    assert json.loads(sawali["requetes"][0].content)["source"] == "adLyn"


def test_nouvel_essai_unique_meme_id_sur_5xx(reglages, sawali):
    sawali["reponses"] = [503, 200]
    res = envoyer("+22670000000", "Bonjour")
    assert res["ok"] and len(sawali["requetes"]) == 2
    ids = [json.loads(r.content)["id"] for r in sawali["requetes"]]
    assert ids[0] == ids[1]


def test_nouvel_essai_sur_erreur_reseau_puis_abandon(reglages, sawali):
    sawali["reponses"] = [httpx.ConnectError("panne"), httpx.ConnectError("panne")]
    res = envoyer("+22670000000", "Bonjour")
    assert res["ok"] is False and res["canal"] == "liluvine" and len(sawali["requetes"]) == 2
    assert len({json.loads(r.content)["id"] for r in sawali["requetes"]}) == 1


def test_pas_de_nouvel_essai_sur_4xx(reglages, sawali):
    sawali["reponses"] = [422, 200]
    res = envoyer("+22670000000", "Bonjour")
    assert res["ok"] is False and "422" in res["erreur"] and len(sawali["requetes"]) == 1


def test_desactivation_propre_sans_variables(reglages, sawali, monkeypatch):
    monkeypatch.setattr(reglages, "liluvine_wa_hmac", None)
    res = envoyer("+22670000000", "Bonjour")
    assert res["ok"] is False and res["canal"] is None and res["statut"] == "NON_CONFIGURE"
    assert "LILUVINE_WA" in res["erreur"] and not sawali["requetes"]
    # L'ancien point d'entrée renvoie toujours un statut lisible
    assert asyncio.run(envois.envoyer_whatsapp("+22670000000", [], "Bonjour"))[0] == "NON_CONFIGURE"


def test_priorite_boutique_puis_plateforme_puis_liluvine(reglages, sawali, monkeypatch):
    appels = []

    async def faux_waba(telephone, variables, texte, *, modele=None, composants=None, identifiants=None):
        appels.append(identifiants)
        return "ENVOYE", "", "wamid.META"

    monkeypatch.setattr(envois, "envoyer_whatsapp_waba", faux_waba)
    boutique = {"nom": "B", "whatsapp_waba": {"phone_number_id": "111", "access_token": envois.chiffrer("jeton-b")}}

    # 1) WABA de la boutique, même si la plateforme a le sien
    monkeypatch.setattr(reglages, "whatsapp_access_token", "jeton-plateforme")
    monkeypatch.setattr(reglages, "whatsapp_phone_number_id", "999")
    assert envoyer("+22670000000", "x", boutique=boutique)["canal"] == "waba_boutique"
    assert appels[-1] == ("111", "jeton-b")
    # 2) Boutique sans WABA : celui de la plateforme
    assert envoyer("+22670000000", "x", boutique={"nom": "C"})["canal"] == "waba_plateforme"
    assert appels[-1] is None
    # 3) Aucun WABA : Liluvine
    monkeypatch.setattr(reglages, "whatsapp_access_token", None)
    assert envoyer("+22670000000", "x", boutique={"nom": "C"})["canal"] == "liluvine"
    assert len(appels) == 2 and len(sawali["requetes"]) == 1


def test_routes_super_admin(client, super_admin, nouvelle_boutique, reglages, sawali):
    r = client.get("/api/admin/transmission-wa/etat", headers=super_admin)
    assert r.status_code == 200
    assert r.json() == {"waba_plateforme_configure": False, "liluvine_configure": True, "emetteur": "adlyn"}
    assert CLE not in r.text
    r = client.post("/api/admin/transmission-wa/test", headers=super_admin, json={"numero": "+22670000000"})
    assert r.status_code == 200 and r.json()["ok"] and r.json()["canal"] == "liluvine"
    assert json.loads(sawali["requetes"][-1].content)["message"] == "Test de transmission WhatsApp depuis adLyn"
    # Interdit à un gérant de boutique
    _, gerant = nouvelle_boutique()
    assert client.get("/api/admin/transmission-wa/etat", headers=gerant).status_code == 403
