"""Boutiques internes (présentation) : invisibles des visiteurs, visibles du
super-admin sur le portail, et aucun message ne part de chez elles."""
import messagerie


def test_boutique_interne(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique(nom="Galaxie Mobile Koudougou")
    assert client.patch(f"/api/plateforme/boutiques/{b['id']}", headers=super_admin, json={"test": True}).status_code == 200
    client.cookies.clear()
    # Visiteur : ni dans l'annuaire, ni par son adresse, ni par son code
    assert b["id"] not in [x["id"] for x in client.get("/api/public/boutiques").json()]
    assert client.get(f"/api/public/b/{b['slug']}").status_code == 404
    assert client.get(f"/api/public/b/{b['code_marchand']}").status_code == 404
    # Le personnel de la boutique (non super-admin) ne la voit pas non plus sur le portail public
    assert client.get(f"/api/public/b/{b['slug']}", headers=h).status_code == 404
    # Super-admin connecté : visible
    assert b["id"] in [x["id"] for x in client.get("/api/public/boutiques", headers=super_admin).json()]
    assert client.get(f"/api/public/b/{b['slug']}", headers=super_admin).status_code == 200
    # Aucun e-mail ne part, même avec un serveur d'envoi réglé
    boutique = dict(b, test=True, messagerie={"email_actif": True, "smtp_hote": "smtp.exemple.bf"})
    journal = client.portal.call(lambda: messagerie.envoyer_email(boutique, "client@exemple.bf", "Sujet", "Texte"))
    assert journal["statut"] == "NON_ENVOYE"
    # Rendue publique : visible de tous
    client.patch(f"/api/plateforme/boutiques/{b['id']}", headers=super_admin, json={"test": False})
    assert client.get(f"/api/public/b/{b['slug']}").status_code == 200
