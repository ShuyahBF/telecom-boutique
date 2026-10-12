"""Lot D — photo récente du DG (selfie, pièce tenue à côté du visage) comparée par l'IA à
la pièce d'identité, et revue HUMAINE dès que l'IA doute.

Mêmes doubles que le lot C (tests/test_kyc_ia.py) : client Anthropic simulé (`ia.lecture`
règle la réponse JSON, `ia.erreur` simule une panne), envois WhatsApp / e-mail capturés
dans `boite`, réglages remis à zéro avant chaque test."""
import json

import pytest

import kyc_ia
from config import get_settings
from db import db
# Doubles et outils partagés avec les tests du lot C (aucun test n'est importé ici)
from tests.test_kyc_ia import (JPEG, LECTURE_BONNE, PDF, VISAGE_BON, boite, envoyer, fiche, ia,  # noqa: F401
                               inscrite, reglages_par_defaut)


def lecture_avec(**visage) -> dict:
    """Lecture « tout concordant » dont l'avis sur le selfie est modifié."""
    return {**LECTURE_BONNE, "visage": {**VISAGE_BON, **visage}}


def dossier_admin(client, super_admin, boutique_id) -> dict:
    """La boutique telle que la voit le super-administrateur (liste de la plateforme)."""
    return next(b for b in client.get("/api/plateforme/boutiques", headers=super_admin).json() if b["id"] == boutique_id)


def emails(boite):
    return [m for m in boite if m["canal"] == "email"]


# ---------------------------------------------------------------------------
# Décision de l'IA
# ---------------------------------------------------------------------------
def test_tout_concordant_valide_la_boutique(client, inscrite, ia, boite):
    b, h = inscrite()
    r = envoyer(client, h, verso=JPEG)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["decision"] == "VERIFIE" and d["validee_maintenant"] and not d["revue_humaine"]
    assert d["message"].startswith("Votre boutique est validée")
    assert d["kyc"]["revue_humaine_requise"] is False
    # Le selfie est rangé dans le dossier (type SELFIE_DG) avec le même envoi_id que la pièce
    docs = d["kyc"]["documents"]
    selfie = next(p for p in docs if p["type"] == "SELFIE_DG")
    assert selfie["face"] == "SELFIE" and {p["envoi_id"] for p in docs} == {selfie["envoi_id"]}
    # Un seul appel à l'IA : schéma avec l'avis « visage », consignes d'aide à un humain
    appel = ia.appels[0]
    assert "visage" in appel["output_config"]["format"]["schema"]["required"]
    assert "ne dois PAS chercher à reconnaître" in appel["system"]
    textes = [c["text"] for c in appel["messages"][0]["content"] if c["type"] == "text"]
    assert any(t.startswith("Selfie") for t in textes)
    f = fiche(client, b["id"])
    assert f["validee"] is True and f["kyc"]["ia"]["visage"]["meme_personne"] == "oui"
    assert not emails(boite)  # aucun humain dérangé quand tout est sûr


@pytest.mark.parametrize("visage, code", [
    ({"meme_personne": "incertain", "confiance_visage": 0.5}, "VISAGE_INCERTAIN"),
    ({"meme_personne": "oui", "confiance_visage": 0.7}, "VISAGE_INCERTAIN"),  # sous le seuil visage 0,85
])
def test_visage_incertain_revue_humaine_et_email(client, inscrite, ia, boite, super_admin, visage, code):
    b, h = inscrite()
    ia.lecture = lecture_avec(**visage)
    d = envoyer(client, h).json()
    assert d["decision"] == "EN_ATTENTE" and d["motif_code"] == code and d["revue_humaine"]
    # Commerçant : message neutre, ni score ni analyse des visages
    assert d["message"] == kyc_ia.MESSAGE_REVUE
    assert "visage" not in d["kyc"]["ia"] and "confiance" not in d["kyc"]["ia"]["lecture"]
    assert "revue" not in d["kyc"] and d["kyc"]["revue_humaine_requise"] is True
    assert fiche(client, b["id"])["validee"] is False
    # E-mail immédiat à l'équipe : résumé + lien direct vers le dossier
    mail = emails(boite)[-1]
    assert mail["a"] == "equipe@adlyn-test.bf" and "KYC à vérifier" in mail["sujet"]
    assert f"/plateforme?kyc={b['id']}" in mail["texte"] and "Ressemblance des visages incertaine" in mail["texte"]
    assert "B12345789" not in mail["texte"]
    # Super-admin : motifs détaillés et scores visibles
    dossier = dossier_admin(client, super_admin, b["id"])
    assert dossier["kyc"]["revue_humaine_requise"] is True and dossier["kyc"]["revue"]["motifs"][0] == code
    assert dossier["kyc"]["ia"]["visage"]["confiance_visage"] == visage["confiance_visage"]


