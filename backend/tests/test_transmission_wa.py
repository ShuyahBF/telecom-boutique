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


# ===========================================================================
# Protocole v3 : médias, retours de SAWALI, désinscription, repli, WABA boutique
# ===========================================================================
import base64  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402

from db import db  # noqa: E402


# ---- 1. Médias ----
def test_media_par_adresse(reglages, sawali):
    media = {"type": "document", "url": "https://r2.test/facture.pdf", "nom_fichier": "facture.pdf",
             "mime": "application/pdf"}
    res = envoyer("+22670000000", "Votre facture", media=media)
    assert res["ok"] and res["canal"] == "liluvine"
    corps = json.loads(sawali["requetes"][0].content)
    assert corps["message"] == "Votre facture"
    assert corps["media"] == {"type": "document", "url": "https://r2.test/facture.pdf",
                              "nom_fichier": "facture.pdf", "mime": "application/pdf"}


def test_media_en_octets_encode_en_base64(reglages, sawali):
    octets = b"%PDF-1.4 contenu de test"
    res = envoyer("+22670000000", "Votre facture", media={"type": "document", "contenu": octets,
                                                          "nom_fichier": "f.pdf", "mime": "application/pdf",
                                                          "legende": "Facture 12"})
    assert res["ok"]
    media = json.loads(sawali["requetes"][0].content)["media"]
    assert base64.b64decode(media["contenu_base64"]) == octets and "url" not in media
    assert media["legende"] == "Facture 12"
    # La signature couvre bien le corps avec le média
    req = sawali["requetes"][0]
    assert req.headers["X-Signature"] == tw.signer(CLE, req.headers["X-Timestamp"], req.content)


def test_media_trop_lourd_refuse_sans_appel(reglages, sawali):
    lourd = b"\x00" * (10 * 1024 * 1024 + 1)
    res = envoyer("+22670000000", "Photo", media={"type": "image", "contenu": lourd})
    assert res["ok"] is False and "10 Mo" in res["erreur"] and not sawali["requetes"]
    # Exactement un des deux : adresse OU contenu ; adresse https obligatoire
    assert "exactement un" in envoyer("+22670000000", "x", media={"type": "image"})["erreur"]
    assert "https" in envoyer("+22670000000", "x", media={"type": "image", "url": "http://a.b/c.png"})["erreur"]
    assert not sawali["requetes"]
    # Ancien point d'entrée : le paramètre media est transmis
    statut, erreur = asyncio.run(envois.envoyer_whatsapp("+22670000000", [], "x",
                                                         media={"type": "video", "contenu": lourd}))
    assert statut == "ECHEC" and "10 Mo" in erreur


# ---- 3. Désinscription : 409 = échec définitif, sans nouvel essai ----
def test_409_desinscrit_sans_nouvel_essai(reglages, sawali):
    sawali["reponses"] = [409, 200]
    res = envoyer("+22670009999", "Promo")
    assert res["ok"] is False and res["desinscrit"] is True and "désinscrit" in res["erreur"]
    assert len(sawali["requetes"]) == 1  # aucun nouvel essai
    id_envoi = json.loads(sawali["requetes"][0].content)["id"]
    trace = asyncio.run(db.liluvine_retours.find_one({"id_origine": id_envoi}, {"_id": 0}))
    assert trace["type"] == "refus_desinscrit" and trace["numero"] == "+22670009999"


# ---- 4. Repli quand le WABA propre échoue ----
def _waba_en_echec(monkeypatch, reglages, erreur):
    """WABA de la plateforme configuré, mais Meta refuse l'envoi avec `erreur`."""
    appels = []

    async def faux_waba(telephone, variables, texte, *, modele=None, composants=None, identifiants=None):
        appels.append(texte)
        return "ECHEC", erreur, None

    monkeypatch.setattr(envois, "envoyer_whatsapp_waba", faux_waba)
    monkeypatch.setattr(reglages, "whatsapp_access_token", "jeton-plateforme")
    monkeypatch.setattr(reglages, "whatsapp_phone_number_id", "999")
    return appels


def test_repli_liluvine_sur_fenetre_24h(reglages, sawali, monkeypatch):
    appels = _waba_en_echec(monkeypatch, reglages,
                            'text : HTTP 400 {"error":{"message":"Re-engagement message","code":131047}}')
    res = envoyer("+22670000000", "Votre réparation est prête")
    assert appels and res["ok"] and res["canal"] == "liluvine_repli" and "131047" in res["erreur_waba"]
    assert json.loads(sawali["requetes"][0].content)["message"] == "Votre réparation est prête"


