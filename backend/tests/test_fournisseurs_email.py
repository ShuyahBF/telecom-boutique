"""Choix du service d'envoi des e-mails : Resend, ZeptoMail (Zoho), Brevo ou SMTP,
pour la plateforme (écran Paramètres) et pour chaque boutique. httpx est simulé :
aucun appel réseau. Les clés sont fictives."""
import smtplib

import httpx
import pytest

import envois_plateforme as envois
from config import get_settings
from db import db


class FausseReponse:
    """Réponse simulée d'une API d'envoi."""
    def __init__(self, code=200, corps=None):
        self.status_code, self._corps = code, corps if corps is not None else {"id": "e-1"}
        self.text = str(self._corps)

    def json(self):
        return self._corps


@pytest.fixture
def api(monkeypatch, client):
    """Capture chaque appel HTTP ; aucune variable de repli ; réglages de la plateforme effacés avant et après."""
    s = get_settings()
    for champ in ("resend_api_key", "resend_expediteur", "brevo_api_key", "zeptomail_api_key",
                  "email_expediteur", "plateforme_smtp_hote", "plateforme_expediteur"):
        monkeypatch.setattr(s, champ, None)
    appels = {"liste": [], "reponse": FausseReponse()}

    async def faux_post(self, url, json=None, headers=None, **kw):
        appels["liste"].append({"url": url, "json": json, "headers": headers})
        return appels["reponse"]

    monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)
    client.portal.call(lambda: db.parametres_plateforme.delete_one({"_id": "smtp"}))
    yield appels
    client.portal.call(lambda: db.parametres_plateforme.delete_one({"_id": "smtp"}))


def _envoyer(client, *args, **kw):
    return client.portal.call(lambda: envois.envoyer_par_api(*args, **kw))


# ---------------------------------------------------------------------------
# Forme exacte des requêtes de chaque fournisseur
# ---------------------------------------------------------------------------
def test_requete_resend(client, api):
    _envoyer(client, "resend", "cle_test", "noreply@exemple.com", "Ma <Boutique>\n", "c@exemple.bf",
             "Sujet", "Corps", reponse_a="contact@boutique.bf")
    a = api["liste"][-1]
    assert a["url"] == "https://api.resend.com/emails"
    assert a["headers"] == {"Authorization": "Bearer cle_test"}
    # Nom nettoyé (sans < > ni retour à la ligne)
    assert a["json"] == {"from": "Ma Boutique <noreply@exemple.com>", "to": ["c@exemple.bf"], "subject": "Sujet",
                         "text": "Corps", "reply_to": "contact@boutique.bf"}


def test_requete_brevo(client, api):
    api["reponse"] = FausseReponse(201, {"messageId": "m-1"})
    _envoyer(client, "brevo", "cle_test", "noreply@exemple.com", "adLyn", "c@exemple.bf", "Sujet", "Corps",
             reponse_a="contact@boutique.bf")
    a = api["liste"][-1]
    assert a["url"] == "https://api.brevo.com/v3/smtp/email"
    assert a["headers"] == {"api-key": "cle_test", "accept": "application/json"}
    assert a["json"] == {"sender": {"name": "adLyn", "email": "noreply@exemple.com"}, "to": [{"email": "c@exemple.bf"}],
                         "subject": "Sujet", "textContent": "Corps", "replyTo": {"email": "contact@boutique.bf"}}
    # Sans adresse de réponse : pas de champ replyTo
    _envoyer(client, "brevo", "cle_test", "noreply@exemple.com", "adLyn", "c@exemple.bf", "Sujet", "Corps")
    assert "replyTo" not in api["liste"][-1]["json"]


