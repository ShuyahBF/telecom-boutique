"""Proformas -> factures, QR code chiffré des documents et espace client public
(« Mon espace » : numéro de téléphone + code à usage unique envoyé par WhatsApp)."""
import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest

import jetons_qr
import transmission_wa
from config import get_settings
from db import db


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------
def _proforma(client, a, qte=1):
    r = client.post("/api/documents", headers=a["h"], json={
        "type_document": "PRO", "client_id": a["client"]["id"], "lignes": [
            {"produit_id": a["tel"]["id"], "quantite": qte}, {"produit_id": a["service"]["id"], "quantite": 1}]})
    assert r.status_code == 201, r.text
    return r.json()


def _facture_validee(client, a):
    f = client.post("/api/documents", headers=a["h"], json={
        "client_id": a["client"]["id"], "lignes": [{"produit_id": a["service"]["id"], "quantite": 2}]}).json()
    v = client.post(f"/api/documents/{f['id']}/valider", headers=a["h"])
    assert v.status_code == 200, v.text
    return v.json()


def _jeton_qr(client, a, doc_id):
    r = client.get(f"/api/documents/{doc_id}/qr", headers=a["h"])
    assert r.status_code == 200, r.text
    return urlparse(r.json()["url"]).path.split("/q/")[1]


@pytest.fixture
def whatsapp(monkeypatch):
    """Transmission WA SIMULÉE : aucun envoi réel, les messages sont gardés ici."""
    envoyes = []

    async def faux_envoi(numero, message, **kw):
        envoyes.append({"numero": numero, "message": message, **kw})
        return {"ok": True, "canal": "waba_plateforme", "message_id": "m1", "erreur": None, "statut": "ENVOYE"}

    monkeypatch.setattr(transmission_wa, "envoyer_whatsapp", faux_envoi)
    # Limites assouplies pour les tests (chaque test réinitialise les compteurs)
    s = get_settings()
    monkeypatch.setattr(s, "espace_client_delai_renvoi_secondes", 0)
    monkeypatch.setattr(s, "espace_client_demandes_par_ip", 1000)
    monkeypatch.setattr(s, "whatsapp_code_template", None)
    asyncio.run(db.espace_client_limites.delete_many({}))
    return envoyes


def _code(envoyes):
    """Code à 6 chiffres contenu dans le dernier message envoyé."""
    import re
    return re.search(r"\b(\d{6})\b", envoyes[-1]["message"]).group(1)


def _connecter(client, whatsapp, jeton=None, slug=None, telephone="70 11 22 33"):
    r = client.post("/api/espace-client/demander-code", json={"jeton": jeton, "slug": slug, "telephone": telephone})
    assert r.status_code == 200, r.text
    v = client.post("/api/espace-client/verifier-code", json={"demande_id": r.json()["demande_id"], "code": _code(whatsapp)})
    assert v.status_code == 200, v.text
    client.cookies.clear()  # les tests utilisent l'en-tête (jeton gardé en mémoire)
    return {"X-Espace-Client": v.json()["jeton"]}


# ---------------------------------------------------------------------------
# 1. Proformas -> factures
# ---------------------------------------------------------------------------
def test_conversion_brouillon_et_liste(client, boutique_equipee):
    a = boutique_equipee
    pro = _proforma(client, a)
    liste = client.get("/api/documents", headers=a["h"], params={"type_document": "PRO"}).json()
    ligne = next(d for d in liste if d["id"] == pro["id"])
    assert ligne["convertible"] is True and ligne["convertie"] is False
    fac = client.post(f"/api/documents/{pro['id']}/convertir", headers=a["h"]).json()
    assert fac["type_document"] == "FAC" and fac["statut"] == "BROUILLON"
    # La proforma porte le lien vers la facture ; badge « Convertie » dans la liste
    relue = client.get(f"/api/documents/{pro['id']}", headers=a["h"]).json()
    assert relue["facture_generee"]["id"] == fac["id"] and relue["convertible"] is False
    liste = client.get("/api/documents", headers=a["h"], params={"type_document": "PRO"}).json()
    assert next(d for d in liste if d["id"] == pro["id"])["convertie"] is True


def test_conversion_proforma_acceptee_et_double_conversion(client, boutique_equipee):
    a = boutique_equipee
    pro = _proforma(client, a)
    # Proforma ACCEPTÉE (VALIDE) sans facture : convertible
    asyncio.run(db.documents.update_one({"id": pro["id"]}, {"$set": {"statut": "VALIDE"}}))
    r = client.post(f"/api/documents/{pro['id']}/convertir", headers=a["h"])
    assert r.status_code == 200, r.text
    # Jamais deux fois : 409 avec un message clair
    r = client.post(f"/api/documents/{pro['id']}/convertir", headers=a["h"])
    assert r.status_code == 409 and "déjà été convertie" in r.json()["detail"]
    nb = asyncio.run(db.documents.count_documents({"proforma_origine.id": pro["id"]}))
    assert nb == 1


