"""Reversements aux boutiques de l'argent encaissé par PawaPay : suivi par le
super-admin, et chaque boutique ne voit que les siens."""
from db import db


def paiement(client, boutique_id, montant, statut="paye", type_=None):
    """Paiement PawaPay d'une commande, déjà confirmé (inséré directement)."""
    doc = {"id": f"p-{boutique_id[:6]}-{montant}-{statut}-{type_}", "deposit_id": f"d-{boutique_id}-{montant}-{statut}-{type_}",
           "boutique_id": boutique_id, "montant": montant, "statut": statut, "commande_numero": "CMD-1",
           "client_nom": "Client", "created_at": "2026-09-01T10:00:00+00:00"}
    if type_:
        doc["type"] = type_
    client.portal.call(lambda: db.paiements.insert_one(dict(doc)))
    return doc["id"]


def test_reversements(client, super_admin, nouvelle_boutique):
    a, ha = nouvelle_boutique()
    b, hb = nouvelle_boutique()
    p1 = paiement(client, a["id"], 50000)
    p2 = paiement(client, a["id"], 20000)
    paiement(client, a["id"], 9999, statut="echec")          # échec : jamais reversé
    paiement(client, a["id"], 5000, type_="abonnement")      # argent dû à la plateforme : exclu
    paiement(client, b["id"], 30000)

    # Chaque boutique ne voit que ses propres encaissements
    va = client.get("/api/reversements", headers=ha).json()
    assert va["situation"]["encaisse"] == 70000 and va["situation"]["a_reverser"] == 70000
    assert {p["id"] for p in va["paiements"]} == {p1, p2}
    assert client.get("/api/reversements", headers=hb).json()["situation"]["encaisse"] == 30000
    # Réservé au super-admin
    assert client.get("/api/plateforme/reversements/boutiques", headers=ha).status_code == 403

    # Le super-admin reverse les deux paiements, avec 1 000 FCFA de frais
    assert len(client.get(f"/api/plateforme/reversements/boutiques/{a['id']}/a-reverser", headers=super_admin).json()) == 2
    r = client.post("/api/plateforme/reversements", headers=super_admin, json={
        "boutique_id": a["id"], "paiement_ids": [p1, p2], "frais": 1000, "mode": "MOBILE_MONEY", "reference": "OM-123"})
    assert r.status_code == 201, r.text
    rev = r.json()
    assert rev["montant_brut"] == 70000 and rev["montant_net"] == 69000
    # Impossible de reverser deux fois le même paiement, ou celui d'une autre boutique
    assert client.post("/api/plateforme/reversements", headers=super_admin,
                       json={"boutique_id": a["id"], "paiement_ids": [p1]}).status_code == 409
    pb = client.get(f"/api/plateforme/reversements/boutiques/{b['id']}/a-reverser", headers=super_admin).json()[0]["id"]
    assert client.post("/api/plateforme/reversements", headers=super_admin,
                       json={"boutique_id": a["id"], "paiement_ids": [pb]}).status_code == 409

    va = client.get("/api/reversements", headers=ha).json()
    assert va["situation"]["reverse"] == 69000 and va["situation"]["frais"] == 1000 and va["situation"]["a_reverser"] == 0
    assert all(p["reversement_numero"] == rev["numero"] for p in va["paiements"])
    assert client.get("/api/reversements", headers=hb).json()["reversements"] == []  # rien chez B

    ligne = next(x for x in client.get("/api/plateforme/reversements/boutiques", headers=super_admin).json()["boutiques"]
                 if x["id"] == a["id"])
    assert ligne["reverse"] == 69000 and ligne["a_reverser"] == 0

    # Annulation : les paiements redeviennent « à reverser »
    assert client.post(f"/api/plateforme/reversements/{rev['id']}/annuler", headers=super_admin).status_code == 200
    va = client.get("/api/reversements", headers=ha).json()
    assert va["situation"]["a_reverser"] == 70000 and va["situation"]["reverse"] == 0
