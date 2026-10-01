"""Identifiants de connexion : e-mail OU téléphone, mot de passe oublié (code par
WhatsApp / SMS / e-mail), changement de son e-mail ou de son téléphone, gestion
par le DG et par l'administrateur, journal.

Les envois (WhatsApp, SMS, e-mail) sont remplacés par des DOUBLES qui notent
les messages au lieu de les envoyer : aucun accès réseau pendant les tests."""
import asyncio
import re
import time

import pytest

import envois_plateforme
import identifiants
from utils import telephone_e164

_n = {"i": 0}


def unique() -> int:
    _n["i"] += 1
    return int(f"{_n['i']}{time.time_ns() % 10_000}")


def numero_unique() -> str:
    """Numéro burkinabè local (8 chiffres) jamais utilisé dans la session de tests."""
    return f"7{unique() % 10_000_000:07d}"


def ip() -> dict:
    """Adresse IP différente pour chaque test (les limites d'envoi comptent aussi par IP)."""
    return {"X-Forwarded-For": f"10.{unique() % 250}.{unique() % 250}.{unique() % 250}"}


@pytest.fixture
def boite(monkeypatch):
    """Capture les messages. `boite.statuts[canal]` règle la réponse du faux fournisseur."""
    class Boite(list):
        statuts = {"whatsapp": "ENVOYE", "sms": "ENVOYE", "email": "ENVOYE"}

        def derniers(self, canal=None, a=None):
            return [m for m in self if (canal is None or m["canal"] == canal) and (a is None or m["a"] == a)]

        def code(self, a):
            """Dernier code à 6 chiffres envoyé à ce destinataire."""
            for m in reversed(self):
                trouve = re.search(r"\b(\d{6})\b", m["texte"])
                if m["a"] == a and trouve and m["statut"] == "ENVOYE":
                    return trouve.group(1)
            raise AssertionError(f"Aucun code envoyé à {a}")

    b = Boite()
    b.statuts = dict(Boite.statuts)

    async def faux_whatsapp(telephone, variables, texte, *, modele=None, composants=None):
        statut = b.statuts["whatsapp"]
        b.append({"canal": "whatsapp", "a": telephone, "texte": texte, "modele": modele, "statut": statut})
        return statut, "" if statut == "ENVOYE" else "refusé (test)"

    async def faux_sms(telephone, texte):
        statut = b.statuts["sms"]
        b.append({"canal": "sms", "a": telephone, "texte": texte, "statut": statut})
        return statut, "" if statut == "ENVOYE" else "refusé (test)"

    async def faux_email(sujet, corps, destinataire):
        statut = b.statuts["email"]
        b.append({"canal": "email", "a": destinataire, "texte": corps, "statut": statut})
        return statut, "" if statut == "ENVOYE" else "refusé (test)"

    monkeypatch.setattr(envois_plateforme, "envoyer_whatsapp", faux_whatsapp)
    monkeypatch.setattr(envois_plateforme, "envoyer_sms", faux_sms)
    monkeypatch.setattr(envois_plateforme, "envoyer_email", faux_email)
    return b


def mot_de_passe_dans(texte: str) -> str:
    return re.search(r"mot de passe provisoire(?: :)? (\S+)", texte).group(1)


def creer_membre(client, h, **champs):
    corps = {"nom": f"Membre {unique()}", "role": "commercial", **champs}
    r = client.post("/api/boutique/equipe", headers=h, json=corps)
    assert r.status_code == 201, r.text
    return r.json()


def connexion(client, code, identifiant, mot_de_passe):
    r = client.post("/api/auth/login", json={"code_boutique": code, "identifiant": identifiant, "password": mot_de_passe})
    client.cookies.clear()
    return r