def test_conversion_proforma_annulee_refusee(client, boutique_equipee):
    a = boutique_equipee
    pro = _proforma(client, a)
    client.post(f"/api/documents/{pro['id']}/annuler", headers=a["h"])
    assert client.post(f"/api/documents/{pro['id']}/convertir", headers=a["h"]).status_code == 409


def test_convertir_et_valider(client, boutique_equipee):
    a = boutique_equipee
    pro = _proforma(client, a)
    fac = client.post(f"/api/documents/{pro['id']}/convertir", headers=a["h"], params={"valider_facture": True}).json()
    assert fac["statut"] == "VALIDE" and fac["numero"].startswith("FAC-")
    relue = client.get(f"/api/documents/{pro['id']}", headers=a["h"]).json()
    assert relue["facture_generee"]["numero"] == fac["numero"]


def test_convertir_et_valider_stock_insuffisant(client, boutique_equipee):
    """Validation refusée (stock) : la facture reste en brouillon, le motif est renvoyé."""
    a = boutique_equipee
    pro = _proforma(client, a, qte=50)
    fac = client.post(f"/api/documents/{pro['id']}/convertir", headers=a["h"], params={"valider_facture": True}).json()
    assert fac["statut"] == "BROUILLON" and fac["validation_erreur"]


# ---------------------------------------------------------------------------
# 2. Jeton du QR code
# ---------------------------------------------------------------------------
def test_jeton_qr_aller_retour_et_numero_absent(client, boutique_equipee):
    a = boutique_equipee
    pro = _proforma(client, a)
    r = client.get(f"/api/documents/{pro['id']}/qr", headers=a["h"]).json()
    jeton = urlparse(r["url"]).path.split("/q/")[1]
    # Aucun numéro de téléphone en clair, sous aucune forme, ni dans l'URL ni dans le jeton
    for forme in ("70112233", "22670112233", "70 11 22 33"):
        assert forme not in r["url"]
    contenu = jetons_qr.lire_jeton_document(jeton)
    assert contenu["b"] == a["boutique"]["id"] and contenu["c"] == a["client"]["id"]
    assert contenu["n"] == pro["numero"] and contenu["d"] == pro["date"]
    assert contenu["e"] == jetons_qr.empreinte_telephone(a["boutique"]["id"], "+226 70 11 22 33")
    assert "70112233" not in str(contenu)
    # Deux jetons du même document sont différents (non devinables)
    assert _jeton_qr(client, a, pro["id"]) != jeton
    # Page publique ouverte par le QR code : boutique, sans aucune donnée du client
    page = client.get(f"/api/espace-client/qr/{jeton}").json()
    assert page["boutique"]["nom"] == a["boutique"]["nom"] and page["boutique"]["page_publique"] is True
    assert "client" not in page and "Client Test" not in str(page)


def test_jeton_qr_falsifie_refuse(client, boutique_equipee):
    a = boutique_equipee
    jeton = _jeton_qr(client, a, _proforma(client, a)["id"])
    falsifie = jeton[:20] + ("A" if jeton[20] != "A" else "B") + jeton[21:]
    assert jetons_qr.lire_jeton_document(falsifie) is None
    assert client.get(f"/api/espace-client/qr/{falsifie}").status_code == 404
    assert client.get("/api/espace-client/qr/nimportequoi").status_code == 404


def test_page_minimale_si_vitrine_fermee(client, boutique_equipee):
    a = boutique_equipee
    jeton = _jeton_qr(client, a, _proforma(client, a)["id"])
    asyncio.run(db.boutiques.update_one({"id": a["boutique"]["id"]}, {"$set": {"validee": False}}))
    page = client.get(f"/api/espace-client/qr/{jeton}").json()
    assert page["boutique"]["page_publique"] is False and page["boutique"]["nom"]


