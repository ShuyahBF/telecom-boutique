"""Boutiques de démonstration (drapeau interne « test ») : visibles de tous sur le
portail comme de vraies boutiques, mais le drapeau n'est connu que du
super-administrateur ; pas de paiement en ligne ni d'envoi de message chez elles."""
import messagerie


def test_boutique_de_demonstration(client, super_admin, boutique_equipee):
    b, h = boutique_equipee["boutique"], boutique_equipee["h"]
    assert client.patch(f"/api/plateforme/boutiques/{b['id']}", headers=super_admin, json={"test": True}).status_code == 200
    client.cookies.clear()

    # Visiteur : la boutique est visible, sans aucune trace du drapeau
    assert b["id"] in [x["id"] for x in client.get("/api/public/boutiques").json()]
    fiche = client.get(f"/api/public/b/{b['slug']}")
    assert fiche.status_code == 200 and "test" not in fiche.json()
    assert fiche.json()["paiement_mobile_money"] is False  # jamais de paiement en ligne

    # Le personnel de la boutique ne voit pas le drapeau non plus
    assert "test" not in client.get("/api/auth/me", headers=h).json()["boutique"]
    assert "test" not in client.get("/api/boutique", headers=h).json()
    # Le super-admin, lui, le voit dans l'administration
    ligne = next(x for x in client.get("/api/plateforme/boutiques", headers=super_admin).json() if x["id"] == b["id"])
    assert ligne["test"] is True

    # Commande : Mobile Money refusé, paiement à la livraison accepté
    commande = {"nom": "Client Portail", "telephone": "70000000",
                "lignes": [{"produit_id": boutique_equipee["tel"]["id"], "quantite": 1}]}
    assert client.post(f"/api/public/b/{b['slug']}/commandes", json={**commande, "mode_paiement": "MOBILE_MONEY"}).status_code == 400
    assert client.post(f"/api/public/b/{b['slug']}/commandes", json=commande).status_code == 201

    # Aucun e-mail ne part, même avec un serveur d'envoi réglé
    boutique = dict(b, test=True, messagerie={"email_actif": True, "smtp_hote": "smtp.exemple.bf"})
    journal = client.portal.call(lambda: messagerie.envoyer_email(boutique, "client@exemple.bf", "Sujet", "Texte"))
    assert journal["statut"] == "NON_ENVOYE"
