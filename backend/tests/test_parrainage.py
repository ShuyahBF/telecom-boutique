"""Parrainage entre boutiques : invitation acceptée, bonus validé à l'ouverture
de la boutique filleule, bonus déduit de l'abonnement (en totalité ou en partie)."""
import pytest

from config import get_settings

_n = {"i": 0}


def _demande(**extra):
    """Formulaire d'ouverture rempli par une personne invitée (valeurs uniques)."""
    _n["i"] += 1
    i = _n["i"]
    return {"nom": f"Telephonie Filleule {chr(65 + i)}{chr(66 + i)}", "ville": "Bobo-Dioulasso",
            "dg_nom": f"Filleul Numero {i}", "dg_email": f"filleul{i}@exemple.bf",
            "dg_telephone": f"+226 76 {i:02d} 11 22", "accepte_invitation": True, "accepte_conditions": True, **extra}


@pytest.fixture
def parrain(client, nouvelle_boutique):
    b, h = nouvelle_boutique()
    return b, h


def _solde(client, h):
    return client.get("/api/boutique/parrainage", headers=h).json()["solde"]


def test_invitation_et_bonus_a_l_ouverture(client, super_admin, parrain):
    b, h = parrain
    info = client.get("/api/boutique/parrainage", headers=h).json()
    assert info["lien"].endswith(f"/ouvrir-ma-boutique?parrain={b['code_marchand']}")
    assert info["bonus_unitaire"] == 500 and info["lien_actif"]
    assert client.get(f"/api/public/parrainage/{b['code_marchand']}").json()["parrain"]["nom"] == b["nom"]
    assert client.get("/api/public/parrainage/ZZZZZZ").status_code == 404

    # Invitation non acceptée : refus
    r = client.post(f"/api/public/parrainage/{b['code_marchand']}/demande", json=_demande(accepte_invitation=False))
    assert r.status_code == 400
    # Invitation acceptée : boutique créée EN ATTENTE, aucun bonus encore
    r = client.post(f"/api/public/parrainage/{b['code_marchand']}/demande", json=_demande())
    assert r.status_code == 201, r.text
    assert r.json()["statut"] == "EN_ATTENTE_VALIDATION"
    filleuls = client.get("/api/boutique/parrainage", headers=h).json()["filleuls"]
    assert len(filleuls) == 1 and filleuls[0]["statut"] == "EN_ATTENTE"
    assert _solde(client, h)["disponible"] == 0

    # L'administrateur ouvre la boutique filleule : bonus validé (une seule fois)
    tous = client.get("/api/plateforme/parrainages", headers=super_admin).json()
    filleul_id = next(p["filleul_id"] for p in tous if p["parrain_id"] == b["id"])
    for _ in range(2):
        assert client.post(f"/api/plateforme/boutiques/{filleul_id}/valider", headers=super_admin).status_code == 200
    info = client.get("/api/boutique/parrainage", headers=h).json()
    assert info["filleuls"][0]["statut"] == "VALIDE"
    assert info["solde"] == {"gagnes": 500, "utilises": 0, "reserves": 0, "disponible": 500}
    # Réservé au DG / au super-admin
    assert client.get("/api/plateforme/parrainages", headers=h).status_code == 403


def test_garde_fous(client, super_admin, parrain):
    b, h = parrain
    code = b["code_marchand"]
    d = _demande()
    assert client.post(f"/api/public/parrainage/{code}/demande", json=d).status_code == 201
    # Même boutique / même DG : refusé
    assert client.post(f"/api/public/parrainage/{code}/demande", json=d).status_code == 409
    # Se parrainer soi-même (téléphone de la boutique marraine) : refusé
    r = client.post(f"/api/public/parrainage/{code}/demande", json=_demande(dg_telephone=b["telephone"] or "25 00 00 00"))
    assert r.status_code == 400
    # Conditions non acceptées : refusé
    assert client.post(f"/api/public/parrainage/{code}/demande", json=_demande(accepte_conditions=False)).status_code == 400
    # Une boutique filleule pas encore ouverte ne peut pas parrainer à son tour
    filleul = next(p for p in client.get("/api/plateforme/parrainages", headers=super_admin).json()
                   if p["parrain_id"] == b["id"])
    boutiques = client.get("/api/plateforme/boutiques", headers=super_admin).json()
    code_filleul = next(x["code_marchand"] for x in boutiques if x["id"] == filleul["filleul_id"])
    assert client.get(f"/api/public/parrainage/{code_filleul}").status_code == 404


def test_limite_par_parrain(client, parrain, monkeypatch):
    b, _ = parrain
    monkeypatch.setattr(get_settings(), "parrainage_max_demandes_parrain_jour", 1)
    monkeypatch.setattr(get_settings(), "parrainage_max_demandes_ip_heure", 100)
    assert client.post(f"/api/public/parrainage/{b['code_marchand']}/demande", json=_demande()).status_code == 201
    assert client.post(f"/api/public/parrainage/{b['code_marchand']}/demande", json=_demande()).status_code == 429


