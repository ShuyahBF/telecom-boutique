"""Service SMS des boutiques : configuration par le super-admin, envois (manuels et
automatiques), journal par contact, facturation, retard et suspension du seul service SMS."""
from datetime import timedelta

import pytest

import envois_plateforme
import sms_boutiques
from abonnements import aujourd_hui

AUJ = aujourd_hui().isoformat()


@pytest.fixture
def ovh(monkeypatch):
    """Remplace l'envoi OVH : on garde chaque SMS « envoyé » en mémoire."""
    boite = []

    async def faux_ovh(telephone, texte, expediteur, service=None):
        boite.append({"tel": telephone, "texte": texte, "expediteur": expediteur, "service": service})
        return "ENVOYE", ""

    monkeypatch.setattr(envois_plateforme, "envoyer_sms_ovh", faux_ovh)
    return boite


def configurer(client, super_admin, b, **extra):
    r = client.put(f"/api/plateforme/sms/boutiques/{b['id']}", headers=super_admin,
                   json={"expediteur": "FASOMOBILE", "prix_sms": 25, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_nombre_de_sms():
    assert sms_boutiques.nombre_sms("Bonjour") == 1
    assert sms_boutiques.nombre_sms("a" * 160) == 1 and sms_boutiques.nombre_sms("a" * 161) == 2
    # « ê » n'existe pas en GSM 7 bits : 70 caractères par SMS
    assert sms_boutiques.nombre_sms("ê" * 70) == 1 and sms_boutiques.nombre_sms("ê" * 71) == 2


def test_configuration_et_envois(client, super_admin, boutique_equipee, ovh):
    a = boutique_equipee
    b, h = a["boutique"], a["h"]
    # Non configuré : aucun envoi possible
    assert client.get("/api/boutique/sms", headers=h).json()["statut"] == "NON_CONFIGURE"
    assert client.post("/api/boutique/sms/envoyer", headers=h, json={"telephone": "70112233", "texte": "Test"}).status_code == 403
    # Expéditeur invalide refusé ; la boutique ne peut pas se configurer elle-même
    assert client.put(f"/api/plateforme/sms/boutiques/{b['id']}", headers=super_admin,
                      json={"expediteur": "Faso Mob!", "prix_sms": 25}).status_code == 400
    assert client.put(f"/api/plateforme/sms/boutiques/{b['id']}", headers=h,
                      json={"expediteur": "PIRATE", "prix_sms": 0}).status_code == 403
    assert configurer(client, super_admin, b, service_ovh="sms-ab123-1")["statut"] == "ACTIF"

    # Envoi manuel (1 SMS) + notification automatique d'un dépôt SAV (client avec téléphone)
    r = client.post("/api/boutique/sms/envoyer", headers=h, json={
        "telephone": "70 11 22 33", "texte": "Votre téléphone est prêt", "contact_nom": "Client Test"})
    assert r.status_code == 201 and r.json()["statut"] == "ENVOYE" and r.json()["nb_sms"] == 1
    assert ovh[-1]["expediteur"] == "FASOMOBILE" and ovh[-1]["service"] == "sms-ab123-1"
    d = client.post("/api/maintenance", headers=h, json={
        "client_id": a["client"]["id"], "marque": "Tecno", "modele": "Spark 20", "panne_declaree": "Écran cassé"})
    assert d.status_code == 201, d.text
    client.get("/api/boutique/sms", headers=h)  # laisse la tâche de fond se terminer
    assert any(d.json()["numero"] in s["texte"] for s in ovh)

    # Journal regroupé par contact
    contacts = client.get("/api/boutique/sms/contacts", headers=h).json()
    c = next(x for x in contacts if x["telephone"] == "70112233")
    assert c["nb_messages"] == 2 and c["contact_nom"] == "Client Test"
    assert len(client.get("/api/boutique/sms/contacts/70112233", headers=h).json()) == 2
    # Le super-admin voit la même liste
    assert client.get(f"/api/plateforme/sms/boutiques/{b['id']}/contacts", headers=super_admin).json()[0]["telephone"]

    # SMS automatiques désactivés : plus de notification, l'envoi manuel reste possible
    configurer(client, super_admin, b, notifications_auto=False)
    avant = len(ovh)
    client.post("/api/maintenance", headers=h, json={"client_id": a["client"]["id"], "marque": "Itel", "modele": "A70", "panne_declaree": "Batterie"})
    client.get("/api/boutique/sms", headers=h)
    assert len(ovh) == avant


def test_facturation_retard_et_suspension(client, super_admin, boutique_equipee, ovh, monkeypatch):
    a = boutique_equipee
    b, h = a["boutique"], a["h"]
    configurer(client, super_admin, b, prix_sms=30)
    for texte in ("Premier message", "x" * 200):  # 1 + 2 SMS
        client.post("/api/boutique/sms/envoyer", headers=h, json={"telephone": "76000000", "texte": texte})
    assert client.get("/api/boutique/sms", headers=h).json()["mois_montant"] == 90

    # Facture de la période : 3 SMS x 30 FCFA ; les SMS ne sont facturés qu'une fois
    r = client.post("/api/plateforme/sms/factures/generer", headers=super_admin,
                    json={"debut": AUJ, "fin": AUJ, "boutique_id": b["id"]})
    facture = r.json()[0]
    assert facture["nb_sms"] == 3 and facture["montant"] == 90 and facture["statut"] == "A_PAYER"
    assert client.post("/api/plateforme/sms/factures/generer", headers=super_admin,
                       json={"debut": AUJ, "fin": AUJ, "boutique_id": b["id"]}).json() == []
    assert client.get("/api/boutique/sms/factures", headers=h).json()[0]["id"] == facture["id"]

    # Échéance dépassée : la boutique apparaît dans les retards du service SMS
    client.portal.call(lambda: sms_boutiques.db.sms_factures.update_one(
        {"id": facture["id"]}, {"$set": {"echeance": (aujourd_hui() - timedelta(days=4)).isoformat()}}))
    retards = client.get("/api/plateforme/sms/retards", headers=super_admin).json()
    ligne = next(x for x in retards["boutiques"] if x["boutique_id"] == b["id"])
    assert ligne["jours_retard"] == 4 and ligne["montant_du"] == 90

    # Suspension du SEUL service SMS : plus d'envoi, mais la boutique fonctionne
    assert client.post("/api/plateforme/sms/suspendre", headers=super_admin, json={"boutique_ids": [b["id"]]}).json()["suspendues"] == 1
    assert client.get("/api/boutique/sms", headers=h).json()["statut"] == "SUSPENDU"
    assert client.post("/api/boutique/sms/envoyer", headers=h, json={"telephone": "76000000", "texte": "x"}).status_code == 403
    assert client.get("/api/produits", headers=h).status_code == 200

    # Paiement de la facture (en ligne, appliqué une seule fois) : service rétabli
    from routes.paiements import appliquer_statut

    paiement = {"deposit_id": f"sms-{facture['id']}", "boutique_id": b["id"], "montant": 90, "type": "facture_sms",
                "facture_id": facture["id"], "statut": "en_attente", "created_at": "2026-01-01"}
    client.portal.call(lambda: sms_boutiques.db.paiements.insert_one(dict(paiement)))
    for _ in range(2):
        client.portal.call(lambda: appliquer_statut(paiement, {"status": "COMPLETED", "amount": "90"}))
    assert client.get("/api/boutique/sms/factures", headers=h).json()[0]["statut"] == "PAYEE"
    assert client.get("/api/boutique/sms", headers=h).json()["statut"] == "ACTIF"


def test_paiement_saisi_et_facturation_mensuelle(client, super_admin, boutique_equipee, ovh, monkeypatch):
    a = boutique_equipee
    configurer(client, super_admin, a["boutique"])
    client.post("/api/boutique/sms/envoyer", headers=a["h"], json={"telephone": "70000001", "texte": "Bonjour"})
    # Pas le 1er du mois : rien n'est facturé automatiquement
    monkeypatch.setattr(sms_boutiques, "aujourd_hui", lambda: aujourd_hui().replace(day=15))
    assert client.portal.call(sms_boutiques.facturation_mensuelle) == []
    f = client.post("/api/plateforme/sms/factures/generer", headers=super_admin,
                    json={"debut": AUJ, "fin": AUJ, "boutique_id": a["boutique"]["id"]}).json()[0]
    r = client.post(f"/api/plateforme/sms/factures/{f['id']}/paiements", headers=super_admin,
                    json={"mode": "ESPECES", "reference": "Reçu 7"})
    assert r.json()["statut"] == "PAYEE" and r.json()["paiement"]["mode"] == "ESPECES"
    # Liste des boutiques côté super-admin : réservée
    assert client.get("/api/plateforme/sms/boutiques", headers=a["h"]).status_code == 403
    ligne = next(x for x in client.get("/api/plateforme/sms/boutiques", headers=super_admin).json()
                 if x["id"] == a["boutique"]["id"])
    assert ligne["service"]["expediteur"] == "FASOMOBILE" and ligne["montant_du"] == 0
