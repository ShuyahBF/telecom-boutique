"""Lot C — lecture de la pièce d'identité par l'IA (« Liluvine ») et validation
automatique de la boutique quand le nom concorde avec le propriétaire déclaré.

Le client Anthropic est remplacé par un DOUBLE (aucun appel réseau, aucun coût) :
`ia.lecture` règle la réponse JSON renvoyée, `ia.erreur` simule une panne. Les envois
(WhatsApp, e-mail) sont capturés dans `boite`."""
import io
import json
from types import SimpleNamespace

import pytest

import envois_plateforme
import kyc_ia
from config import get_settings
from db import db

JPEG = b"\xff\xd8\xff\xe0" + b"photo-de-test" * 20  # signature JPEG valable
PDF = b"%PDF-1.4 carte"

LECTURE_BONNE = {
    "type_document": "CNIB", "nom": "OUEDRAOGO", "prenoms": "Awa Mariam", "date_naissance": "1990-04-12",
    "numero_piece": "B12345789", "date_expiration": "2034-01-01", "pays": "Burkina Faso",
    "lisible": True, "ressemble_piece_identite": True, "expiree": False, "confiance": 0.95, "remarques": "",
}


# ---------------------------------------------------------------------------
# Doubles : client Anthropic, envois, réglages remis à zéro
# ---------------------------------------------------------------------------
@pytest.fixture
def ia(monkeypatch):
    """Faux client anthropic.AsyncAnthropic : renvoie `etat.lecture` (JSON) ou lève `etat.erreur`."""
    import anthropic

    etat = SimpleNamespace(lecture=dict(LECTURE_BONNE), erreur=None, appels=[])

    class FauxMessages:
        async def create(self, **kwargs):
            etat.appels.append(kwargs)
            if etat.erreur:
                raise etat.erreur
            return SimpleNamespace(stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text=json.dumps(etat.lecture))])

    class FauxClient:
        def __init__(self, **kwargs):
            self.beta = SimpleNamespace(messages=FauxMessages())

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FauxClient)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "cle-de-test")
    return etat


@pytest.fixture
def boite(monkeypatch):
    messages = []

    async def faux_whatsapp(telephone, variables, texte, **_):
        messages.append({"canal": "whatsapp", "a": telephone, "texte": texte})
        return "ENVOYE", ""

    async def faux_email(sujet, corps, destinataire):
        messages.append({"canal": "email", "a": destinataire, "sujet": sujet, "texte": corps})
        return "ENVOYE", ""

    monkeypatch.setattr(envois_plateforme, "envoyer_whatsapp", faux_whatsapp)
    monkeypatch.setattr(envois_plateforme, "envoyer_email", faux_email)
    monkeypatch.setattr(get_settings(), "rapport_email", "equipe@adlyn-test.bf")
    return messages


@pytest.fixture(autouse=True)
def reglages_par_defaut(client):
    """Chaque test part des réglages par défaut (auto activée, seuil 0,8, 5 par jour)."""
    client.portal.call(lambda: db.parametres_plateforme.delete_one({"_id": kyc_ia.REGLAGE_ID}))
    yield
    client.portal.call(lambda: db.parametres_plateforme.delete_one({"_id": kyc_ia.REGLAGE_ID}))


_numero = {"n": 4_300_000}


@pytest.fixture
def inscrite(client, nouvelle_boutique):
    """Boutique « inscrite en ligne » : en attente de validation, DG Awa OUÉDRAOGO."""
    def _creer(prenom="Awa", nom_famille="Ouédraogo", validee=False):
        b, h = nouvelle_boutique(dg_nom=f"{prenom} {nom_famille}")
        _numero["n"] += 1
        tel = f"+2267{_numero['n']:07d}"  # numéro unique (index d'unicité des comptes)
        client.portal.call(lambda: db.boutiques.update_one({"id": b["id"]}, {"$set": {
            "validee": validee, "origine": "inscription", "dg_telephone": tel,
            "inscription": {"dg_prenom": prenom, "dg_nom_famille": nom_famille}}}))
        client.portal.call(lambda: db.users.update_one({"boutique_id": b["id"], "role": "dg"}, {"$set": {
            "prenom": prenom, "nom_famille": nom_famille, "telephone": tel}}))
        return b, h
    return _creer


def envoyer(client, h, recto=JPEG, verso=None, type_document="CNIB", mime="image/jpeg"):
    fichiers = {"recto": ("recto.jpg", io.BytesIO(recto), mime)}
    if verso is not None:
        fichiers["verso"] = ("verso.jpg", io.BytesIO(verso), "image/jpeg")
    return client.post("/api/boutique/kyc/piece-identite", headers=h, files=fichiers,
                       data={"type_document": type_document})