def test_repli_avec_le_meme_media(reglages, sawali, monkeypatch):
    async def faux_media(telephone, media, legende="", *, identifiants=None):
        return "ECHEC", 'image : HTTP 400 {"error":{"code":470}}', None

    monkeypatch.setattr(envois, "envoyer_media_waba", faux_media)
    monkeypatch.setattr(reglages, "whatsapp_access_token", "jeton-plateforme")
    monkeypatch.setattr(reglages, "whatsapp_phone_number_id", "999")
    res = envoyer("+22670000000", "Photo", media={"type": "image", "url": "https://r2.test/p.png"})
    assert res["canal"] == "liluvine_repli"
    assert json.loads(sawali["requetes"][0].content)["media"]["url"] == "https://r2.test/p.png"


def test_pas_de_repli_sur_numero_invalide(reglages, sawali, monkeypatch):
    _waba_en_echec(monkeypatch, reglages, 'text : HTTP 400 {"error":{"message":"Recipient phone number not in '
                                          'allowed list","code":131030}}')
    res = envoyer("+22670000000", "Bonjour")
    assert res["ok"] is False and res["canal"] == "waba_plateforme" and not sawali["requetes"]


def test_pas_de_repli_sans_liluvine(reglages, sawali, monkeypatch):
    _waba_en_echec(monkeypatch, reglages, '{"error":{"code":131047}}')
    monkeypatch.setattr(reglages, "liluvine_wa_url", None)
    res = envoyer("+22670000000", "Bonjour")
    assert res["ok"] is False and res["canal"] == "waba_plateforme" and not sawali["requetes"]


# ---- 2. Retours de SAWALI : POST /api/webhooks/liluvine-retour ----
def _poster_retour(client, doc, cle=CLE, horodatage=None):
    corps = json.dumps(doc).encode()
    ts = str(horodatage or int(time.time()))
    return client.post("/api/webhooks/liluvine-retour", content=corps, headers={
        "Content-Type": "application/json", "X-Emetteur": "sawali", "X-Timestamp": ts,
        "X-Signature": tw.signer(cle, ts, corps)})


def test_webhook_retour_signature_et_idempotence(client, super_admin, reglages, sawali, monkeypatch):
    # Envoi d'origine (journalisé), auquel les retours se rapportent
    envoyer("+22670001111", "Bonjour")
    id_envoi = json.loads(sawali["requetes"][0].content)["id"]
    statut = {"type": "statut", "id": id_envoi, "message_id": "wamid.1", "statut": "delivered", "erreur": None,
              "date": "2026-10-04T10:00:00Z"}
    # Signature fausse, ou horodatage hors de la fenêtre de ± 5 min : 401
    assert _poster_retour(client, statut, cle="mauvaise-cle").status_code == 401
    assert _poster_retour(client, statut, horodatage=int(time.time()) - 600).status_code == 401
    # Signature correcte : enregistré, puis doublon ignoré
    r = _poster_retour(client, statut)
    assert r.status_code == 200 and r.json() == {"ok": True, "doublon": False}
    assert _poster_retour(client, statut).json() == {"ok": True, "doublon": True}
    lignes = client.portal.call(lambda: db.liluvine_retours.find({"id_origine": id_envoi, "type": "statut"}).to_list(10))
    assert len(lignes) == 1
    # Statut reporté sur l'envoi d'origine
    origine = client.portal.call(lambda: db.transmissions_wa.find_one({"id": id_envoi}))
    assert origine["statut_livraison"] == "delivered"
    # Type inconnu : 422
    assert _poster_retour(client, {"type": "autre"}).status_code == 422


def test_webhook_reponse_signalee_et_liste_admin(client, super_admin, nouvelle_boutique, reglages, sawali,
                                                  monkeypatch):
    courriels = []

    async def faux_email(sujet, corps, destinataire):
        courriels.append((sujet, corps, destinataire))
        return "ENVOYE", ""

    monkeypatch.setattr(envois, "envoyer_email", faux_email)
    de = f"+2267{uuid.uuid4().int % 10**7:07d}"
    reponse = {"type": "reponse", "id_origine": "inconnu", "de": de, "texte": "Merci, je passe demain",
               "media": None, "date": "2026-10-04T11:00:00Z"}
    assert _poster_retour(client, reponse).json()["doublon"] is False
    assert _poster_retour(client, reponse).json()["doublon"] is True
    # Signalée UNE fois aux super-administrateurs (e-mail), jamais par WhatsApp
    assert len(courriels) >= 1 and all("Merci, je passe demain" in c[1] for c in courriels)
    assert {c[2] for c in courriels} >= {"super@plateforme-test.bf"}
    nb = len(courriels)
    _poster_retour(client, reponse)
    assert len(courriels) == nb
    # Désinscription : tracée
    assert _poster_retour(client, {"type": "desinscription", "de": de, "date": "2026-10-04T12:00:00Z"}).status_code == 200
    # Route super-admin : les 100 derniers retours
    r = client.get("/api/admin/transmission-wa/retours", headers=super_admin)
    assert r.status_code == 200 and r.json()["chemin_retour"] == "/api/webhooks/liluvine-retour"
    types = [l["type"] for l in r.json()["retours"] if l["numero"] == de]
    assert sorted(types) == ["desinscription", "reponse"]
    assert CLE not in r.text
    _, gerant = nouvelle_boutique()
    assert client.get("/api/admin/transmission-wa/retours", headers=gerant).status_code == 403