# ---------------------------------------------------------------------------
# Lecture des identifiants
# ---------------------------------------------------------------------------
def test_normalisation_des_identifiants():
    assert telephone_e164("70 12 34 56") == "+22670123456"
    assert telephone_e164("+226 70-12-34-56") == "+22670123456"
    assert telephone_e164("0022670123456") == "+22670123456"
    assert telephone_e164("+33 6 12 34 56 78") == "+33612345678"
    assert telephone_e164("123") is None
    assert identifiants.lire_identifiant(" Jean@Exemple.BF ") == ("email", "jean@exemple.bf")
    assert identifiants.lire_identifiant("70123456") == ("telephone", "+22670123456")
    assert identifiants.lire_identifiant("pas un identifiant") == (None, None)
    assert identifiants.masquer("+22670123456") == "+2267*****56"
    assert identifiants.masquer("jean@exemple.bf") == "j***@exemple.bf"


# ---------------------------------------------------------------------------
# Création d'un membre par le DG, connexion par téléphone
# ---------------------------------------------------------------------------
def test_membre_sans_email_recoit_ses_acces_par_whatsapp_et_se_connecte_par_telephone(client, nouvelle_boutique, boite):
    b, h = nouvelle_boutique()
    tel = numero_unique()
    membre = creer_membre(client, h, telephone=tel)
    assert "email" not in membre and membre["telephone"] == telephone_e164(tel)
    # Envoyé par WhatsApp, sans passer au SMS ; le DG voit le résultat réel
    assert membre["envoi"]["canal"] == "WHATSAPP" and membre["envoi"]["statut"] == "ENVOYE"
    assert "mot_de_passe_provisoire" not in membre["envoi"]  # parti : il n'est pas montré au DG
    message = boite.derniers("whatsapp", telephone_e164(tel))[-1]
    assert b["code_marchand"] in message["texte"] and not boite.derniers("sms")
    mdp = mot_de_passe_dans(message["texte"])
    # Connexion avec le numéro tapé de différentes façons
    for saisie in (tel, f"+226 {tel[:2]} {tel[2:4]} {tel[4:6]} {tel[6:]}", f"00226{tel}"):
        r = connexion(client, b["code_marchand"], saisie, mdp)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["doit_changer_mot_de_passe"] is True
    # Mauvaise boutique : refusé
    autre, _ = nouvelle_boutique()
    assert connexion(client, autre["code_marchand"], tel, mdp).status_code == 401


def test_regles_de_creation_d_un_membre(client, nouvelle_boutique, boite):
    _, h = nouvelle_boutique()
    # Ni e-mail ni téléphone : refusé
    r = client.post("/api/boutique/equipe", headers=h, json={"nom": "Sans contact", "role": "commercial"})
    assert r.status_code == 400
    # Plusieurs comptes SANS e-mail peuvent coexister (index unique partiel)
    creer_membre(client, h, telephone=numero_unique())
    tel = numero_unique()
    creer_membre(client, h, telephone=tel)
    # Mais un téléphone ne sert qu'à un compte, sur toute la plateforme
    _, h2 = nouvelle_boutique()
    r = client.post("/api/boutique/equipe", headers=h2, json={"nom": "Doublon", "telephone": f"+226{tel}"})
    assert r.status_code == 409
    r = client.post("/api/boutique/equipe", headers=h2, json={"nom": "Mauvais", "telephone": "12"})
    assert r.status_code == 400


def test_repli_sms_puis_mot_de_passe_montre_si_rien_ne_part(client, nouvelle_boutique, boite):
    _, h = nouvelle_boutique()
    boite.statuts["whatsapp"] = "ECHEC"
    membre = creer_membre(client, h, telephone=numero_unique())
    assert membre["envoi"]["canal"] == "SMS"
    assert [e["canal"] for e in membre["envoi"]["essais"]] == ["WHATSAPP", "SMS"]
    # Plus rien ne passe : le DG obtient le mot de passe pour le remettre en main propre
    boite.statuts["sms"] = "NON_CONFIGURE"
    membre = creer_membre(client, h, telephone=numero_unique())
    assert membre["envoi"]["statut"] == "ECHEC" and len(membre["envoi"]["mot_de_passe_provisoire"]) >= 8