def fiche(client, boutique_id):
    return client.portal.call(lambda: db.boutiques.find_one({"id": boutique_id}, {"_id": 0}))


# ---------------------------------------------------------------------------
# Règle de concordance (fonctions pures)
# ---------------------------------------------------------------------------
def test_regle_de_concordance():
    declare = {"source": "compte_dg", "prenoms": ["awa"], "nom_famille": ["ouedraogo"], "libelle": "Awa Ouédraogo"}
    # Ordre inversé, majuscules, sans accents : concordant
    assert kyc_ia.comparer_noms(declare, "OUEDRAOGO", "AWA")["concorde"]
    # Prénom et nom intervertis par l'IA : l'ordre ne compte pas
    assert kyc_ia.comparer_noms(declare, "Awa", "Ouédraogo")["concorde"]
    # Faute légère (une lettre) tolérée
    assert kyc_ia.comparer_noms(declare, "OUEDRAOGQ", "Awa")["concorde"]
    # Nom de famille différent : refusé ; prénom différent : refusé
    assert not kyc_ia.comparer_noms(declare, "KABORE", "Awa")["concorde"]
    assert not kyc_ia.comparer_noms(declare, "OUEDRAOGO", "Fatimata")["concorde"]
    # Tirets et apostrophes neutralisés, nom composé : tous ses mots doivent concorder
    compose = {"prenoms": ["jean", "baptiste"], "nom_famille": ["kabore", "zongo"], "libelle": "Jean-Baptiste Kaboré-Zongo"}
    assert kyc_ia.comparer_noms(compose, "KABORE ZONGO", "Jean Baptiste")["concorde"]
    assert not kyc_ia.comparer_noms(compose, "KABORE", "Jean Baptiste")["concorde"]
    assert kyc_ia.mots("N'Guessan-Koné") == ["n", "guessan", "kone"]
    # Masquage du numéro
    assert kyc_ia.masquer_numero("B12345789") == "B12•••789"
    assert kyc_ia.masquer_numero("") == ""


# ---------------------------------------------------------------------------
# Parcours du commerçant
# ---------------------------------------------------------------------------
def test_nom_concordant_ordre_inverse_et_accents_valide_la_boutique(client, inscrite, ia, boite):
    b, h = inscrite(prenom="Awa", nom_famille="Ouédraogo")
    r = envoyer(client, h, verso=JPEG)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["decision"] == "VERIFIE" and d["validee_maintenant"] and d["boutique_validee"]
    assert d["kyc"]["statut"] == "VERIFIE" and d["kyc"]["verifie_par"] == "IA (Liluvine)"
    # Recto + verso envoyés à l'IA (deux images en base64) et rangés dans le dossier
    contenu = ia.appels[0]["messages"][0]["content"]
    assert [c["type"] for c in contenu].count("image") == 2
    assert ia.appels[0]["output_config"]["format"]["type"] == "json_schema"
    assert [p["face"] for p in d["kyc"]["documents"]] == ["RECTO", "VERSO"]
    # Boutique validée par l'IA, traçabilité complète
    f = fiche(client, b["id"])
    assert f["validee"] is True and f["validee_par"] == "IA (Liluvine)"
    trace = f["kyc"]["ia"]
    assert trace["par"] == "IA (Liluvine)" and trace["motif_code"] == "CONCORDANT"
    assert trace["comparaison"]["nom_famille_ok"] and trace["comparaison"]["prenom_ok"]
    assert trace["lecture"]["confiance"] == 0.95 and trace["modele"]
    # Message WhatsApp de bienvenue au DG
    assert any(m["canal"] == "whatsapp" and "est validée" in m["texte"] for m in boite)


def test_nom_different_reste_en_attente(client, inscrite, ia, boite):
    b, h = inscrite()
    ia.lecture = {**LECTURE_BONNE, "nom": "KABORE", "prenoms": "Moussa"}
    d = envoyer(client, h).json()
    assert d["decision"] == "EN_ATTENTE" and d["motif_code"] == "NOM_DIFFERENT"
    assert "KABORE" in d["motif"] and "ne correspond pas" in d["motif"]
    assert d["kyc"]["statut"] == "EN_ATTENTE" and not d["boutique_validee"]
    assert fiche(client, b["id"])["validee"] is False
    # Le super-admin est prévenu par e-mail
    assert any(m["canal"] == "email" and m["a"] == "equipe@adlyn-test.bf" for m in boite)