def _ouvrir_filleuls(client, super_admin, b, nombre):
    """Crée et ouvre `nombre` boutiques filleules : le parrain gagne nombre × 500 F."""
    for _ in range(nombre):
        assert client.post(f"/api/public/parrainage/{b['code_marchand']}/demande", json=_demande()).status_code == 201
    for p in client.get("/api/plateforme/parrainages", headers=super_admin, params={"statut": "EN_ATTENTE"}).json():
        if p["parrain_id"] == b["id"]:
            client.post(f"/api/plateforme/boutiques/{p['filleul_id']}/valider", headers=super_admin)


def test_abonnement_paye_entierement_par_les_bonus(client, super_admin, parrain, monkeypatch):
    monkeypatch.setattr(get_settings(), "parrainage_max_demandes_ip_heure", 100)
    b, h = parrain
    _ouvrir_filleuls(client, super_admin, b, 2)  # 1 000 F de bonus
    client.post("/api/plateforme/abonnements/formules", headers=super_admin,
                json={"libelle": "Semaine test", "mois": 1, "montant": 800, "ordre": 9})
    code = next(f["code"] for f in client.get("/api/plateforme/abonnements/formules", headers=super_admin).json()
                if f["libelle"] == "Semaine test")
    avant = client.get("/api/boutique/abonnement", headers=h).json()["etat"]["echeance"]
    r = client.post("/api/boutique/abonnement/payer", headers=h, json={"formule": code, "utiliser_bonus": True})
    assert r.status_code == 200, r.text
    assert r.json()["paye_par_bonus"] is True
    donnees = client.get("/api/boutique/abonnement", headers=h).json()
    assert donnees["etat"]["echeance"] > avant
    p = donnees["paiements"][0]
    assert p["mode"] == "BONUS_PARRAINAGE" and p["bonus_deduit"] == 800 and p["montant"] == 0
    assert donnees["bonus"]["disponible"] == 200
    client.put(f"/api/plateforme/abonnements/formules/{code}", headers=super_admin,
               json={"libelle": "Semaine test", "mois": 1, "montant": 800, "actif": False, "ordre": 9})


def test_paiement_en_ligne_reduit_puis_echec_ou_succes(client, super_admin, parrain, monkeypatch):
    import routes.paiements as paiements
    from routes.paiements import appliquer_statut

    monkeypatch.setattr(get_settings(), "parrainage_max_demandes_ip_heure", 100)
    b, h = parrain
    _ouvrir_filleuls(client, super_admin, b, 1)  # 500 F
    monkeypatch.setattr(paiements, "_token", lambda: "cle-test")
    ouverts = []

    async def fausse_page(paiement, reason, retour, msisdn=""):
        await paiements.db.paiements.insert_one(dict(paiement, statut="en_attente"))
        ouverts.append(paiement)
        return "https://pawapay.test/page"

    monkeypatch.setattr(paiements, "_ouvrir_page", fausse_page)
    # Paiement du MENSUEL (5 000 F) avec les bonus : 4 500 F à payer, 500 F réservés
    r = client.post("/api/boutique/abonnement/payer", headers=h, json={"formule": "MENSUEL", "utiliser_bonus": True})
    assert r.status_code == 200 and r.json()["url"]
    assert ouverts[-1]["montant"] == 4500 and ouverts[-1]["bonus_deduit"] == 500
    assert _solde(client, h) == {"gagnes": 500, "utilises": 0, "reserves": 500, "disponible": 0}
    # Échec du paiement : les bonus redeviennent disponibles
    p = dict(ouverts[-1], statut="en_attente")
    client.portal.call(lambda: appliquer_statut(p, {"depositId": p["deposit_id"], "status": "FAILED"}))
    assert _solde(client, h)["disponible"] == 500
    # Nouvel essai réussi : bonus utilisés, échéance repoussée, paiement tracé
    client.post("/api/boutique/abonnement/payer", headers=h, json={"formule": "MENSUEL", "utiliser_bonus": True})
    p = dict(ouverts[-1], statut="en_attente")
    client.portal.call(lambda: appliquer_statut(p, {"depositId": p["deposit_id"], "status": "COMPLETED", "amount": "4500"}))
    assert _solde(client, h) == {"gagnes": 500, "utilises": 500, "reserves": 0, "disponible": 0}
    paye = client.get("/api/boutique/abonnement", headers=h).json()["paiements"][0]
    assert paye["montant"] == 4500 and paye["bonus_deduit"] == 500 and paye["mode"] == "PAWAPAY"


def test_saisie_admin_avec_bonus(client, super_admin, parrain, monkeypatch):
    monkeypatch.setattr(get_settings(), "parrainage_max_demandes_ip_heure", 100)
    b, h = parrain
    _ouvrir_filleuls(client, super_admin, b, 1)
    r = client.post(f"/api/plateforme/abonnements/boutiques/{b['id']}/paiements", headers=super_admin,
                    json={"formule": "MENSUEL", "mode": "ESPECES", "utiliser_bonus": True})
    assert r.status_code == 201 and r.json()["montant"] == 4500 and r.json()["bonus_deduit"] == 500
    assert _solde(client, h)["disponible"] == 0