def test_requete_zeptomail(client, api):
    api["reponse"] = FausseReponse(201, {"data": [], "message": "OK"})
    _envoyer(client, "zeptomail", "cle_test", "noreply@exemple.com", "adLyn", "c@exemple.bf", "Sujet", "Corps",
             reponse_a="contact@boutique.bf", zeptomail_hote="api.zeptomail.eu")
    a = api["liste"][-1]
    assert a["url"] == "https://api.zeptomail.eu/v1.1/email"
    assert a["headers"]["Authorization"] == "Zoho-enczapikey cle_test"
    assert a["json"] == {"from": {"address": "noreply@exemple.com", "name": "adLyn"},
                         "to": [{"email_address": {"address": "c@exemple.bf"}}], "subject": "Sujet",
                         "textbody": "Corps", "reply_to": [{"address": "contact@boutique.bf"}]}
    # Clé collée avec son préfixe : il n'est pas doublé ; hôte inconnu -> .com
    _envoyer(client, "zeptomail", "Zoho-enczapikey cle_test", "noreply@exemple.com", "adLyn", "c@exemple.bf",
             "Sujet", "Corps", zeptomail_hote="pirate.exemple.com")
    a = api["liste"][-1]
    assert a["headers"]["Authorization"] == "Zoho-enczapikey cle_test"
    assert a["url"] == "https://api.zeptomail.com/v1.1/email"


@pytest.mark.parametrize("fournisseur,code,corps,attendu", [
    ("resend", 403, {"message": "The domain is not verified"}, "Resend 403 : The domain is not verified"),
    ("brevo", 401, {"code": "unauthorized", "message": "Key not found"}, "Brevo 401 : Key not found"),
    ("zeptomail", 400, {"error": {"message": "Invalid API Token", "details": [{"message": "cle_test refusee"}]}},
     "ZeptoMail 400 : Invalid API Token : *** refusee"),
])
def test_erreur_fournisseur_remontee(client, api, fournisseur, code, corps, attendu):
    # Le message du fournisseur est remonté, jamais la clé
    api["reponse"] = FausseReponse(code, corps)
    with pytest.raises(envois.ErreurEnvoi) as e:
        _envoyer(client, fournisseur, "cle_test", "noreply@exemple.com", "adLyn", "c@exemple.bf", "S", "C")
    assert str(e.value) == attendu and "cle_test" not in str(e.value)


# ---------------------------------------------------------------------------
# Réglages de la plateforme
# ---------------------------------------------------------------------------
def test_plateforme_brevo_puis_zeptomail(client, super_admin, nouvelle_boutique, api):
    _, h = nouvelle_boutique()
    reglage = {"fournisseur": "brevo", "expediteur": "noreply@adlyn.bf", "nom_expediteur": "adLyn", "cle_api": "cle_test_brevo"}
    assert client.put("/api/plateforme/parametres/email", headers=h, json=reglage).status_code == 403  # super-admin seul
    r = client.put("/api/plateforme/parametres/email", headers=super_admin, json=reglage)
    assert r.status_code == 200, r.text
    assert r.json()["fournisseur"] == "brevo" and r.json()["a_cle"] is True and r.json()["pret"] is True
    assert "cle_test_brevo" not in r.text
    # En base : clé chiffrée, jamais en clair
    doc = client.portal.call(lambda: db.parametres_plateforme.find_one({"_id": "smtp"}))
    assert "cle_test_brevo" not in str(doc) and envois.dechiffrer(doc["cles_chiffrees"]["brevo"]) == "cle_test_brevo"
    # Essai : réglages enregistrés utilisés
    api["reponse"] = FausseReponse(201, {"messageId": "m-1"})
    r = client.post("/api/plateforme/parametres/email/essai", headers=super_admin, json={"destinataire": "moi@exemple.bf"})
    assert r.status_code == 200, r.text
    assert api["liste"][-1]["headers"]["api-key"] == "cle_test_brevo"
    assert api["liste"][-1]["json"]["sender"] == {"name": "adLyn", "email": "noreply@adlyn.bf"}
    # Erreur du fournisseur affichée par le bouton d'essai
    api["reponse"] = FausseReponse(400, {"code": "invalid_parameter", "message": "sender is not valid"})
    r = client.post("/api/plateforme/parametres/email/essai", headers=super_admin, json={"destinataire": "moi@exemple.bf"})
    assert r.status_code == 400 and "Brevo 400 : sender is not valid" in r.json()["detail"]

    # Passage à ZeptoMail (.eu), puis retour à Brevo sans retaper la clé : elle est conservée
    client.put("/api/plateforme/parametres/email", headers=super_admin, json={
        **reglage, "fournisseur": "zeptomail", "cle_api": "cle_test_zepto", "zeptomail_hote": "api.zeptomail.eu"})
    api["reponse"] = FausseReponse(201, {"message": "OK"})
    client.post("/api/plateforme/parametres/email/essai", headers=super_admin, json={"destinataire": "moi@exemple.bf"})
    assert api["liste"][-1]["url"] == "https://api.zeptomail.eu/v1.1/email"
    assert api["liste"][-1]["headers"]["Authorization"] == "Zoho-enczapikey cle_test_zepto"
    r = client.put("/api/plateforme/parametres/email", headers=super_admin, json={**reglage, "cle_api": ""})
    assert r.json()["a_cle"] is True and r.json()["cles"] == {"resend": False, "zeptomail": True, "brevo": True}
    c = client.portal.call(envois.config_email)
    assert c["fournisseur"] == "brevo" and c["cle"] == "cle_test_brevo"

    # Journal : qui, quand, quel fournisseur ; jamais la clé
    j = client.get("/api/plateforme/parametres/email/journal", headers=super_admin).json()
    assert [e["fournisseur"] for e in j[:3]] == ["brevo", "zeptomail", "brevo"]
    assert j[0]["par"] == "super@plateforme-test.bf" and j[0]["date"] and "cle_test" not in str(j)

    # Désactivé : plus rien ne part
    client.put("/api/plateforme/parametres/email", headers=super_admin, json={"fournisseur": "desactive"})
    assert client.portal.call(lambda: envois.envoyer_email("S", "C", "x@exemple.bf"))[0] == "NON_CONFIGURE"