def test_compte_email_existant_se_connecte_toujours(client, nouvelle_boutique):
    b, h = nouvelle_boutique()
    dg = client.get("/api/auth/me", headers=h).json()["user"]
    # Ancien champ « email » (outils) et nouveau champ « identifiant »
    r = client.post("/api/auth/login", json={"code_boutique": b["code_marchand"], "email": dg["email"],
                                             "password": "motdepasse-123"})
    assert r.status_code == 200
    assert connexion(client, b["code_marchand"], dg["email"].upper(), "motdepasse-123").status_code == 200
    client.cookies.clear()


# ---------------------------------------------------------------------------
# Mot de passe oublié
# ---------------------------------------------------------------------------
def test_mot_de_passe_oublie_par_whatsapp(client, nouvelle_boutique, boite):
    b, h = nouvelle_boutique()
    tel = numero_unique()
    membre = creer_membre(client, h, telephone=tel, email=f"m{unique()}@test.bf")
    h_membre = {"Authorization": f"Bearer {connexion(client, b['code_marchand'], tel, mot_de_passe_dans(boite[-1]['texte'])).json()['access_token']}"}
    adresse = ip()
    r = client.post("/api/auth/mot-de-passe-oublie", headers=adresse,
                    json={"code_boutique": b["code_marchand"].lower(), "identifiant": tel})
    assert r.status_code == 200
    message = r.json()["message"]
    # Le code part par WhatsApp (en priorité), pas par e-mail
    code = boite.code(telephone_e164(tel))
    assert boite[-1]["canal"] == "whatsapp"
    # Même réponse pour un compte qui n'existe pas
    r2 = client.post("/api/auth/mot-de-passe-oublie", headers=ip(),
                     json={"code_boutique": b["code_marchand"], "identifiant": numero_unique()})
    assert r2.status_code == 200 and r2.json()["message"] == message
    # Mauvais code, puis bon code
    faux = "000000" if code != "000000" else "111111"
    corps = {"code_boutique": b["code_marchand"], "identifiant": tel, "nouveau": "tout-nouveau-789"}
    assert client.post("/api/auth/mot-de-passe-oublie/confirmer", headers=ip(), json={**corps, "code": faux}).status_code == 400
    r = client.post("/api/auth/mot-de-passe-oublie/confirmer", headers=ip(), json={**corps, "code": code})
    assert r.status_code == 200, r.text
    # Code à usage unique
    assert client.post("/api/auth/mot-de-passe-oublie/confirmer", headers=ip(), json={**corps, "code": code}).status_code == 400
    # Toutes les sessions ouvertes sont fermées
    assert client.get("/api/auth/me", headers=h_membre).status_code == 401
    # Nouveau mot de passe actif (et définitif : plus de changement obligatoire), ancien refusé
    r = connexion(client, b["code_marchand"], tel, "tout-nouveau-789")
    assert r.status_code == 200 and r.json()["user"]["doit_changer_mot_de_passe"] is False
    assert r.json()["user"]["telephone_verifie"] is True
    # Journal : la demande, l'échec et la réinitialisation... sans aucun code
    journal = client.get("/api/boutique/equipe/journal-identifiants", headers=h).json()
    actions = [l["action"] for l in journal if l["user_id"] == membre["id"]]
    assert {"CODE_DEMANDE", "CODE_ECHEC", "MDP_REINITIALISE"} <= set(actions)
    assert code not in str(journal)