# ---------------------------------------------------------------------------
# 3. Espace client : connexion
# ---------------------------------------------------------------------------
def test_parcours_complet_par_qr(client, boutique_equipee, whatsapp):
    a = boutique_equipee
    fac = _facture_validee(client, a)
    jeton = _jeton_qr(client, a, fac["id"])
    h = _connecter(client, whatsapp, jeton=jeton)
    # Code envoyé par la Transmission WA, au nom de la boutique, au numéro du client
    assert whatsapp[-1]["numero"] == "+22670112233" and whatsapp[-1]["boutique"]["id"] == a["boutique"]["id"]
    moi = client.get("/api/espace-client/moi", headers=h).json()
    assert moi["client"]["nom"] == "Client Test" and moi["resume"]["nb_factures"] == 1
    docs = client.get("/api/espace-client/documents", headers=h).json()
    assert [d["id"] for d in docs] == [fac["id"]]
    detail = client.get(f"/api/espace-client/documents/{fac['id']}", headers=h).json()
    assert detail["document"]["lignes"] and "cree_par" not in detail["document"]
    assert client.get("/api/espace-client/sav", headers=h).status_code == 200
    assert client.get("/api/espace-client/reglements", headers=h).status_code == 200
    # Connexion journalisée, avec l'adresse IP masquée
    j = asyncio.run(db.espace_client_connexions.find_one({"boutique_id": a["boutique"]["id"]}))
    assert j["client_id"] == a["client"]["id"] and j["ip"]
    # Le code n'est jamais gardé en clair
    code = asyncio.run(db.espace_client_codes.find_one({"boutique_id": a["boutique"]["id"]}))
    assert _code(whatsapp) not in str(code)
    # Déconnexion : la session ne sert plus
    assert client.post("/api/espace-client/deconnexion", headers=h).status_code == 200
    assert client.get("/api/espace-client/moi", headers=h).status_code == 401


def test_parcours_par_vitrine_sans_qr(client, boutique_equipee, whatsapp):
    a = boutique_equipee
    h = _connecter(client, whatsapp, slug=a["boutique"]["slug"], telephone="+22670112233")
    assert client.get("/api/espace-client/moi", headers=h).json()["client"]["nom"] == "Client Test"


def test_mauvais_numero_refuse(client, boutique_equipee, whatsapp):
    a = boutique_equipee
    jeton = _jeton_qr(client, a, _proforma(client, a)["id"])
    r = client.post("/api/espace-client/demander-code", json={"jeton": jeton, "telephone": "76 99 99 99"})
    assert r.status_code == 403 and not whatsapp


def test_code_faux_puis_cinq_essais(client, boutique_equipee, whatsapp):
    a = boutique_equipee
    r = client.post("/api/espace-client/demander-code", json={"slug": a["boutique"]["slug"], "telephone": "70112233"})
    demande = r.json()["demande_id"]
    bon = _code(whatsapp)
    faux = "000000" if bon != "000000" else "111111"
    for i in range(4):
        r = client.post("/api/espace-client/verifier-code", json={"demande_id": demande, "code": faux})
        assert r.status_code == 400 and f"{4 - i} essai" in r.json()["detail"]
    r = client.post("/api/espace-client/verifier-code", json={"demande_id": demande, "code": faux})
    assert r.status_code == 429
    # Même le bon code est refusé après 5 essais
    r = client.post("/api/espace-client/verifier-code", json={"demande_id": demande, "code": bon})
    assert r.status_code == 400


def test_code_expire_et_usage_unique(client, boutique_equipee, whatsapp):
    a = boutique_equipee
    r = client.post("/api/espace-client/demander-code", json={"slug": a["boutique"]["slug"], "telephone": "70112233"})
    demande = r.json()["demande_id"]
    passe = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    asyncio.run(db.espace_client_codes.update_one({"id": demande}, {"$set": {"expire_a": passe}}))
    r = client.post("/api/espace-client/verifier-code", json={"demande_id": demande, "code": _code(whatsapp)})
    assert r.status_code == 400 and "expiré" in r.json()["detail"]
    # Nouveau code : il ne sert qu'une fois
    r = client.post("/api/espace-client/demander-code", json={"slug": a["boutique"]["slug"], "telephone": "70112233"})
    demande = r.json()["demande_id"]
    corps = {"demande_id": demande, "code": _code(whatsapp)}
    assert client.post("/api/espace-client/verifier-code", json=corps).status_code == 200
    assert client.post("/api/espace-client/verifier-code", json=corps).status_code == 400
    client.cookies.clear()


def test_limitation_par_numero_et_par_ip(client, boutique_equipee, whatsapp, monkeypatch):
    a = boutique_equipee
    corps = {"slug": a["boutique"]["slug"], "telephone": "70112233"}
    # Par numéro : 3 codes par quart d'heure
    for _ in range(3):
        assert client.post("/api/espace-client/demander-code", json=corps).status_code == 200
    assert client.post("/api/espace-client/demander-code", json=corps).status_code == 429
    # Délai minimal entre deux codes
    asyncio.run(db.espace_client_limites.delete_many({}))
    monkeypatch.setattr(get_settings(), "espace_client_delai_renvoi_secondes", 60)
    assert client.post("/api/espace-client/demander-code", json=corps).status_code == 200
    assert client.post("/api/espace-client/demander-code", json=corps).status_code == 429
    # Par adresse IP (même avec des numéros inconnus)
    asyncio.run(db.espace_client_limites.delete_many({}))
    monkeypatch.setattr(get_settings(), "espace_client_demandes_par_ip", 3)
    for _ in range(3):
        client.post("/api/espace-client/demander-code", json={**corps, "telephone": "76000000"})
    assert client.post("/api/espace-client/demander-code", json=corps).status_code == 429