def test_plateforme_champs_obligatoires(client, super_admin, api):
    r = client.put("/api/plateforme/parametres/email", headers=super_admin, json={"fournisseur": "resend", "cle_api": "x"})
    assert r.status_code == 422  # adresse d'expéditeur obligatoire
    r = client.put("/api/plateforme/parametres/email", headers=super_admin,
                   json={"fournisseur": "smtp", "expediteur": "noreply@adlyn.bf"})
    assert r.status_code == 422  # serveur SMTP obligatoire


def test_repli_variables_environnement(client, super_admin, api, monkeypatch):
    s = get_settings()
    # Rien nulle part : non configuré, sans planter
    assert client.portal.call(lambda: envois.envoyer_email("S", "C", "x@exemple.bf"))[0] == "NON_CONFIGURE"
    # Brevo (repli facultatif) avec EMAIL_EXPEDITEUR
    monkeypatch.setattr(s, "brevo_api_key", "cle_test_brevo")
    monkeypatch.setattr(s, "email_expediteur", "noreply@adlyn.bf")
    api["reponse"] = FausseReponse(201, {"messageId": "m-1"})
    assert client.portal.call(lambda: envois.envoyer_email("S", "C", "x@exemple.bf")) == ("ENVOYE", "")
    assert api["liste"][-1]["url"] == envois.BREVO_URL
    # Le SMTP de repli passe avant Brevo
    monkeypatch.setattr(s, "plateforme_smtp_hote", "smtp.exemple.bf")
    assert client.portal.call(envois.config_email)["fournisseur"] == "smtp"
    # Resend passe avant tout (priorité 1)
    monkeypatch.setattr(s, "resend_api_key", "cle_test_resend")
    monkeypatch.setattr(s, "resend_expediteur", "noreply@resend.adlyn.bf")
    c = client.portal.call(envois.config_email)
    assert (c["fournisseur"], c["expediteur"], c["source"]) == ("resend", "noreply@resend.adlyn.bf", "variables d'environnement")
    etat = client.get("/api/plateforme/parametres/email", headers=super_admin)
    assert etat.json()["fournisseur"] == "" and etat.json()["fournisseur_effectif"] == "resend"
    assert "cle_test" not in etat.text
    # Choisi dans l'écran sans clé saisie : la clé de la variable du même fournisseur sert
    client.put("/api/plateforme/parametres/email", headers=super_admin,
               json={"fournisseur": "resend", "expediteur": "noreply@ecran.adlyn.bf"})
    c = client.portal.call(envois.config_email)
    assert (c["source"], c["cle"], c["expediteur"]) == ("administration", "cle_test_resend", "noreply@ecran.adlyn.bf")


