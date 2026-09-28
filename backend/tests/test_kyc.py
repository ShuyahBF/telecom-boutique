"""Dossier KYC des boutiques : justificatifs PRIVÉS, vérification par l'administrateur."""
import io


def test_creation_avec_identification(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique(pays="Côte d'Ivoire", ville="Abidjan", latitude=5.3364, longitude=-4.0267,
                             dg_nom="Koné Awa", ifu="IFU123", cnss="CNSS456", rccm="CI-ABJ-2026-B-1")
    assert (b["pays"], b["dg_nom"], b["cnss"]) == ("Côte d'Ivoire", "Koné Awa", "CNSS456")
    assert b["kyc"]["statut"] == "NON_FOURNI"
    public = client.get(f"/api/public/b/{b['slug']}").json()
    assert public["latitude"] == 5.3364 and public["pays"] == "Côte d'Ivoire"
    assert "kyc" not in public and "cnss" not in public  # rien du dossier KYC côté public


def test_justificatifs_prives(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique()
    fichier = {"fichier": ("cni.pdf", io.BytesIO(b"%PDF-1.4 piece identite"), "application/pdf")}
    kyc = client.post("/api/boutique/kyc/documents", headers=h, files=fichier, data={"type_piece": "PIECE_IDENTITE_DG"}).json()
    assert kyc["statut"] == "EN_ATTENTE" and "cle" not in kyc["documents"][0]
    piece_id = kyc["documents"][0]["id"]
    # Le DG peut ouvrir son justificatif ; l'adresse n'est jamais publique
    r = client.get(f"/api/boutique/kyc/documents/{piece_id}", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert client.get(f"/api/boutique/kyc/documents/{piece_id}").status_code == 401
    # Une autre boutique ne peut pas l'ouvrir
    _, h2 = nouvelle_boutique()
    assert client.get(f"/api/boutique/kyc/documents/{piece_id}", headers=h2).status_code == 404
    # Décision de l'administrateur
    assert client.post(f"/api/plateforme/boutiques/{b['id']}/kyc/decision", headers=super_admin,
                       json={"statut": "REJETE"}).status_code == 400  # motif obligatoire
    d = client.post(f"/api/plateforme/boutiques/{b['id']}/kyc/decision", headers=super_admin,
                    json={"statut": "VERIFIE"}).json()
    assert d["statut"] == "VERIFIE"
    assert client.get(f"/api/plateforme/boutiques/{b['id']}/kyc/documents/{piece_id}", headers=super_admin).status_code == 200
    # Dossier vérifié : le DG ne retire plus de pièce seul ; changer l'IFU relance la vérification
    assert client.delete(f"/api/boutique/kyc/documents/{piece_id}", headers=h).status_code == 409
    client.patch("/api/boutique", headers=h, json={"ifu": "NOUVEL-IFU"})
    assert client.get("/api/boutique", headers=h).json()["kyc"]["statut"] == "EN_ATTENTE"
    # Réservé au DG / super-admin
    assert client.post(f"/api/plateforme/boutiques/{b['id']}/kyc/decision", headers=h, json={"statut": "VERIFIE"}).status_code == 403