def test_mot_de_passe_oublie_compte_avec_seulement_un_email(client, nouvelle_boutique, boite):
    b, h = nouvelle_boutique()
    email = f"seul{unique()}@test.bf"
    creer_membre(client, h, email=email)
    r = client.post("/api/auth/mot-de-passe-oublie", headers=ip(), json={"code_boutique": b["code_marchand"], "identifiant": email})
    assert r.status_code == 200
    assert boite[-1]["canal"] == "email" and boite[-1]["a"] == email
    code = boite.code(email)
    r = client.post("/api/auth/mot-de-passe-oublie/confirmer", headers=ip(), json={
        "code_boutique": b["code_marchand"], "identifiant": email, "code": code, "nouveau": "par-email-123"})
    assert r.status_code == 200
    assert connexion(client, b["code_marchand"], email, "par-email-123").status_code == 200


def test_cinq_mauvais_codes_bloquent_15_minutes(client, nouvelle_boutique, boite):
    b, h = nouvelle_boutique()
    tel = numero_unique()
    creer_membre(client, h, telephone=tel)
    client.post("/api/auth/mot-de-passe-oublie", headers=ip(), json={"code_boutique": b["code_marchand"], "identifiant": tel})
    code = boite.code(telephone_e164(tel))
    faux = "000000" if code != "000000" else "111111"
    corps = {"code_boutique": b["code_marchand"], "identifiant": tel, "nouveau": "jamais-utilise-1"}
    statuts = [client.post("/api/auth/mot-de-passe-oublie/confirmer", headers=ip(), json={**corps, "code": faux}).status_code
               for _ in range(5)]
    assert statuts == [400, 400, 400, 400, 429]
    # Même le bon code est refusé pendant le blocage
    assert client.post("/api/auth/mot-de-passe-oublie/confirmer", headers=ip(), json={**corps, "code": code}).status_code == 429
    # Compte inconnu : même comportement (on ne révèle rien)
    corps_inconnu = {**corps, "identifiant": numero_unique()}
    statuts = [client.post("/api/auth/mot-de-passe-oublie/confirmer", headers=ip(), json={**corps_inconnu, "code": faux}).status_code
               for _ in range(5)]
    assert statuts == [400, 400, 400, 400, 429]


def test_limites_d_envoi(client, nouvelle_boutique, boite, monkeypatch):
    b, h = nouvelle_boutique()
    tel, email = numero_unique(), f"limite{unique()}@test.bf"
    creer_membre(client, h, telephone=tel, email=email)
    corps = {"code_boutique": b["code_marchand"], "identifiant": tel}
    adresse = ip()
    assert client.post("/api/auth/mot-de-passe-oublie", headers=adresse, json=corps).status_code == 200
    # 1 par minute (le même numéro, même tapé autrement et depuis une autre adresse IP)
    assert client.post("/api/auth/mot-de-passe-oublie", headers=adresse, json=corps).status_code == 429
    assert client.post("/api/auth/mot-de-passe-oublie", headers=ip(), json={**corps, "identifiant": f"+226{tel}"}).status_code == 429
    # Le même COMPTE désigné par son e-mail : réponse identique, mais aucun nouvel envoi
    nb_avant = len(boite)
    r = client.post("/api/auth/mot-de-passe-oublie", headers=ip(), json={**corps, "identifiant": email})
    assert r.status_code == 200 and len(boite) == nb_avant  # réponse identique, mais aucun nouvel envoi
    # 5 par heure
    from datetime import timedelta
    monkeypatch.setattr(identifiants, "DELAI_ENTRE_ENVOIS", timedelta(0))
    tel2 = numero_unique()
    creer_membre(client, h, telephone=tel2)
    corps2 = {"code_boutique": b["code_marchand"], "identifiant": tel2}
    statuts = [client.post("/api/auth/mot-de-passe-oublie", headers=ip(), json=corps2).status_code for _ in range(6)]
    assert statuts == [200, 200, 200, 200, 200, 429]