def test_ancien_document_smtp(client, super_admin, api, monkeypatch):
    # Ancien réglage (sans « fournisseur ») : il vaut « smtp » et reste utilisé
    client.portal.call(lambda: db.parametres_plateforme.insert_one({
        "_id": "smtp", "hote": "mail.exemple.bf", "port": 465, "ssl": True, "utilisateur": "u@exemple.bf",
        "mot_de_passe_chiffre": envois.chiffrer("mdp_test"), "expediteur": "u@exemple.bf",
        "nom_expediteur": "adLyn", "actif": True}))
    r = client.get("/api/plateforme/parametres/email", headers=super_admin).json()
    assert r["fournisseur"] == "smtp" and r["fournisseur_effectif"] == "smtp"
    assert r["smtp"]["hote"] == "mail.exemple.bf" and r["smtp"]["a_mot_de_passe"] is True
    envoyes = []

    class FauxSmtp:
        def __init__(self, hote, port, timeout=None):
            envoyes.append(("connexion", hote, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, u, m): envoyes.append(("login", u, m))
        def send_message(self, msg): envoyes.append(("envoi", msg["From"], msg["Reply-To"]))

    monkeypatch.setattr(smtplib, "SMTP_SSL", FauxSmtp)
    assert client.portal.call(lambda: envois.envoyer_email("S", "C", "x@exemple.bf")) == ("ENVOYE", "")
    assert ("login", "u@exemple.bf", "mdp_test") in envoyes
    # Transition : avec Resend réglé dans Render, l'ancien SMTP ne prend pas le pas (comme avant)
    monkeypatch.setattr(get_settings(), "resend_api_key", "cle_test_resend")
    monkeypatch.setattr(get_settings(), "resend_expediteur", "noreply@resend.adlyn.bf")
    assert client.portal.call(envois.config_email)["fournisseur"] == "resend"


# ---------------------------------------------------------------------------
# Messagerie des boutiques
# ---------------------------------------------------------------------------
def _plateforme_brevo(client, super_admin):
    r = client.put("/api/plateforme/parametres/email", headers=super_admin, json={
        "fournisseur": "brevo", "expediteur": "noreply@adlyn.bf", "nom_expediteur": "adLyn", "cle_api": "cle_test_plateforme"})
    assert r.status_code == 200, r.text


def test_boutique_service_plateforme(client, super_admin, nouvelle_boutique, api):
    _plateforme_brevo(client, super_admin)
    boutique, h = nouvelle_boutique(nom="Phone Store")
    assert client.get("/api/boutique", headers=h).json()["messagerie"]["fournisseur"] == "plateforme"  # défaut
    f = client.get("/api/boutique/messagerie/fournisseur", headers=h).json()
    assert f["plateforme_pret"] is True and f["plateforme_fournisseur"] == "brevo" and "cle_test" not in str(f)
    client.put("/api/boutique/messagerie", headers=h, json={
        "email_actif": True, "fournisseur": "plateforme", "expediteur_nom": "Phone Store",
        "expediteur_email": "contact@phonestore.bf"})
    api["reponse"] = FausseReponse(201, {"messageId": "m-1"})
    r = client.post("/api/boutique/messagerie/test", headers=h, json={"destinataire": "client@exemple.bf"})
    assert r.json() == {"statut": "ENVOYE", "erreur": ""}
    a = api["liste"][-1]
    # Adresse de la plateforme, nom de la boutique, réponses vers la boutique
    assert a["headers"]["api-key"] == "cle_test_plateforme"
    assert a["json"]["sender"] == {"name": "Phone Store", "email": "noreply@adlyn.bf"}
    assert a["json"]["replyTo"] == {"email": "contact@phonestore.bf"}
    # Erreur du fournisseur : notée au journal des envois, sans bloquer
    api["reponse"] = FausseReponse(400, {"code": "x", "message": "quota atteint"})
    r = client.post("/api/boutique/messagerie/test", headers=h, json={"destinataire": "client@exemple.bf"})
    assert r.json() == {"statut": "ECHEC", "erreur": "Brevo 400 : quota atteint"}


def test_boutique_propre_service(client, super_admin, nouvelle_boutique, api):
    _plateforme_brevo(client, super_admin)
    boutique, h = nouvelle_boutique(nom="Tech Shop")
    r = client.put("/api/boutique/messagerie", headers=h, json={
        "email_actif": True, "fournisseur": "resend", "cle_api": "cle_test_boutique",
        "expediteur_nom": "Tech Shop", "expediteur_email": "ventes@techshop.bf"})
    assert r.status_code == 200, r.text
    assert r.json()["a_cle"] is True and r.json()["fournisseur"] == "resend" and "cle_test" not in r.text
    assert "cle_test" not in client.get("/api/boutique", headers=h).text
    # En base : clé chiffrée
    doc = client.portal.call(lambda: db.boutiques.find_one({"id": boutique["id"]}))
    assert "cle_test_boutique" not in str(doc)
    r = client.post("/api/boutique/messagerie/test", headers=h, json={"destinataire": "client@exemple.bf"})
    assert r.json()["statut"] == "ENVOYE"
    a = api["liste"][-1]
    # SA clé à elle, son adresse, son nom
    assert a["url"] == envois.RESEND_URL and a["headers"]["Authorization"] == "Bearer cle_test_boutique"
    assert a["json"]["from"] == "Tech Shop <ventes@techshop.bf>"
    # Enregistrer sans retaper la clé : conservée ; journal des modifications sans la clé
    client.put("/api/boutique/messagerie", headers=h, json={
        "email_actif": True, "fournisseur": "resend", "expediteur_email": "ventes@techshop.bf"})
    client.post("/api/boutique/messagerie/test", headers=h, json={"destinataire": "client@exemple.bf"})
    assert api["liste"][-1]["headers"]["Authorization"] == "Bearer cle_test_boutique"
    j = client.portal.call(lambda: db.journal_reglages_email.find({"boutique_id": boutique["id"]}).to_list(10))
    assert [e["fournisseur"] for e in j] == ["resend", "resend"] and "cle_test" not in str(j)
    # Clé absente pour ZeptoMail : non envoyé, avec la raison
    client.put("/api/boutique/messagerie", headers=h, json={
        "email_actif": True, "fournisseur": "zeptomail", "expediteur_email": "ventes@techshop.bf"})
    r = client.post("/api/boutique/messagerie/test", headers=h, json={"destinataire": "client@exemple.bf"})
    assert r.json() == {"statut": "NON_ENVOYE", "erreur": "Clé API ZeptoMail manquante"}


def test_ancienne_boutique_smtp(client, nouvelle_boutique, api, monkeypatch):
    # Ancienne boutique : SMTP renseigné, mot de passe en clair, sans « fournisseur » -> « smtp »
    boutique, h = nouvelle_boutique()
    client.portal.call(lambda: db.boutiques.update_one({"id": boutique["id"]}, {"$set": {"messagerie": {
        "email_actif": True, "smtp_hote": "smtp.exemple.bf", "smtp_port": 465, "smtp_ssl": True,
        "smtp_utilisateur": "b@exemple.bf", "smtp_mot_de_passe": "mdp_test", "expediteur_nom": "B",
        "expediteur_email": "b@exemple.bf", "email_equipe": ""}}}))
    m = client.get("/api/boutique", headers=h).json()["messagerie"]
    assert m["fournisseur"] == "smtp" and m["a_mot_de_passe"] is True and "mdp_test" not in str(m)
    envoyes = []

    class FauxSmtp:
        def __init__(self, hote, port, timeout=None):
            envoyes.append(("connexion", hote, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, u, mdp): envoyes.append(("login", u, mdp))
        def send_message(self, msg): envoyes.append(("envoi", msg["From"]))

    monkeypatch.setattr(smtplib, "SMTP_SSL", FauxSmtp)
    assert client.post("/api/boutique/messagerie/test", headers=h, json={"destinataire": "c@exemple.bf"}).json()["statut"] == "ENVOYE"
    assert ("login", "b@exemple.bf", "mdp_test") in envoyes
    # Un enregistrement (ancien écran, sans « fournisseur ») garde « smtp » et chiffre le mot de passe
    client.put("/api/boutique/messagerie", headers=h, json={
        "email_actif": True, "smtp_hote": "smtp.exemple.bf", "smtp_port": 465, "smtp_ssl": True,
        "smtp_utilisateur": "b@exemple.bf", "expediteur_email": "b@exemple.bf"})
    doc = client.portal.call(lambda: db.boutiques.find_one({"id": boutique["id"]}))
    assert doc["messagerie"]["fournisseur"] == "smtp" and "mdp_test" not in str(doc)
    envoyes.clear()
    client.post("/api/boutique/messagerie/test", headers=h, json={"destinataire": "c@exemple.bf"})
    assert ("login", "b@exemple.bf", "mdp_test") in envoyes
