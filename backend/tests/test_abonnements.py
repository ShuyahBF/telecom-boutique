"""Abonnements : essai de 14 jours, retards, suspension choisie par le super-admin,
paiements (saisis ou en ligne), renouvellement selon la formule, rappels."""
from datetime import date, timedelta

import pytest

import abonnements
import envois_plateforme
from abonnements import ajouter_mois, aujourd_hui

AUJ = aujourd_hui()


def etat(client, h):
    r = client.get("/api/boutique/abonnement", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["etat"]


def fixer_echeance(client, super_admin, b, jours):
    """Échéance = aujourd'hui + jours (négatif = dépassée)."""
    r = client.patch(f"/api/plateforme/abonnements/boutiques/{b['id']}", headers=super_admin,
                     json={"echeance": (AUJ + timedelta(days=jours)).isoformat()})
    assert r.status_code == 200, r.text


def test_calcul_des_mois():
    assert ajouter_mois(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert ajouter_mois(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert ajouter_mois(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert ajouter_mois(date(2026, 10, 12), 12) == date(2027, 10, 12)


def test_essai_de_14_jours(client, nouvelle_boutique):
    _, h = nouvelle_boutique()
    e = etat(client, h)
    assert e["statut"] == "ESSAI" and e["en_essai"] is True
    assert e["jours_restants"] == 13  # jour de création compris : 14 jours
    assert e["echeance"] == (AUJ + timedelta(days=13)).isoformat()


def test_retard_suspension_et_paiement(client, super_admin, nouvelle_boutique, connecter_membre):
    b, h = nouvelle_boutique()
    # Un commercial de la boutique
    client.post("/api/boutique/equipe", headers=h, json={
        "nom": "Vendeur", "email": f"vendeur-{b['code_marchand'].lower()}@test.bf",
        "mot_de_passe": "motdepasse-123", "role": "commercial"})
    hc, _ = connecter_membre(b["code_marchand"], f"vendeur-{b['code_marchand'].lower()}@test.bf")

    # Échéance dépassée de 2 jours : la boutique apparaît dans les retards, sans être bloquée
    # (période de grâce de 3 jours, voir test_abonnement_grace.py pour la coupure automatique)
    fixer_echeance(client, super_admin, b, -2)
    retards = client.get("/api/plateforme/abonnements/retards", headers=super_admin).json()
    ligne = next(x for x in retards["boutiques"] if x["id"] == b["id"])
    assert ligne["abonnement"]["jours_retard"] == 2 and ligne["abonnement"]["statut"] == "EN_RETARD"
    assert ligne["abonnement"]["montant_attendu"] == 5000  # formule mensuelle par défaut
    assert client.get("/api/produits", headers=hc).status_code == 200  # pas encore de blocage

    # Le super-admin sélectionne la boutique et suspend son accès
    r = client.post("/api/plateforme/abonnements/suspendre", headers=super_admin, json={"boutique_ids": [b["id"]]})
    assert r.json()["suspendues"] == 1
    r = client.get("/api/produits", headers=hc)
    assert r.status_code == 403 and "abonnement" in r.json()["detail"].lower()
    assert client.get(f"/api/public/b/{b['slug']}").status_code == 404  # vitrine fermée aussi
    # Le DG garde l'accès à la page Abonnement (pour payer) ; pas le commercial
    assert etat(client, h)["statut"] == "SUSPENDU"
    assert client.get("/api/boutique/abonnement", headers=hc).status_code == 403

    # Paiement reçu (3 mois) : accès rendu, nouvelle échéance calculée depuis le jour du paiement
    r = client.post(f"/api/plateforme/abonnements/boutiques/{b['id']}/paiements", headers=super_admin,
                    json={"formule": "TRIMESTRIEL", "mode": "ESPECES", "reference": "Reçu 42"})
    assert r.status_code == 201, r.text
    assert r.json()["montant"] == 14000 and r.json()["reactivee"] is True
    e = etat(client, h)
    assert e["statut"] == "ACTIF" and e["en_essai"] is False
    assert e["echeance"] == ajouter_mois(AUJ - timedelta(days=1), 3).isoformat()
    assert client.get("/api/produits", headers=hc).status_code == 200


def test_renouvellement_anticipe_et_suspension_manuelle(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique()
    fin_essai = date.fromisoformat(etat(client, h)["echeance"])
    # Paiement pendant l'essai : l'essai n'est pas perdu, l'abonnement commence après
    client.post(f"/api/plateforme/abonnements/boutiques/{b['id']}/paiements", headers=super_admin,
                json={"formule": "ANNUEL", "mode": "VIREMENT"})
    assert etat(client, h)["echeance"] == ajouter_mois(fin_essai, 12).isoformat()
    # Suspension MANUELLE (autre motif) : un paiement ne la lève pas
    client.patch(f"/api/plateforme/boutiques/{b['id']}", headers=super_admin, json={"actif": False})
    client.post(f"/api/plateforme/abonnements/boutiques/{b['id']}/paiements", headers=super_admin,
                json={"formule": "MENSUEL", "mode": "ESPECES"})
    assert etat(client, h)["statut"] == "SUSPENDU"
    client.patch(f"/api/plateforme/boutiques/{b['id']}", headers=super_admin, json={"actif": True})
    assert etat(client, h)["statut"] == "ACTIF"


def test_paiement_en_ligne_applique_une_seule_fois(client, super_admin, nouvelle_boutique):
    from routes.paiements import appliquer_statut

    b, h = nouvelle_boutique()
    fixer_echeance(client, super_admin, b, -2)
    # PawaPay non configuré dans les tests : pas de page de paiement
    assert client.post("/api/boutique/abonnement/payer", headers=h, json={"formule": "MENSUEL"}).status_code == 503
    paiement = {"deposit_id": f"dep-{b['id']}", "boutique_id": b["id"], "montant": 5000, "type": "abonnement",
                "formule": "MENSUEL", "statut": "en_attente", "created_at": "2026-01-01"}
    client.portal.call(lambda: abonnements.db.paiements.insert_one(dict(paiement)))
    depot = {"depositId": paiement["deposit_id"], "status": "COMPLETED", "amount": "5000"}
    for _ in range(2):  # webhook + rapprochement : appliqué une seule fois
        client.portal.call(lambda: appliquer_statut(paiement, depot))
    e = etat(client, h)
    assert e["echeance"] == ajouter_mois(AUJ - timedelta(days=2), 1).isoformat()
    historique = client.get("/api/boutique/abonnement", headers=h).json()["paiements"]
    assert len(historique) == 1 and historique[0]["mode"] == "PAWAPAY"
    # Absent de l'historique des ventes de la boutique (ce n'est pas une vente)
    journal = client.get("/api/journal-paiements", headers=h).json()
    assert all("abonnement" not in str(x).lower() for x in journal.get("lignes", journal))


def test_rappels(client, super_admin, nouvelle_boutique, monkeypatch):
    envois = []

    async def faux_whatsapp(tel, variables, texte):
        envois.append(("wa", tel, texte))
        return "ENVOYE", ""

    async def faux_email(sujet, corps, a):
        envois.append(("email", a, sujet))
        return "ENVOYE", ""

    monkeypatch.setattr(envois_plateforme, "envoyer_whatsapp", faux_whatsapp)
    monkeypatch.setattr(envois_plateforme, "envoyer_email", faux_email)
    proche, _ = nouvelle_boutique(dg_telephone="70 11 22 33")
    loin, _ = nouvelle_boutique()
    en_retard, _ = nouvelle_boutique()
    fixer_echeance(client, super_admin, proche, 2)  # dans 2 jours : rappel
    fixer_echeance(client, super_admin, loin, 20)   # loin : pas de rappel
    fixer_echeance(client, super_admin, en_retard, -4)  # en retard : rappel chaque jour
    envoyes = client.post("/api/plateforme/abonnements/rappels/envoyer", headers=super_admin).json()["envoyes"]
    ids = {r["boutique_id"] for r in envoyes}
    assert proche["id"] in ids and en_retard["id"] in ids and loin["id"] not in ids
    wa = next(e for e in envois if e[0] == "wa" and e[1] == "70112233")
    assert "dans 2 jour(s)" in wa[2] and "5 000 FCFA" in wa[2]
    # Même jour : pas de second rappel
    encore = client.post("/api/plateforme/abonnements/rappels/envoyer", headers=super_admin).json()["envoyes"]
    assert not {r["boutique_id"] for r in encore} & ids
    journal = client.get("/api/plateforme/abonnements/rappels", headers=super_admin).json()
    assert any(r["boutique_id"] == proche["id"] and r["whatsapp"] == "ENVOYE" for r in journal)


def test_formules(client, super_admin, nouvelle_boutique):
    r = client.put("/api/plateforme/abonnements/formules/MENSUEL", headers=super_admin,
                   json={"libelle": "Mensuel (30 jours)", "mois": 1, "montant": 12500, "ordre": 1})
    assert r.status_code == 200 and r.json()["montant"] == 12500
    b, h = nouvelle_boutique()
    fixer_echeance(client, super_admin, b, -1)
    retards = client.get("/api/plateforme/abonnements/retards", headers=super_admin).json()["boutiques"]
    assert next(x for x in retards if x["id"] == b["id"])["abonnement"]["montant_attendu"] == 12500
    # Réservé au super-admin
    assert client.get("/api/plateforme/abonnements/retards", headers=h).status_code == 403
    client.put("/api/plateforme/abonnements/formules/MENSUEL", headers=super_admin,
               json={"libelle": "Mensuel (30 jours)", "mois": 1, "montant": 5000, "ordre": 1})


@pytest.mark.parametrize("champ", [{"formule": "INCONNUE"}])
def test_paiement_formule_inconnue(client, super_admin, nouvelle_boutique, champ):
    b, _ = nouvelle_boutique()
    assert client.post(f"/api/plateforme/abonnements/boutiques/{b['id']}/paiements", headers=super_admin,
                       json=champ).status_code == 400
