"""Lot B — inscription libre d'un commerçant (« Créer ma boutique ») et connexion
par téléphone + code WhatsApp.

Les envois (WhatsApp, SMS, e-mail) sont remplacés par des DOUBLES qui notent les
messages au lieu de les envoyer : aucun accès réseau pendant les tests. Chaque test
utilise son propre numéro et sa propre adresse IP (les limites comptent par numéro
et par adresse IP)."""
import re
import time
from datetime import datetime, timedelta, timezone

import pytest

import envois_plateforme
import identifiants
from db import db

_n = {"i": 0}


# Lot D — correction d'un test intermittent : l'ancienne version collait le compteur et
# l'horloge (« 12 » + « 3456 » = « 1 » + « 23456 ») et pouvait redonner un numéro ou une
# adresse IP déjà utilisés (code « déjà inscrit », limite d'envoi atteinte…). Désormais :
# un décalage tiré une fois par session (< 4 000, pour rester sous les numéros du lot C
# « +22674300001… ») suivi du compteur : deux appels ne donnent jamais la même valeur.
_DEPART = time.time_ns() // 1000 % 4000


def unique() -> int:
    _n["i"] += 1
    return _DEPART * 1000 + _n["i"]


def numero_unique() -> str:
    """Numéro burkinabè local (8 chiffres, commence par 6) jamais utilisé dans la session de tests."""
    return f"6{unique() % 10_000_000:07d}"


def e164(numero_local: str) -> str:
    return "+226" + numero_local


def _adresse_ip(k: int) -> dict:
    """Adresse 10.x.y.z tirée d'un nombre : deux nombres différents (< 15 millions) -> deux adresses différentes."""
    return {"X-Forwarded-For": f"10.{k // 62_500 % 250}.{k // 250 % 250}.{k % 250}"}


def ip() -> dict:
    """Adresse IP différente pour chaque appel de test."""
    return _adresse_ip(unique())


@pytest.fixture
def boite(monkeypatch):
    """Capture les messages envoyés ; `boite.statuts[canal]` règle la réponse du faux fournisseur."""
    class Boite(list):
        def code(self, a):
            """Dernier code à 6 chiffres envoyé à ce numéro."""
            for m in reversed(self):
                trouve = re.search(r"\b(\d{6})\b", m["texte"])
                if m["a"] == a and trouve and m["statut"] == "ENVOYE":
                    return trouve.group(1)
            raise AssertionError(f"Aucun code envoyé à {a}")

    b = Boite()
    b.statuts = {"whatsapp": "ENVOYE", "sms": "ENVOYE", "email": "ENVOYE"}

    async def faux_whatsapp(telephone, variables, texte, *, modele=None, composants=None, **_):
        statut = b.statuts["whatsapp"]
        b.append({"canal": "whatsapp", "a": telephone, "texte": texte, "statut": statut})
        return statut, "" if statut == "ENVOYE" else "refusé (test)"

    async def faux_sms(telephone, texte):
        statut = b.statuts["sms"]
        b.append({"canal": "sms", "a": telephone, "texte": texte, "statut": statut})
        return statut, "" if statut == "ENVOYE" else "refusé (test)"

    async def faux_email(sujet, corps, destinataire):
        b.append({"canal": "email", "a": destinataire, "texte": corps, "statut": b.statuts["email"]})
        return b.statuts["email"], ""

    monkeypatch.setattr(envois_plateforme, "envoyer_whatsapp", faux_whatsapp)
    monkeypatch.setattr(envois_plateforme, "envoyer_sms", faux_sms)
    monkeypatch.setattr(envois_plateforme, "envoyer_email", faux_email)
    return b


def formulaire(numero: str, **extra) -> dict:
    """Formulaire « Créer ma boutique » complet et valable."""
    n = unique()
    return {"telephone": numero, "prenom": "Awa", "nom": "Ouédraogo", "nom_boutique": f"Mode Awa {n}",
            "ville": "Ouagadougou", "adresse": "Quartier Gounghin", "latitude": 12.3657, "longitude": -1.5339,
            "secteur": "pret_a_porter", "accepte_conditions": True, **extra}


def inscrire(client, boite, numero=None, **extra):
    """Inscription complète (code demandé puis confirmé) -> (réponse, formulaire, numéro local)."""
    numero = numero or numero_unique()
    f = formulaire(numero, **extra)
    entetes = ip()
    r = client.post("/api/inscription/demander-code", json=f, headers=entetes)
    assert r.status_code == 200, r.text
    r = client.post("/api/inscription/confirmer", json={**f, "code": boite.code(e164(numero))}, headers=entetes)
    client.cookies.clear()  # les tests suivants n'héritent pas de la session
    return r, f, numero