# ---------------------------------------------------------------------------
# Mon compte : changer son e-mail / son téléphone
# ---------------------------------------------------------------------------
def test_changer_son_telephone_puis_retirer_son_email(client, nouvelle_boutique, boite):
    b, h = nouvelle_boutique()
    moi = client.get("/api/auth/me", headers=h).json()["user"]
    tel = numero_unique()
    # Mauvais mot de passe : refusé
    r = client.post("/api/auth/identifiant/demande", headers={**h, **ip()},
                    json={"type": "telephone", "valeur": tel, "mot_de_passe": "faux"})
    assert r.status_code == 400
    r = client.post("/api/auth/identifiant/demande", headers={**h, **ip()},
                    json={"type": "telephone", "valeur": tel, "mot_de_passe": "motdepasse-123"})
    assert r.status_code == 200, r.text
    assert r.json()["canal"] == "WHATSAPP" and tel not in r.json()["message"]  # numéro masqué
    # Le code est parti vers le NOUVEAU numéro
    code = boite.code(telephone_e164(tel))
    assert code not in r.text
    r = client.post("/api/auth/identifiant/confirmer", headers=h, json={"type": "telephone", "code": code})
    assert r.status_code == 200, r.text
    assert r.json()["telephone"] == telephone_e164(tel) and r.json()["telephone_verifie"] is True
    assert connexion(client, b["code_marchand"], tel, "motdepasse-123").status_code == 200
    # Retirer le téléphone : impossible, l'e-mail (ancien compte) n'est pas vérifié
    r = client.post("/api/auth/identifiant/retirer", headers=h, json={"type": "telephone", "mot_de_passe": "motdepasse-123"})
    assert r.status_code == 400
    # Retirer l'e-mail : possible (téléphone vérifié) ; la personne en est prévenue
    r = client.post("/api/auth/identifiant/retirer", headers=h, json={"type": "email", "mot_de_passe": "motdepasse-123"})
    assert r.status_code == 200 and "email" not in r.json()
    assert boite.derniers("email", moi["email"])
    assert connexion(client, b["code_marchand"], moi["email"], "motdepasse-123").status_code == 401
    # Plus que le téléphone : il ne peut plus être retiré
    r = client.post("/api/auth/identifiant/retirer", headers=h, json={"type": "telephone", "mot_de_passe": "motdepasse-123"})
    assert r.status_code == 400


def test_changer_son_email_avec_code_envoye_a_la_nouvelle_adresse(client, nouvelle_boutique, boite):
    b, h = nouvelle_boutique()
    ancien = client.get("/api/auth/me", headers=h).json()["user"]["email"]
    nouvelle = f"nouvelle{unique()}@test.bf"
    r = client.post("/api/auth/identifiant/demande", headers={**h, **ip()},
                    json={"type": "email", "valeur": nouvelle, "mot_de_passe": "motdepasse-123"})
    assert r.status_code == 200 and r.json()["canal"] == "EMAIL"
    code = boite.code(nouvelle)
    r = client.post("/api/auth/identifiant/confirmer", headers=h, json={"type": "email", "code": code})
    assert r.status_code == 200 and r.json()["email"] == nouvelle and r.json()["email_verifie"] is True
    # Ancienne ET nouvelle adresses prévenues
    assert any("modifie" in m["texte"] for m in boite.derniers("email", ancien))
    assert connexion(client, b["code_marchand"], nouvelle, "motdepasse-123").status_code == 200
    assert connexion(client, b["code_marchand"], ancien, "motdepasse-123").status_code == 401


def test_changement_impossible_si_le_code_ne_part_pas(client, nouvelle_boutique, boite):
    _, h = nouvelle_boutique()
    boite.statuts.update({"whatsapp": "NON_CONFIGURE", "sms": "NON_CONFIGURE"})
    r = client.post("/api/auth/identifiant/demande", headers={**h, **ip()},
                    json={"type": "telephone", "valeur": numero_unique(), "mot_de_passe": "motdepasse-123"})
    assert r.status_code == 503 and "WhatsApp" in r.json()["detail"]