@pytest.mark.parametrize("lecture, code", [
    ({"expiree": True, "date_expiration": "2020-01-01"}, "EXPIREE"),
    ({"expiree": False, "date_expiration": "2021-06-30"}, "EXPIREE"),  # date passée, même si l'IA se trompe
    ({"lisible": False, "confiance": 0.2}, "ILLISIBLE"),
    ({"ressemble_piece_identite": False}, "PAS_PIECE"),
    ({"confiance": 0.6}, "CONFIANCE_FAIBLE"),
])
def test_piece_refusee_par_les_controles(client, inscrite, ia, boite, lecture, code):
    b, h = inscrite()
    ia.lecture = {**LECTURE_BONNE, **lecture}
    d = envoyer(client, h).json()
    assert d["motif_code"] == code and d["kyc"]["statut"] == "EN_ATTENTE"
    assert fiche(client, b["id"])["validee"] is False


def test_sans_cle_api_verification_manuelle(client, inscrite, boite, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    b, h = inscrite()
    r = envoyer(client, h)
    assert r.status_code == 200
    d = r.json()
    assert d["motif_code"] == "IA_INDISPONIBLE" and "vérification manuelle" in d["motif"]
    assert d["kyc"]["statut"] == "EN_ATTENTE" and len(d["kyc"]["documents"]) == 1  # pièce enregistrée


def test_erreur_de_l_ia_jamais_500(client, inscrite, ia, boite):
    b, h = inscrite()
    ia.erreur = RuntimeError("panne réseau")
    r = envoyer(client, h)
    assert r.status_code == 200
    assert r.json()["motif_code"] == "IA_INDISPONIBLE"
    # Réponse non JSON : même traitement
    ia.erreur, ia.lecture = None, "pas du json"
    assert envoyer(client, h).json()["motif_code"] == "IA_INDISPONIBLE"


def test_boutique_deja_validee_jamais_devalidee(client, inscrite, ia, boite):
    b, h = inscrite(validee=True)
    client.portal.call(lambda: db.boutiques.update_one({"id": b["id"]}, {"$set": {"validee_par": "admin@adlyn.bf"}}))
    ia.lecture = {**LECTURE_BONNE, "nom": "TRAORE"}
    d = envoyer(client, h).json()
    assert d["decision"] == "EN_ATTENTE" and d["boutique_validee"]
    f = fiche(client, b["id"])
    assert f["validee"] is True and f["validee_par"] == "admin@adlyn.bf"
    # Concordant ensuite : KYC vérifié, validation d'origine conservée, pas de 2e message de bienvenue
    ia.lecture = dict(LECTURE_BONNE)
    d = envoyer(client, h).json()
    assert d["decision"] == "VERIFIE" and not d["validee_maintenant"]
    assert fiche(client, b["id"])["validee_par"] == "admin@adlyn.bf"
    assert not any("est validée" in m["texte"] for m in boite)


def test_validation_automatique_desactivee(client, inscrite, ia, boite, super_admin):
    r = client.put("/api/plateforme/parametres/kyc-ia", headers=super_admin,
                   json={"auto_validation": False, "seuil_confiance": 0.9, "max_par_jour": 5})
    assert r.status_code == 200 and r.json()["auto_validation"] is False and r.json()["ia_configuree"]
    b, h = inscrite()
    d = envoyer(client, h).json()
    assert d["motif_code"] == "AUTO_DESACTIVEE" and fiche(client, b["id"])["validee"] is False
    # Réglages réservés au super-admin, bornés
    assert client.get("/api/plateforme/parametres/kyc-ia", headers=h).status_code == 403
    assert client.put("/api/plateforme/parametres/kyc-ia", headers=super_admin,
                      json={"auto_validation": True, "seuil_confiance": 2, "max_par_jour": 5}).status_code == 422


def test_limite_par_jour(client, inscrite, ia, boite, super_admin):
    client.put("/api/plateforme/parametres/kyc-ia", headers=super_admin,
               json={"auto_validation": True, "seuil_confiance": 0.8, "max_par_jour": 2})
    b, h = inscrite()
    ia.lecture = {**LECTURE_BONNE, "lisible": False}
    assert envoyer(client, h).json()["motif_code"] == "ILLISIBLE"
    assert envoyer(client, h).json()["motif_code"] == "ILLISIBLE"
    d = envoyer(client, h).json()
    assert d["motif_code"] == "LIMITE" and len(ia.appels) == 2  # 3e envoi : pas d'appel à l'IA
    assert len(d["kyc"]["documents"]) == 3  # la pièce est quand même enregistrée


def test_fichiers_controles(client, inscrite, ia, boite):
    b, h = inscrite()
    assert envoyer(client, h, recto=b"pas une image", mime="image/jpeg").status_code == 400
    assert envoyer(client, h, mime="text/plain").status_code == 400
    assert envoyer(client, h, recto=b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024)).status_code == 400
    assert envoyer(client, h, type_document="INCONNU").status_code == 400
    assert not ia.appels
    # PDF accepté : envoyé comme bloc « document »
    assert envoyer(client, h, recto=PDF, mime="application/pdf").status_code == 200
    assert ia.appels[0]["messages"][0]["content"][1]["type"] == "document"