# ---------------------------------------------------------------------------
# Inscription
# ---------------------------------------------------------------------------
def test_secteurs_publics_pour_le_formulaire(client):
    r = client.get("/api/secteurs")
    assert r.status_code == 200
    codes = {s["code"] for s in r.json()}
    assert {"telecom", "pret_a_porter"} <= codes
    assert all(s.get("icone") for s in r.json())


def test_envoi_du_code_puis_creation_de_la_boutique(client, boite, super_admin):
    numero = numero_unique()
    f = formulaire(numero)
    entetes = ip()
    r = client.post("/api/inscription/demander-code", json=f, headers=entetes)
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["canal"] == "WhatsApp" and corps["validite_minutes"] == 10
    # Le code est parti par WhatsApp, sur le numéro au format international
    assert boite[-1]["canal"] == "whatsapp" and boite[-1]["a"] == e164(numero)
    code = boite.code(e164(numero))
    # Ni le code ni le numéro complet dans la réponse
    assert numero not in r.text and code not in r.text
    # Le code n'est pas stocké en clair
    doc = client.portal.call(lambda: db.otp_whatsapp.find_one({"telephone": e164(numero)}, {"_id": 0}))
    assert doc and code not in str(doc)
    # Pas de boutique tant que le code n'est pas validé
    assert client.portal.call(lambda: db.boutiques.count_documents({"nom": f["nom_boutique"]})) == 0

    r = client.post("/api/inscription/confirmer", json={**f, "code": code}, headers=entetes)
    assert r.status_code == 201, r.text
    session = r.json()
    client.cookies.clear()
    boutique, user = session["boutique"], session["user"]
    assert boutique["validee"] is False and boutique["origine"] == "inscription"
    assert boutique["secteur"] == "pret_a_porter"
    assert boutique["ville"] == "Ouagadougou" and boutique["adresse"] == "Quartier Gounghin"
    assert boutique["latitude"] == pytest.approx(12.3657)
    assert boutique["options_actives"]["parametres"] is True  # dossier KYC accessible
    assert session["inscription"]["code_boutique"] == boutique["code_marchand"]
    assert user["role"] == "dg" and user["telephone"] == e164(numero)
    assert user["a_mot_de_passe"] is False and "password_hash" not in user
    assert user["nom"] == "Awa Ouédraogo" and user["prenom"] == "Awa" and user["nom_famille"] == "Ouédraogo"
    # Compte sans e-mail : aucun champ « email » (index d'unicité partiel)
    fiche = client.portal.call(lambda: db.users.find_one({"id": user["id"]}, {"_id": 0}))
    assert "email" not in fiche and fiche["password_hash"] == ""
    # Session immédiatement utilisable
    h = {"Authorization": f"Bearer {session['access_token']}"}
    me = client.get("/api/auth/me", headers=h)
    assert me.status_code == 200 and me.json()["boutique"]["validee"] is False
    # Vitrine publique invisible tant que la boutique n'est pas validée
    assert client.get(f"/api/public/b/{boutique['slug']}").status_code == 404
    # Le code est à usage unique : le même numéro ne peut plus s'inscrire
    r = client.post("/api/inscription/confirmer", json={**f, "code": code}, headers=ip())
    assert r.status_code == 409
    # Le super-admin la voit dans la liste, avec son origine, puis la valide
    liste = client.get("/api/plateforme/boutiques", headers=super_admin).json()
    b = next(x for x in liste if x["id"] == boutique["id"])
    assert b["origine"] == "inscription" and b["validee"] is False and b["inscription"]["telephone_verifie"] == e164(numero)
    assert client.post(f"/api/plateforme/boutiques/{boutique['id']}/valider", headers=super_admin).status_code == 200
    assert client.get(f"/api/public/b/{boutique['slug']}").status_code == 200


def test_boutique_non_validee_parametres_et_kyc_accessibles(client, boite):
    r, _, _ = inscrire(client, boite, secteur="telecom")
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # Même pour le télécom (aucun module d'office), Paramètres et KYC sont ouverts
    assert client.get("/api/boutique", headers=h).status_code == 200
    assert client.get("/api/boutique/kyc/types", headers=h).status_code == 200
    # Le DG définit son premier mot de passe sans « ancien » mot de passe
    r = client.post("/api/auth/mot-de-passe", headers=h, json={"nouveau": "mon-mdp-2026"})
    assert r.status_code == 200, r.text