def test_super_admin_inchange(client, super_admin, boite):
    r = client.post("/api/auth/identifiant/demande", headers={**super_admin, **ip()},
                    json={"type": "telephone", "valeur": numero_unique(), "mot_de_passe": "super-motdepasse"})
    assert r.status_code == 403
    # Le mot de passe oublié ne concerne pas le super-administrateur
    r = client.post("/api/auth/mot-de-passe-oublie", headers=ip(),
                    json={"code_boutique": "", "identifiant": "super@plateforme-test.bf"})
    assert r.status_code == 200 and not boite
    assert client.post("/api/auth/login", json={"identifiant": "super@plateforme-test.bf",
                                                "password": "super-motdepasse"}).status_code == 200
    client.cookies.clear()


# ---------------------------------------------------------------------------
# Gestion par le DG et par l'administrateur
# ---------------------------------------------------------------------------
def test_dg_modifie_les_identifiants_d_un_membre(client, nouvelle_boutique, boite):
    b, h = nouvelle_boutique()
    ancien_tel = numero_unique()
    membre = creer_membre(client, h, telephone=ancien_tel)
    nouveau_tel, email = numero_unique(), f"ajout{unique()}@test.bf"
    r = client.patch(f"/api/boutique/equipe/{membre['id']}", headers=h, json={"telephone": nouveau_tel, "email": email})
    assert r.status_code == 200, r.text
    assert r.json()["telephone"] == telephone_e164(nouveau_tel) and r.json()["email"] == email
    # Prévenu sur l'ancien et le nouveau numéro (et sur la nouvelle adresse)
    destinataires = {n["destination"] for n in r.json()["notifications"]}
    assert identifiants.masquer(telephone_e164(ancien_tel)) in destinataires
    assert identifiants.masquer(telephone_e164(nouveau_tel)) in destinataires
    assert boite.derniers(a=telephone_e164(ancien_tel))[-1]["texte"].count("modifie") == 1
    # Retirer les deux : refusé ; retirer le téléphone seul : accepté
    r = client.patch(f"/api/boutique/equipe/{membre['id']}", headers=h, json={"telephone": "", "email": ""})
    assert r.status_code == 400
    r = client.patch(f"/api/boutique/equipe/{membre['id']}", headers=h, json={"telephone": ""})
    assert r.status_code == 200 and "telephone" not in r.json()
    # Le DG ne change pas ses propres identifiants ici (il passe par Mon compte, avec code)
    moi = client.get("/api/auth/me", headers=h).json()["user"]
    r = client.patch(f"/api/boutique/equipe/{moi['id']}", headers=h, json={"telephone": numero_unique()})
    assert r.status_code == 400
    # Un membre d'une AUTRE boutique : introuvable
    _, h2 = nouvelle_boutique()
    assert client.patch(f"/api/boutique/equipe/{membre['id']}", headers=h2, json={"email": "x@y.bf"}).status_code == 404
    journal = client.get("/api/boutique/equipe/journal-identifiants", headers=h).json()
    assert any(l["action"] == "IDENTIFIANT_MODIFIE" and l["par_id"] == moi["id"] for l in journal)


def test_dg_envoie_un_nouveau_mot_de_passe_provisoire(client, nouvelle_boutique, boite, connecter_membre):
    b, h = nouvelle_boutique()
    tel = numero_unique()
    membre = creer_membre(client, h, telephone=tel)
    h_membre, _ = connecter_membre(b["code_marchand"], tel, mot_de_passe_dans(boite[-1]["texte"]))
    r = client.post(f"/api/boutique/equipe/{membre['id']}/nouveau-mot-de-passe", headers=h)
    assert r.status_code == 200 and r.json()["envoi"]["canal"] == "WHATSAPP"
    assert "mot_de_passe_provisoire" not in r.json()["envoi"]
    nouveau = mot_de_passe_dans(boite[-1]["texte"])
    assert client.get("/api/auth/me", headers=h_membre).status_code == 401  # sessions fermées
    assert connexion(client, b["code_marchand"], tel, nouveau).status_code == 200