def test_webhook_ferme_sans_configuration(client, reglages, monkeypatch):
    monkeypatch.setattr(reglages, "liluvine_wa_hmac", None)
    assert _poster_retour(client, {"type": "desinscription", "de": "+22670000000", "date": "x"}).status_code == 503


# ---- 5. WABA propre à la boutique : saisie par le gérant, jeton masqué ----
def test_saisie_waba_boutique_jeton_masque(client, nouvelle_boutique, reglages, monkeypatch):
    boutique, gerant = nouvelle_boutique()
    url = "/api/boutique/whatsapp-waba"
    r = client.get(url, headers=gerant)
    assert r.status_code == 200 and r.json()["configure"] is False and r.json()["canal_prevu"] == "liluvine"
    # Sans jeton : refus
    assert client.put(url, headers=gerant, json={"phone_number_id": "1234567890"}).status_code == 400
    # Enregistrement : le jeton n'est jamais renvoyé en clair
    r = client.put(url, headers=gerant, json={"phone_number_id": "1234567890", "access_token": "EAAG-jeton-secret"})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"] == "********" and "EAAG-jeton-secret" not in r.text
    assert r.json()["configure"] is True and r.json()["canal_prevu"] == "waba_boutique"
    assert "EAAG-jeton-secret" not in client.get(url, headers=gerant).text
    assert "EAAG-jeton-secret" not in client.get("/api/boutique", headers=gerant).text
    # En base : chiffré (déchiffrable par le serveur seulement)
    fiche = client.portal.call(lambda: db.boutiques.find_one({"id": boutique["id"]}))
    assert fiche["whatsapp_waba"]["access_token"] != "EAAG-jeton-secret"
    assert tw.waba_boutique(fiche) == ("1234567890", "EAAG-jeton-secret")
    # Ré-enregistrer avec le masque « ******** » conserve le jeton
    r = client.put(url, headers=gerant, json={"phone_number_id": "1234567890", "access_token": "********",
                                              "actif": False})
    assert r.json()["actif"] is False and r.json()["configure"] is False
    fiche = client.portal.call(lambda: db.boutiques.find_one({"id": boutique["id"]}))
    assert envois.dechiffrer(fiche["whatsapp_waba"]["access_token"]) == "EAAG-jeton-secret"
    # Identifiant du numéro : chiffres uniquement
    assert client.put(url, headers=gerant, json={"phone_number_id": "abc"}).status_code == 422

    # Bouton « Tester » : vérification chez Meta, sans repli vers un autre canal
    verifs = []

    async def faux_verifier(identifiants):
        verifs.append(identifiants)
        return {"ok": True, "numero_affiche": "+226 70 00 00 00", "nom_verifie": "Boutique", "erreur": None}

    monkeypatch.setattr(envois, "verifier_waba", faux_verifier)
    r = client.post(f"{url}/tester", headers=gerant, json={})
    assert r.status_code == 200 and r.json()["ok"] is True and verifs == [("1234567890", "EAAG-jeton-secret")]
    assert "EAAG-jeton-secret" not in r.text
    # Suppression du réglage
    assert client.delete(url, headers=gerant).json()["a_jeton"] is False
    assert client.post(f"{url}/tester", headers=gerant, json={}).status_code == 400


def test_media_waba_octets_deposes_chez_meta(reglages, monkeypatch):
    """WABA : un fichier en octets est d'abord déposé chez Meta (/media), puis envoyé par son id."""
    requetes = []

    def gerer(requete: httpx.Request):
        requetes.append(requete)
        if requete.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "MEDIA-1"})
        return httpx.Response(200, json={"messages": [{"id": "wamid.M"}]})

    vrai_client = httpx.AsyncClient
    monkeypatch.setattr(envois.httpx, "AsyncClient", lambda **kw: vrai_client(transport=httpx.MockTransport(gerer), **kw))
    media, _ = tw.normaliser_media({"type": "document", "contenu": b"PDF", "nom_fichier": "f.pdf",
                                    "mime": "application/pdf"})
    statut, erreur, mid = asyncio.run(envois.envoyer_media_waba("+22670000000", media, "Votre facture",
                                                                identifiants=("111", "jeton")))
    assert (statut, mid) == ("ENVOYE", "wamid.M") and len(requetes) == 2
    corps = json.loads(requetes[1].content)
    assert corps["type"] == "document" and corps["document"] == {"id": "MEDIA-1", "caption": "Votre facture",
                                                                 "filename": "f.pdf"}