def test_mauvais_code_et_essais_maximum(client, boite):
    numero = numero_unique()
    f = formulaire(numero)
    entetes = ip()
    assert client.post("/api/inscription/demander-code", json=f, headers=entetes).status_code == 200
    bon = boite.code(e164(numero))
    faux = f"{(int(bon) + 1) % 1_000_000:06d}"
    r = client.post("/api/inscription/confirmer", json={**f, "code": faux}, headers=entetes)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "code_faux"
    for _ in range(3):  # 2e, 3e, 4e essais faux
        assert client.post("/api/inscription/confirmer", json={**f, "code": faux}, headers=entetes).status_code == 400
    r = client.post("/api/inscription/confirmer", json={**f, "code": faux}, headers=entetes)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "code_epuise"
    # Le code est détruit : même le bon code ne passe plus
    r = client.post("/api/inscription/confirmer", json={**f, "code": bon}, headers=entetes)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "code_expire"
    assert client.portal.call(lambda: db.boutiques.count_documents({"nom": f["nom_boutique"]})) == 0


def test_code_expire(client, boite):
    numero = numero_unique()
    f = formulaire(numero)
    entetes = ip()
    assert client.post("/api/inscription/demander-code", json=f, headers=entetes).status_code == 200
    code = boite.code(e164(numero))
    passe = datetime.now(timezone.utc) - timedelta(minutes=1)
    client.portal.call(lambda: db.otp_whatsapp.update_one({"telephone": e164(numero)},
                                                          {"$set": {"expire_iso": passe.isoformat()}}))
    r = client.post("/api/inscription/confirmer", json={**f, "code": code}, headers=entetes)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "code_expire"


def test_limites_d_envoi(client, boite, monkeypatch):
    numero = numero_unique()
    f = formulaire(numero)
    assert client.post("/api/inscription/demander-code", json=f, headers=ip()).status_code == 200
    # 1 par minute pour un même numéro (même depuis une autre adresse IP)
    assert client.post("/api/inscription/demander-code", json=f, headers=ip()).status_code == 429
    # 5 par heure pour une même adresse IP (sans délai d'une minute pour aller vite)
    monkeypatch.setattr(identifiants, "DELAI_ENTRE_ENVOIS", timedelta(0))
    entetes = ip()
    for _ in range(5):
        assert client.post("/api/inscription/demander-code", json=formulaire(numero_unique()),
                           headers=entetes).status_code == 200
    assert client.post("/api/inscription/demander-code", json=formulaire(numero_unique()),
                       headers=entetes).status_code == 429


def test_envoi_impossible(client, boite):
    boite.statuts.update(whatsapp="ECHEC", sms="ECHEC")
    numero = numero_unique()
    r = client.post("/api/inscription/demander-code", json=formulaire(numero), headers=ip())
    assert r.status_code == 502
    assert client.portal.call(lambda: db.otp_whatsapp.count_documents({"telephone": e164(numero)})) == 0


def test_formulaire_controle(client, boite):
    numero = numero_unique()
    assert client.post("/api/inscription/demander-code", json=formulaire(numero, accepte_conditions=False),
                       headers=ip()).status_code == 400
    assert client.post("/api/inscription/demander-code", json=formulaire(numero, secteur="inconnu"),
                       headers=ip()).status_code == 400
    assert client.post("/api/inscription/demander-code", json=formulaire(numero, nom_boutique="test"),
                       headers=ip()).status_code == 400
    assert client.post("/api/inscription/demander-code", json=formulaire("123"), headers=ip()).status_code in (400, 422)
    assert client.post("/api/inscription/demander-code", json=formulaire(numero, latitude=12.3, longitude=None),
                       headers=ip()).status_code == 400
    assert client.post("/api/inscription/demander-code", json=formulaire(numero, email="x@yopmail.com"),
                       headers=ip()).status_code == 400
    assert not boite  # aucun code envoyé pour un formulaire refusé


def test_numero_deja_inscrit(client, boite, nouvelle_boutique):
    # 1) Numéro d'un DG inscrit en ligne
    r, _, numero = inscrire(client, boite)
    assert r.status_code == 201
    r = client.post("/api/inscription/demander-code", json=formulaire(numero), headers=ip())
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "numero_deja_inscrit"
    assert "déjà une boutique" in r.json()["detail"]["message"]
    # 2) Numéro de DG saisi sur la fiche d'une boutique existante (format local)
    autre = numero_unique()
    nouvelle_boutique(dg_telephone=autre[:2] + " " + autre[2:])
    r = client.post("/api/inscription/demander-code", json=formulaire(autre), headers=ip())
    assert r.status_code == 409 and "connectez-vous" in r.json()["detail"]["message"]
    # 3) E-mail déjà utilisé
    r = client.post("/api/inscription/demander-code",
                    json=formulaire(numero_unique(), email="super@plateforme-test.bf"), headers=ip())
    assert r.status_code == 409


