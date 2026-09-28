"""Sauvegardes chiffrées, restauration, tâches de nuit et historique des paiements."""
import asyncio
import base64
import io
import json

import httpx


def test_historique_des_paiements(client, boutique_equipee):
    a = boutique_equipee
    f = client.post("/api/documents", headers=a["h"], json={"client_id": a["client"]["id"], "lignes": [
        {"produit_id": a["tel"]["id"], "quantite": 1}]}).json()
    client.post(f"/api/documents/{f['id']}/valider", headers=a["h"])
    d = client.post(f"/api/documents/{f['id']}/reglements", headers=a["h"], json={"montant": 40000, "mode": "OM"}).json()
    client.post(f"/api/documents/{f['id']}/reglements", headers=a["h"], json={"montant": 10000, "mode": "ESP"})
    client.delete(f"/api/documents/{f['id']}/reglements/{d['reglements'][0]['id']}", headers=a["h"])
    # Paiement PawaPay échoué (appliqué comme le ferait le rapprochement)
    from db import db
    from routes.paiements import appliquer_statut
    slug = a["boutique"]["slug"]
    cmd = client.post(f"/api/public/b/{slug}/commandes", json={
        "nom": "Payeur", "telephone": "70202020", "lignes": [{"produit_id": a["tel"]["id"], "quantite": 1}]}).json()
    commande = next(c for c in client.get("/api/commandes", headers=a["h"]).json() if c["numero"] == cmd["numero"])
    p = {"deposit_id": "dep-echec", "boutique_id": a["boutique"]["id"], "commande_id": commande["id"],
         "commande_numero": cmd["numero"], "montant": 100000, "devise": "XOF", "statut": "en_attente", "created_at": "2026"}
    client.portal.call(lambda: db.paiements.insert_one(dict(p)))
    client.portal.call(lambda: appliquer_statut(p, {"status": "FAILED", "failureReason": {"failureCode": "INSUFFICIENT_BALANCE"}}))

    h = client.get("/api/journal-paiements", headers=a["h"]).json()
    statuts = sorted((e["mode"], e["statut"]) for e in h["entrees"])
    assert statuts == [("ESP", "SUCCES"), ("MM", "ECHEC"), ("OM", "ANNULE")]
    assert h["total_encaisse"] == 10000 and h["par_statut"]["ECHEC"]["nombre"] == 1
    # Filtres : période et statut
    assert client.get("/api/journal-paiements", headers=a["h"], params={"au": "2000-01-01"}).json()["entrees"] == []
    assert len(client.get("/api/journal-paiements", headers=a["h"], params={"statut": "ECHEC"}).json()["entrees"]) == 1
    csv = client.get("/api/journal-paiements/export.csv", headers=a["h"])
    assert csv.status_code == 200 and "Orange Money" in csv.text and "INSUFFICIENT_BALANCE" in csv.text


def test_sauvegarde_et_restauration(client, super_admin, boutique_equipee, nouvelle_boutique):
    a = boutique_equipee
    bid = a["boutique"]["id"]
    r = client.get(f"/api/plateforme/boutiques/{bid}/sauvegarde", headers=super_admin)
    assert r.status_code == 200 and r.content.startswith(b"TLB1")
    assert b"Client Test" not in r.content  # chiffré : aucune donnée lisible
    archive = r.content
    # Modification après la sauvegarde...
    client.post("/api/clients", headers=a["h"], json={"nom": "Ajouté après", "telephone": "70000001"})
    assert len(client.get("/api/clients", headers=a["h"]).json()) == 2
    fichier = lambda contenu: {"fichier": ("s.tlb.gz.enc", io.BytesIO(contenu), "application/octet-stream")}  # noqa: E731
    # Confirmation obligatoire (code marchand)
    assert client.post(f"/api/plateforme/boutiques/{bid}/restauration", headers=super_admin, files=fichier(archive),
                       data={"confirmation": "NON"}).status_code == 400
    # Fichier modifié : refusé
    abime = archive[:-5] + b"xxxxx"
    assert client.post(f"/api/plateforme/boutiques/{bid}/restauration", headers=super_admin, files=fichier(abime),
                       data={"confirmation": a["boutique"]["code_marchand"]}).status_code == 400
    # Archive d'une autre boutique : refusée
    b, _ = nouvelle_boutique()
    assert client.post(f"/api/plateforme/boutiques/{b['id']}/restauration", headers=super_admin, files=fichier(archive),
                       data={"confirmation": b["code_marchand"]}).status_code == 400
    r = client.post(f"/api/plateforme/boutiques/{bid}/restauration", headers=super_admin, files=fichier(archive),
                    data={"confirmation": a["boutique"]["code_marchand"]})
    assert r.status_code == 200, r.text
    assert [c["nom"] for c in client.get("/api/clients", headers=a["h"]).json()] == ["Client Test"]
    # Les comptes du personnel sont restaurés : le gérant se connecte toujours
    assert client.get("/api/produits", headers=a["h"]).status_code == 200
    # Réservé au super-admin
    assert client.get(f"/api/plateforme/boutiques/{bid}/sauvegarde", headers=a["h"]).status_code == 403


def test_nuit_sans_drive_ni_smtp(client, super_admin, boutique_equipee):
    """Sans Google Drive configuré : chaque sauvegarde est notée en échec et le rapport le dit."""
    r = client.post("/api/plateforme/sauvegardes/lancer", headers=super_admin).json()
    assert r["sauvegardes"] and all(s["statut"] == "ECHEC" for s in r["sauvegardes"])
    assert "non configuré" in r["sauvegardes"][0]["erreur"]
    assert r["rapport"]["statut"] == "NON_ENVOYE"
    h = client.get("/api/plateforme/sauvegardes", headers=super_admin).json()
    assert h["configuration"]["cle_chiffrement"] is True and h["configuration"]["google_drive"] is False
    rapport = client.get(f"/api/plateforme/rapports/{r['rapport']['id']}", headers=super_admin).json()
    assert "SAUVEGARDES DES BOUTIQUES" in rapport["corps"] and "CATALOGUE PUBLIC" in rapport["corps"]


def test_google_drive_envoi():
    """Client Google Drive simulé : jeton, dossiers, envoi multipart, purge."""
    import gdrive

    appels = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        appels.append((requete.method, requete.url.path))
        if requete.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "jeton"})
        if requete.method == "GET":
            return httpx.Response(200, json={"files": [{"id": "vieux"}]} if "createdTime" in str(requete.url) else {"files": []})
        if requete.method == "DELETE":
            return httpx.Response(204)
        if "upload" in requete.url.path:
            assert b"TLB1" in requete.content and requete.headers["Authorization"] == "Bearer jeton"
            return httpx.Response(200, json={"id": "fichier1"})
        corps = json.loads(requete.content)
        return httpx.Response(200, json={"id": f"dossier-{corps['name']}"})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(repondre)) as c:
            d = gdrive.GoogleDrive(c)
            await d.connecter()
            racine = await d.dossier("Sauvegardes")
            sous = await d.dossier("DEMO01 - Démo", racine)
            envoye = await d.envoyer(sous, "s.tlb.gz.enc", b"TLB1...")
            purges = await d.purger(sous, 30)
            return racine, sous, envoye, purges

    racine, sous, envoye, purges = asyncio.run(scenario())
    assert racine == "dossier-Sauvegardes" and sous == "dossier-DEMO01 - Démo"
    assert envoye["id"] == "fichier1" and purges == 1


def test_cle_de_chiffrement():
    import sauvegarde
    assert len(base64.b64decode(sauvegarde.generer_cle())) == 32