def test_numero_de_piece_toujours_masque(client, inscrite, ia, boite, super_admin):
    b, h = inscrite()
    ia.lecture = {**LECTURE_BONNE, "nom": "ZONGO"}  # en attente : tout le dossier reste consultable
    reponses = [envoyer(client, h).text, client.get("/api/boutique", headers=h).text,
                client.get("/api/plateforme/boutiques", headers=super_admin).text,
                client.get(f"/api/plateforme/boutiques/{b['id']}/kyc/ia-journal", headers=super_admin).text,
                client.post(f"/api/plateforme/boutiques/{b['id']}/kyc/relancer-ia", headers=super_admin).text]
    for texte in reponses:
        assert "B12345789" not in texte
    assert "B12•••789" in reponses[0]
    # Ni la base ne garde le numéro complet, ni la clé de stockage ne sort
    assert "B12345789" not in json.dumps(fiche(client, b["id"]), default=str)
    assert '"cle"' not in reponses[1]


# ---------------------------------------------------------------------------
# Super-administrateur
# ---------------------------------------------------------------------------
def test_refus_par_le_super_admin(client, inscrite, ia, boite, super_admin):
    b, h = inscrite()
    ia.lecture = {**LECTURE_BONNE, "nom": "SAWADOGO"}
    envoyer(client, h)
    url = f"/api/plateforme/boutiques/{b['id']}/kyc/refuser"
    assert client.post(url, headers=h, json={"motif": "x"}).status_code == 403
    assert client.post(url, headers=super_admin, json={"motif": ""}).status_code == 422
    r = client.post(url, headers=super_admin, json={"motif": "La pièce n'est pas au nom du propriétaire"})
    assert r.status_code == 200 and r.json()["statut"] == "REJETE"
    assert r.json()["motif_rejet"] == "La pièce n'est pas au nom du propriétaire"
    # Message WhatsApp au commerçant, journal du refus
    assert any(m["canal"] == "whatsapp" and "pas au nom du propriétaire" in m["texte"] for m in boite)
    journal = client.get(f"/api/plateforme/boutiques/{b['id']}/kyc/ia-journal", headers=super_admin).json()
    assert journal[0]["type"] == "REFUS_ADMIN"
    # L'ancienne route de décision (REJETE) passe par le même traitement
    d = client.post(f"/api/plateforme/boutiques/{b['id']}/kyc/decision", headers=super_admin,
                    json={"statut": "REJETE", "motif_rejet": "Photo coupée"})
    assert d.status_code == 200 and d.json()["motif_rejet"] == "Photo coupée"


def test_relance_par_le_super_admin(client, inscrite, ia, boite, super_admin):
    b, h = inscrite()
    url = f"/api/plateforme/boutiques/{b['id']}/kyc/relancer-ia"
    assert client.post(url, headers=super_admin).status_code == 400  # aucune pièce
    ia.erreur = RuntimeError("panne")
    envoyer(client, h, verso=JPEG)
    assert fiche(client, b["id"])["kyc"]["ia"]["motif_code"] == "IA_INDISPONIBLE"
    assert client.post(url, headers=h).status_code == 403
    ia.erreur = None
    r = client.post(url, headers=super_admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["decision"] == "VERIFIE" and d["boutique"]["validee"] is True
    # Les deux faces du dernier envoi sont relues depuis le stockage privé
    assert [c["type"] for c in ia.appels[-1]["messages"][0]["content"]].count("image") == 2
    assert fiche(client, b["id"])["kyc"]["ia"]["relance"] is True


def test_validation_manuelle_toujours_fonctionnelle(client, inscrite, super_admin):
    b, h = inscrite()
    r = client.post(f"/api/plateforme/boutiques/{b['id']}/valider", headers=super_admin)
    assert r.status_code == 200 and r.json()["validee"] is True
    assert r.json()["validee_par"] == "super@plateforme-test.bf"
    assert client.post("/api/plateforme/boutiques/inconnue/valider", headers=super_admin).status_code == 404
    assert client.post(f"/api/plateforme/boutiques/{b['id']}/valider", headers=h).status_code == 403