def test_visages_differents_revue_humaine(client, inscrite, ia, boite):
    b, h = inscrite()
    ia.lecture = lecture_avec(meme_personne="non", confiance_visage=0.9)
    d = envoyer(client, h).json()
    assert d["motif_code"] == "VISAGE_DIFFERENT" and d["kyc"]["statut"] == "EN_ATTENTE"
    assert d["message"] == kyc_ia.MESSAGE_REVUE  # le commerçant ne sait pas ce qui a été détecté
    assert fiche(client, b["id"])["kyc"]["revue_humaine_requise"] is True
    assert fiche(client, b["id"])["validee"] is False and emails(boite)


@pytest.mark.parametrize("visage, code, libelle", [
    ({"photo_d_ecran": True}, "FRAUDE_SUSPECTEE", "photo d'un écran"),
    ({"photo_de_photo": True}, "FRAUDE_SUSPECTEE", "photo d'une photo"),
    ({"visage_masque": True}, "FRAUDE_SUSPECTEE", "visage masqué"),
    ({"piece_selfie_correspond": "non"}, "PIECE_SELFIE_DIFFERENTE", "pièce tenue"),
])
def test_signe_de_fraude_revue_humaine(client, inscrite, ia, boite, super_admin, visage, code, libelle):
    b, h = inscrite()
    ia.lecture = lecture_avec(**visage)
    d = envoyer(client, h).json()
    assert d["motif_code"] == code and d["revue_humaine"] and fiche(client, b["id"])["validee"] is False
    revue = dossier_admin(client, super_admin, b["id"])["kyc"]["revue"]
    assert any(libelle in t for t in revue["libelles"])


def test_plusieurs_motifs_tous_listes(client, inscrite, ia, boite, super_admin):
    b, h = inscrite()
    ia.lecture = {**lecture_avec(meme_personne="non", montage_suspecte=True), "nom": "KABORE"}
    envoyer(client, h)
    motifs = dossier_admin(client, super_admin, b["id"])["kyc"]["revue"]["motifs"]
    assert motifs[0] == "NOM_DIFFERENT" and {"VISAGE_DIFFERENT", "FRAUDE_SUSPECTEE"} <= set(motifs)


def test_selfie_manquant_revue_humaine_sans_erreur(client, inscrite, ia, boite, super_admin):
    b, h = inscrite()
    r = envoyer(client, h, selfie=None)
    assert r.status_code == 200
    d = r.json()
    assert d["motif_code"] == "SELFIE_MANQUANT" and d["revue_humaine"] and emails(boite)
    # L'IA a lu la pièce seule (schéma du lot C, sans avis « visage »)
    assert "visage" not in ia.appels[0]["output_config"]["format"]["schema"]["required"]
    # Réglage « Exiger le selfie » coupé : le même envoi est validé automatiquement (comme au lot C)
    r = client.put("/api/plateforme/parametres/kyc-ia", headers=super_admin, json={
        "auto_validation": True, "seuil_confiance": 0.8, "max_par_jour": 5, "exiger_selfie": False, "seuil_visage": 0.9})
    assert r.status_code == 200 and r.json()["exiger_selfie"] is False and r.json()["seuil_visage"] == 0.9
    assert envoyer(client, h, selfie=None).json()["decision"] == "VERIFIE"


def test_selfie_controle(client, inscrite, ia, boite):
    b, h = inscrite()
    # Un PDF n'est pas une photo prise sur le moment ; un faux fichier image est refusé
    assert envoyer(client, h, selfie=PDF).status_code == 400
    assert envoyer(client, h, selfie=b"pas une image").status_code == 400
    assert not ia.appels


def test_ia_indisponible_revue_humaine(client, inscrite, ia, boite):
    b, h = inscrite()
    ia.erreur = RuntimeError("refus ou panne")
    d = envoyer(client, h).json()
    assert d["motif_code"] == "IA_INDISPONIBLE" and d["revue_humaine"] and d["message"] == kyc_ia.MESSAGE_REVUE
    assert fiche(client, b["id"])["kyc"]["revue_humaine_requise"] is True
    assert len(fiche(client, b["id"])["kyc"]["documents"]) == 2 and emails(boite)