def test_administrateur_modifie_et_renvoie_les_identifiants_du_dg(client, super_admin, nouvelle_boutique, boite):
    b, h = nouvelle_boutique()
    tel = numero_unique()
    r = client.patch(f"/api/plateforme/boutiques/{b['id']}/dg-identifiants", headers=super_admin, json={"telephone": tel})
    assert r.status_code == 200, r.text
    assert r.json()["dg"]["telephone"] == telephone_e164(tel)
    liste = client.get("/api/plateforme/boutiques", headers=super_admin).json()
    assert next(x for x in liste if x["id"] == b["id"])["dg_compte"]["telephone"] == telephone_e164(tel)
    # Renvoyer les identifiants : WhatsApp d'abord (le SMS n'est pas utilisé), e-mail aussi
    nb = len(boite)
    envoi = client.post(f"/api/plateforme/boutiques/{b['id']}/renvoyer-identifiants", headers=super_admin).json()
    assert envoi["whatsapp"] == "ENVOYE" and envoi["sms"] == "NON_ENVOYE" and envoi["email"] == "ENVOYE"
    nouveaux = boite[nb:]
    assert [m["canal"] for m in nouveaux] == ["whatsapp", "email"] and nouveaux[0]["a"] == telephone_e164(tel)
    mdp = mot_de_passe_dans(nouveaux[0]["texte"])
    assert connexion(client, b["code_marchand"], tel, mdp).status_code == 200
    journal = client.get("/api/plateforme/journal-identifiants", headers=super_admin,
                         params={"boutique_id": b["id"]}).json()
    assert {"IDENTIFIANT_MODIFIE", "MDP_PROVISOIRE_ENVOYE"} <= {l["action"] for l in journal}
    assert mdp not in str(journal)


# ---------------------------------------------------------------------------
# Format du message WhatsApp (modèle « Authentication » de Meta)
# ---------------------------------------------------------------------------
def test_modele_whatsapp_authentication(monkeypatch):
    from config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_access_token", "jeton-test")
    monkeypatch.setattr(s, "whatsapp_phone_number_id", "123456")
    monkeypatch.setattr(s, "whatsapp_code_template", "adlyn_code_connexion")
    monkeypatch.setattr(s, "whatsapp_identifiants_template", "adlyn_identifiants")
    appels = []

    class Reponse:
        status_code = 200
        text = "{}"

    async def faux_post(self, url, json=None, headers=None, **kw):
        appels.append(json)
        return Reponse()

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)
    resultat = asyncio.run(identifiants.envoyer_message(
        telephone="70 12 34 56", sujet="x", texte="code 123456", code="123456", infos_whatsapp=["A", "B", "C", "D"]))
    assert resultat["canal"] == "WHATSAPP"
    infos, code = appels
    assert infos["template"]["name"] == "adlyn_identifiants"
    assert code["to"] == "22670123456" and code["template"]["name"] == "adlyn_code_connexion"
    corps, bouton = code["template"]["components"]
    assert corps["parameters"][0]["text"] == "123456"
    assert bouton["type"] == "button" and bouton["sub_type"] == "url" and bouton["parameters"][0]["text"] == "123456"


def test_ancien_index_email_remplace_au_demarrage(client):
    """Base de production : l'ancien index (e-mail obligatoire et unique) est
    remplacé par l'index partiel (e-mail facultatif mais unique)."""
    from db import db, ensure_indexes

    async def scenario():
        await db.users.drop_index("email_connexion")
        await db.users.create_index("email", unique=True)  # index de l'ancienne version
        await ensure_indexes()
        return await db.users.index_information()

    infos = client.portal.call(scenario)
    assert "email_1" not in infos
    assert infos["email_connexion"]["unique"] and infos["email_connexion"]["partialFilterExpression"]
    assert infos["telephone_connexion"]["unique"]