def test_repli_sms_puis_message_clair(client, boutique_equipee, monkeypatch):
    """WhatsApp en échec : SMS de la boutique s'il est actif, sinon message clair (503)."""
    import sms_boutiques
    a = boutique_equipee
    s = get_settings()
    monkeypatch.setattr(s, "espace_client_delai_renvoi_secondes", 0)
    monkeypatch.setattr(s, "espace_client_demandes_par_ip", 1000)
    asyncio.run(db.espace_client_limites.delete_many({}))

    async def echec(numero, message, **kw):
        return {"ok": False, "canal": None, "message_id": None, "erreur": "x", "statut": "NON_CONFIGURE"}
    monkeypatch.setattr(transmission_wa, "envoyer_whatsapp", echec)
    corps = {"slug": a["boutique"]["slug"], "telephone": "70112233"}
    r = client.post("/api/espace-client/demander-code", json=corps)
    assert r.status_code == 503 and "Contactez la boutique" in r.json()["detail"]

    sms = []
    monkeypatch.setattr(sms_boutiques, "peut_envoyer", lambda b: True)

    async def faux_sms(b, telephone, texte, **kw):
        sms.append(texte)
        return {"statut": "ENVOYE"}
    monkeypatch.setattr(sms_boutiques, "envoyer", faux_sms)
    r = client.post("/api/espace-client/demander-code", json=corps)
    assert r.status_code == 200 and r.json()["canal"] == "SMS" and sms


# ---------------------------------------------------------------------------
# 4. Cloisonnement de la session
# ---------------------------------------------------------------------------
def test_session_cloisonnee(client, nouvelle_boutique, boutique_equipee, whatsapp):
    a = boutique_equipee
    fac_a = _facture_validee(client, a)
    # Autre client de la MÊME boutique
    autre = client.post("/api/clients", headers=a["h"], json={"nom": "Autre", "telephone": "76 55 44 33"}).json()
    f = client.post("/api/documents", headers=a["h"], json={
        "client_id": autre["id"], "lignes": [{"produit_id": a["service"]["id"], "quantite": 1}]}).json()
    fac_autre = client.post(f"/api/documents/{f['id']}/valider", headers=a["h"]).json()
    # AUTRE boutique, client avec le MÊME numéro
    b2, h2 = nouvelle_boutique()
    cli2 = client.post("/api/clients", headers=h2, json={"nom": "Homonyme", "telephone": "70 11 22 33"}).json()
    cat2 = client.post("/api/categories", headers=h2, json={"nom": "R"}).json()
    serv2 = client.post("/api/produits", headers=h2, json={"reference": "S9", "nom": "Service", "type_produit": "SER",
                                                           "categorie_id": cat2["id"], "prix_vente": 1000}).json()
    f2 = client.post("/api/documents", headers=h2, json={"client_id": cli2["id"], "lignes": [
        {"produit_id": serv2["id"], "quantite": 1}]}).json()
    fac_b2 = client.post(f"/api/documents/{f2['id']}/valider", headers=h2).json()

    h = _connecter(client, whatsapp, jeton=_jeton_qr(client, a, fac_a["id"]))
    ids = {d["id"] for d in client.get("/api/espace-client/documents", headers=h).json()}
    assert fac_a["id"] in ids and fac_autre["id"] not in ids and fac_b2["id"] not in ids
    assert client.get(f"/api/espace-client/documents/{fac_autre['id']}", headers=h).status_code == 404
    assert client.get(f"/api/espace-client/documents/{fac_b2['id']}", headers=h).status_code == 404
    # Jeton de session falsifié, ou absent : refusé
    assert client.get("/api/espace-client/moi", headers={"X-Espace-Client": h["X-Espace-Client"][:-3] + "AAA"}).status_code == 401
    assert client.get("/api/espace-client/moi").status_code == 401
    # Un jeton de QR code ne peut pas servir de jeton de session
    assert client.get("/api/espace-client/moi", headers={"X-Espace-Client": _jeton_qr(client, a, fac_a["id"])}).status_code == 401


def test_session_expiree_apres_inactivite(client, boutique_equipee, whatsapp):
    a = boutique_equipee
    h = _connecter(client, whatsapp, slug=a["boutique"]["slug"])
    vieux = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
    asyncio.run(db.espace_client_sessions.update_many({"boutique_id": a["boutique"]["id"]},
                                                      {"$set": {"derniere_activite": vieux}}))
    assert client.get("/api/espace-client/moi", headers=h).status_code == 401