def test_alerte_whatsapp_aux_super_admins_avec_telephone(client, inscrite, ia, boite):
    email = get_settings().super_admin_email
    client.portal.call(lambda: db.users.update_one({"email": email}, {"$set": {"telephone": "+22670999999"}}))
    try:
        b, h = inscrite()
        ia.lecture = lecture_avec(meme_personne="incertain")
        envoyer(client, h)
        alerte = [m for m in boite if m["canal"] == "whatsapp" and m["a"] == "+22670999999"]
        assert alerte and "KYC à vérifier" in alerte[0]["texte"]
    finally:
        client.portal.call(lambda: db.users.update_one({"email": email}, {"$unset": {"telephone": ""}}))


# ---------------------------------------------------------------------------
# Décisions du super-administrateur
# ---------------------------------------------------------------------------
def test_validation_humaine(client, inscrite, ia, boite, super_admin):
    b, h = inscrite()
    ia.lecture = lecture_avec(meme_personne="incertain")
    envoyer(client, h)
    url = f"/api/plateforme/boutiques/{b['id']}/kyc/valider-identite"
    assert client.post(url, headers=h).status_code == 403
    r = client.post(url, headers=super_admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["kyc"]["statut"] == "VERIFIE" and d["kyc"]["revue_humaine_requise"] is False
    assert d["kyc"]["verifie_par"] == "Administrateur plateforme" and d["validee_maintenant"]
    f = fiche(client, b["id"])
    assert f["validee"] is True and f["validee_par"] == "Administrateur plateforme"
    # Le commerçant est prévenu par WhatsApp ; journal de la décision
    assert any(m["canal"] == "whatsapp" and "vérifiée par l'équipe adLyn" in m["texte"] for m in boite)
    journal = client.get(f"/api/plateforme/boutiques/{b['id']}/kyc/ia-journal", headers=super_admin).json()
    assert journal[0]["type"] == "VALIDATION_ADMIN"
    # Sans pièce d'identité : impossible
    b2, _ = inscrite()
    assert client.post(f"/api/plateforme/boutiques/{b2['id']}/kyc/valider-identite", headers=super_admin).status_code == 400


def test_refus_sort_de_la_file(client, inscrite, ia, boite, super_admin):
    b, h = inscrite()
    ia.lecture = lecture_avec(meme_personne="non")
    envoyer(client, h)
    r = client.post(f"/api/plateforme/boutiques/{b['id']}/kyc/refuser", headers=super_admin,
                    json={"motif": "La personne sur la photo n'est pas le titulaire de la pièce"})
    assert r.status_code == 200 and r.json()["statut"] == "REJETE" and r.json()["revue_humaine_requise"] is False
    assert fiche(client, b["id"])["validee"] is False
    assert any(m["canal"] == "whatsapp" and "pas le titulaire" in m["texte"] for m in boite)


def test_demande_de_nouvelle_photo(client, inscrite, ia, boite, super_admin):
    b, h = inscrite()
    ia.lecture = lecture_avec(photo_de_photo=True)
    envoyer(client, h)
    url = f"/api/plateforme/boutiques/{b['id']}/kyc/nouvelle-photo"
    assert client.post(url, headers=h, json={"motif": "x"}).status_code == 403
    assert client.post(url, headers=super_admin, json={"motif": ""}).status_code == 422
    r = client.post(url, headers=super_admin, json={"motif": "Visage flou : reprenez la photo à la lumière du jour"})
    assert r.status_code == 200 and r.json()["revue_humaine_requise"] is False
    # Le commerçant voit le motif dans son dossier et reçoit un WhatsApp avec le lien pour renvoyer
    kyc = client.get("/api/boutique", headers=h).json()["kyc"]
    assert kyc["nouvelle_photo"]["motif"].startswith("Visage flou") and kyc["statut"] == "EN_ATTENTE"
    assert any(m["canal"] == "whatsapp" and "nouvelle photo" in m["texte"] and "onglet=kyc" in m["texte"] for m in boite)
    # Il renvoie : la demande est close et, tout concordant cette fois, la boutique est validée
    ia.lecture = dict(LECTURE_BONNE)
    d = envoyer(client, h).json()
    assert d["decision"] == "VERIFIE" and not d["kyc"].get("nouvelle_photo")
    # Identité déjà vérifiée : plus de demande possible
    assert client.post(url, headers=super_admin, json={"motif": "encore"}).status_code == 409


# ---------------------------------------------------------------------------
# Confidentialité : images réservées au super-admin, aucune clé de stockage
# ---------------------------------------------------------------------------
def test_images_reservees_au_super_admin(client, inscrite, ia, boite, super_admin):
    b, h = inscrite()
    ia.lecture = lecture_avec(meme_personne="incertain")
    docs = envoyer(client, h, verso=JPEG).json()["kyc"]["documents"]
    selfie = next(p for p in docs if p["type"] == "SELFIE_DG")
    recto = next(p for p in docs if p.get("face") == "RECTO")
    url = f"/api/plateforme/boutiques/{b['id']}/kyc/images/{selfie['id']}"
    # Commerçant : 403 sur la route d'image ET sur son propre lien vers le selfie
    assert client.get(url, headers=h).status_code == 403
    assert client.get(f"/api/boutique/kyc/documents/{selfie['id']}", headers=h).status_code == 403
    assert client.get(f"/api/boutique/kyc/documents/{recto['id']}", headers=h).status_code == 200
    assert client.get(url).status_code in (401, 403)  # sans connexion
    # Super-admin : l'image elle-même, sans cache, jamais de redirection vers une adresse
    r = client.get(url, headers=super_admin, follow_redirects=False)
    assert r.status_code == 200 and r.content == JPEG and r.headers["content-type"] == "image/jpeg"
    assert "no-store" in r.headers["cache-control"]
    assert client.get(f"/api/plateforme/boutiques/{b['id']}/kyc/images/inconnue", headers=super_admin).status_code == 404


def test_aucune_cle_de_stockage_dans_les_reponses(client, inscrite, ia, boite, super_admin):
    b, h = inscrite()
    ia.lecture = lecture_avec(meme_personne="incertain")
    base = f"/api/plateforme/boutiques/{b['id']}"
    reponses = [envoyer(client, h, verso=JPEG).text, client.get("/api/boutique", headers=h).text,
                client.get("/api/plateforme/boutiques", headers=super_admin).text,
                client.post(f"{base}/kyc/relancer-ia", headers=super_admin).text,
                client.get(f"{base}/kyc/ia-journal", headers=super_admin).text,
                client.post(f"{base}/kyc/nouvelle-photo", headers=super_admin, json={"motif": "Photo floue"}).text,
                client.post(f"{base}/kyc/valider-identite", headers=super_admin).text]
    cles = [p["cle"] for p in fiche(client, b["id"])["kyc"]["documents"]]
    assert len(cles) == 3
    for texte in reponses:
        # Ni champ « cle » de stockage (toutes commencent par « boutiques/ »), ni chemin du stockage privé
        # (d'autres champs « cle » sans rapport existent, ex. champs propres à un secteur d'activité)
        assert '"cle":"boutiques/' not in texte and "/kyc/" not in texte.replace(base, "")
        assert not any(c in texte for c in cles)
        assert "B12345789" not in texte


def test_retrocompatibilite_lot_c(client, inscrite, super_admin):
    """Dossiers enregistrés au lot C (sans l'indicateur de revue) : un dossier vérifié le reste
    et n'entre pas dans la file ; un dossier en attente après une lecture IA y entre."""
    verifie, _ = inscrite(validee=True)
    attente, _ = inscrite()
    client.portal.call(lambda: db.boutiques.update_one({"id": verifie["id"]}, {"$set": {"kyc": {
        "statut": "VERIFIE", "motif_rejet": "", "documents": [], "verifie_par": "IA (Liluvine)",
        "date_verification": "2026-10-10T10:00:00+00:00", "ia": {"decision": "VERIFIE", "motif_code": "CONCORDANT"}}}}))
    client.portal.call(lambda: db.boutiques.update_one({"id": attente["id"]}, {"$set": {"kyc": {
        "statut": "EN_ATTENTE", "motif_rejet": "", "documents": [], "verifie_par": "", "date_verification": None,
        "ia": {"decision": "EN_ATTENTE", "motif_code": "ILLISIBLE"}}}}))
    v = dossier_admin(client, super_admin, verifie["id"])
    assert v["kyc"]["statut"] == "VERIFIE" and v["kyc"]["revue_humaine_requise"] is False and v["validee"] is True
    assert dossier_admin(client, super_admin, attente["id"])["kyc"]["revue_humaine_requise"] is True


def test_reglages_du_selfie(client, super_admin):
    r = client.get("/api/plateforme/parametres/kyc-ia", headers=super_admin).json()
    assert r["exiger_selfie"] is True and r["seuil_visage"] == 0.85  # valeurs par défaut
    mauvais = {"auto_validation": True, "seuil_confiance": 0.8, "max_par_jour": 5, "seuil_visage": 1.5}
    assert client.put("/api/plateforme/parametres/kyc-ia", headers=super_admin, json=mauvais).status_code == 422
    assert json.dumps(r).find("cle-de-test") == -1  # jamais la clé de l'IA