def test_inscription_avec_email(client, boite):
    courriel = f"awa{unique()}@exemple.bf"
    r, _, _ = inscrire(client, boite, email=courriel)
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email"] == courriel


# ---------------------------------------------------------------------------
# Connexion par téléphone + code WhatsApp
# ---------------------------------------------------------------------------
def test_connexion_otp_d_un_compte_existant(client, boite):
    r, _, numero = inscrire(client, boite)
    assert r.status_code == 201
    entetes = ip()
    r = client.post("/api/auth/whatsapp/demander-code", json={"telephone": numero}, headers=entetes)
    assert r.status_code == 200, r.text
    code = boite.code(e164(numero))
    # Mauvais code refusé
    faux = f"{(int(code) + 7) % 1_000_000:06d}"
    r = client.post("/api/auth/whatsapp/connexion", json={"telephone": numero, "code": faux}, headers=entetes)
    assert r.status_code == 400
    r = client.post("/api/auth/whatsapp/connexion", json={"telephone": numero, "code": code}, headers=entetes)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["telephone"] == e164(numero) and r.json()["boutique"]["validee"] is False
    assert "set-cookie" in r.headers
    client.cookies.clear()
    # Code à usage unique
    r = client.post("/api/auth/whatsapp/connexion", json={"telephone": numero, "code": code}, headers=entetes)
    assert r.status_code == 400


def test_connexion_otp_numero_inconnu_meme_reponse(client, boite):
    connu_r, _, connu = inscrire(client, boite)
    assert connu_r.status_code == 201
    inconnu = numero_unique()
    r1 = client.post("/api/auth/whatsapp/demander-code", json={"telephone": connu}, headers=ip())
    r2 = client.post("/api/auth/whatsapp/demander-code", json={"telephone": inconnu}, headers=ip())
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["message"] == r2.json()["message"]
    assert not [m for m in boite if m["a"] == e164(inconnu)]  # rien n'est envoyé à un inconnu
    r = client.post("/api/auth/whatsapp/connexion", json={"telephone": inconnu, "code": "123456"}, headers=ip())
    assert r.status_code == 400


def test_connexion_mot_de_passe_inchangee(client, nouvelle_boutique):
    """La connexion historique (ID boutique + e-mail + mot de passe) marche à l'identique,
    et un compte sans mot de passe ne s'ouvre jamais par mot de passe vide ou quelconque."""
    boutique, h = nouvelle_boutique()
    assert client.get("/api/auth/me", headers=h).json()["user"]["a_mot_de_passe"] is True
    r = client.post("/api/auth/login", json={"code_boutique": boutique["code_marchand"],
                                             "identifiant": "inconnu@test.bf", "password": "x"})
    assert r.status_code == 401


def test_compte_sans_mot_de_passe_refuse_par_mot_de_passe(client, boite):
    r, _, numero = inscrire(client, boite)
    code_boutique = r.json()["boutique"]["code_marchand"]
    r = client.post("/api/auth/login", json={"code_boutique": code_boutique, "identifiant": numero,
                                             "password": "nimportequoi"})
    assert r.status_code == 401


def test_consentement_whatsapp_a_l_inscription(client, boite, monkeypatch):
    """Lot 55 — case facultative : accord noté (date, moyen, IP) seulement si cochée ; transmis à SAWALI ; IP jamais renvoyée au site."""
    import export_contacts_sawali as E
    monkeypatch.setenv("SAWALI_CONTACTS_HMAC", "cle-contacts-test")
    r_oui, _, num_oui = inscrire(client, boite, accepte_whatsapp=True)
    r_non, _, num_non = inscrire(client, boite)                      # case non cochée
    assert r_oui.status_code == 201 and r_non.status_code == 201
    oui = client.portal.call(lambda: db.users.find_one({"telephone": e164(num_oui)}, {"_id": 0}))
    non = client.portal.call(lambda: db.users.find_one({"telephone": e164(num_non)}, {"_id": 0}))
    assert oui["accepte_whatsapp"] is True and oui["accepte_whatsapp_moyen"] == "inscription"
    assert oui["accepte_whatsapp_le"] and oui["accepte_whatsapp_ip"]
    assert "accepte_whatsapp" not in non                              # jamais d'accord inventé
    assert "accepte_whatsapp_ip" not in r_oui.text                    # la preuve reste côté serveur
    contacts = {c["telephone"]: c for c in client.portal.call(E.tous_les_contacts, db)}
    assert contacts[e164(num_oui).lstrip("+")]["accepte_whatsapp"] is True and contacts[e164(num_oui).lstrip("+")]["accepte_le"]
    assert "accepte_whatsapp" not in contacts[e164(num_non).lstrip("+")]
