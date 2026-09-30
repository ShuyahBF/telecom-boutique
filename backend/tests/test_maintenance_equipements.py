"""Maintenance des équipements confiés : fonction activable par boutique, fiches
(numéro automatique, client, état, diagnostic, statut reçu -> rendu), types extensibles,
espace de la plateforme (clients = boutiques), photos, envoi WhatsApp, lien de paiement
Mobile Money (PawaPay) et facturation. Base en mémoire, WhatsApp et PawaPay simulés."""
from datetime import date

import httpx
import pytest

from config import get_settings
from db import db

ANNEE = date.today().year
FICHE = {"type_materiel": "Imprimante", "marque_modele": "HP LaserJet 1020", "etat_materiel": "mauvais",
         "motif": "Bourrage papier permanent", "date_reception": "2026-09-29", "date_entree": "2026-09-29"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class _Reponse:
    """Réponse simulée des API externes (WhatsApp accepte, PawaPay renvoie sa page)."""
    status_code = 200
    text = "{}"

    def json(self):
        return {"redirectUrl": "https://pay.exemple/page"}


def _capturer(monkeypatch):
    """Intercepte les appels sortants (Meta, PawaPay) et garde leur corps."""
    envois = []

    async def faux_post(self, url, json=None, headers=None):
        envois.append({"url": url, "json": json})
        return _Reponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)
    return envois


def _activer(client, super_admin, boutique_id, actif=True):
    r = client.patch(f"/api/plateforme/boutiques/{boutique_id}", headers=super_admin, json={"maintenance_equipements": actif})
    assert r.status_code == 200 and r.json()["maintenance_equipements"] is actif
    client.cookies.clear()


@pytest.fixture
def atelier(client, super_admin, boutique_equipee):
    """Boutique équipée dont la fonction « Maintenance des équipements » est activée."""
    _activer(client, super_admin, boutique_equipee["boutique"]["id"])
    return boutique_equipee


def test_fonction_activable_par_l_administrateur(client, super_admin, boutique_equipee):
    h, b = boutique_equipee["h"], boutique_equipee["boutique"]
    r = client.get("/api/maintenance-equipements", headers=h)
    assert r.status_code == 403 and "activation" in r.json()["detail"]
    _activer(client, super_admin, b["id"])
    assert client.get("/api/maintenance-equipements", headers=h).json() == {
        "fiches": [], "compte": {"recu": 0, "diagnostic": 0, "reparation": 0, "pret": 0, "rendu": 0}}
    # Le champ est renvoyé avec la boutique (affichage du menu)
    assert client.get("/api/boutique", headers=h).json()["maintenance_equipements"] is True
    _activer(client, super_admin, b["id"], False)
    assert client.get("/api/maintenance-equipements", headers=h).status_code == 403


def test_fiche_complete_et_cloisonnement(client, super_admin, atelier, nouvelle_boutique, connecter_membre):
    h, b, cli = atelier["h"], atelier["boutique"], atelier["client"]
    base = "/api/maintenance-equipements"
    f = client.post(base, headers=h, json={**FICHE, "client_id": cli["id"]}).json()
    assert f["numero"] == f"MNT-{b['code_marchand']}-{ANNEE}-0001" and f["statut"] == "recu"
    assert f["client_nom"] == "Client Test" and f["client_telephone"] == "70112233"
    assert f["prix_diagnostic"] == 10000  # prix par défaut
    # Client saisi librement, prix du diagnostic et équipe
    f2 = client.post(base, headers=h, json={**FICHE, "client_nom": "M. OUEDRAOGO", "client_telephone": "76 00 00 00",
                                            "type_materiel": "Onduleur", "etat_materiel": "bon",
                                            "prix_diagnostic": 7500, "equipe": "Issa, Awa"}).json()
    assert f2["numero"].endswith("-0002") and f2["prix_diagnostic"] == 7500 and f2["equipe"] == "Issa, Awa"
    # Client obligatoire, état contrôlé, client d'une autre boutique refusé
    assert client.post(base, headers=h, json=FICHE).status_code == 400
    assert client.post(base, headers=h, json={**FICHE, "client_nom": "X", "etat_materiel": "neuf"}).status_code == 422
    assert client.post(base, headers=h, json={**FICHE, "client_id": "inconnu"}).status_code == 400
    # Une boutique ne choisit jamais une boutique comme client
    assert client.post(base, headers=h, json={**FICHE, "boutique_client_id": b["id"]}).status_code == 403

    # Diagnostic, pièces à remplacer, en réparation puis restitution
    corps = {**FICHE, "client_id": cli["id"]}
    maj = client.put(f"{base}/{f['id']}", headers=h, json={
        **corps, "diagnostic": "Rouleau d'entraînement usé", "remplacement_pieces": True,
        "pieces": "Rouleau d'entraînement", "statut": "reparation"}).json()
    assert maj["statut"] == "reparation" and maj["remplacement_pieces"] is True and maj["numero"] == f["numero"]
    assert client.put(f"{base}/{f['id']}", headers=h, json={**corps, "date_sortie": "2026-09-01"}).status_code == 400
    rendu = client.put(f"{base}/{f['id']}", headers=h, json={**corps, "date_sortie": "2026-10-02"}).json()
    assert rendu["statut"] == "rendu"

    # Liste, recherche, filtres
    lst = client.get(base, headers=h, params={"q": "client test"}).json()
    assert [x["numero"] for x in lst["fiches"]] == [f["numero"]] and lst["compte"]["rendu"] == 1
    assert client.get(base, headers=h, params={"statut": "recu"}).json()["fiches"][0]["type_materiel"] == "Onduleur"
    assert len(client.get(base, headers=h, params={"type_materiel": "Imprimante"}).json()["fiches"]) == 1

    # Cloisonnement : une autre boutique (même activée) ne voit rien
    b2, h2 = nouvelle_boutique()
    _activer(client, super_admin, b2["id"])
    assert client.get(base, headers=h2).json()["fiches"] == []
    assert client.get(f"{base}/{f['id']}", headers=h2).status_code == 404
    f3 = client.post(base, headers=h2, json={**FICHE, "client_nom": "Autre"}).json()
    assert f3["numero"] == f"MNT-{b2['code_marchand']}-{ANNEE}-0001"

    # Suppression : réservée au DG (le technicien travaille sur la fiche mais ne la supprime pas)
    client.post("/api/boutique/equipe", headers=h, json={"nom": "Tech Atelier", "email": f"tech-{b['code_marchand']}@test.bf",
                                                         "mot_de_passe": "motdepasse-123", "role": "technicien"})
    ht, _ = connecter_membre(b["code_marchand"], f"tech-{b['code_marchand']}@test.bf")
    assert client.get(f"{base}/{f2['id']}", headers=ht).status_code == 200
    assert client.delete(f"{base}/{f2['id']}", headers=ht).status_code == 403
    assert client.delete(f"{base}/{f2['id']}", headers=h).status_code == 200
    assert client.get(f"{base}/{f2['id']}", headers=h).status_code == 404


def test_types_extensibles_par_espace(client, super_admin, atelier, nouvelle_boutique):
    h = atelier["h"]
    base = "/api/maintenance-equipements/types"
    t = client.get(base, headers=h).json()
    assert "Imprimante" in t["tous"] and t["tous"][-1] == "Autre" and t["prix_diagnostic_defaut"] == 10000
    n = client.post(base, headers=h, json={"libelle": "Vidéoprojecteur"}).json()
    assert client.post(base, headers=h, json={"libelle": "vidéoprojecteur"}).status_code == 409
    assert client.post(base, headers=h, json={"libelle": "imprimante"}).status_code == 409
    t = client.get(base, headers=h).json()
    assert "Vidéoprojecteur" in t["tous"] and t["tous"][-1] == "Autre"
    b2, h2 = nouvelle_boutique()
    _activer(client, super_admin, b2["id"])
    assert "Vidéoprojecteur" not in client.get(base, headers=h2).json()["tous"]
    assert client.delete(f"{base}/{n['id']}", headers=h2).status_code == 404
    assert client.delete(f"{base}/{n['id']}", headers=h).status_code == 200


def test_espace_plateforme_clients_boutiques(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique(dg_telephone="+226 70 99 88 77")
    base = "/api/plateforme/maintenance-equipements"
    # Réservé au super-administrateur
    assert client.get(base, headers=h).status_code == 403
    clients = client.get(f"{base}/clients", headers=super_admin).json()
    assert clients["type"] == "boutique"
    item = next(i for i in clients["items"] if i["id"] == b["id"])
    # Téléphone repris : celui qui reçoit les messages de la plateforme (DG)
    assert item["telephone"] == "+22670998877" and item["code"] == b["code_marchand"]
    f = client.post(base, headers=super_admin, json={**FICHE, "boutique_client_id": b["id"]}).json()
    assert f["numero"].startswith(f"MNT-ADLYN-{ANNEE}-") and f["client_nom"] == b["nom"]
    assert f["client_telephone"] == "+22670998877" and f["boutique_client_id"] == b["id"]
    # Téléphone modifiable, client saisi librement possible
    f2 = client.post(base, headers=super_admin, json={**FICHE, "boutique_client_id": b["id"], "client_telephone": "25 30 30 30"}).json()
    assert f2["client_telephone"] == "25303030"
    assert client.post(base, headers=super_admin, json={**FICHE, "client_nom": "Société X"}).status_code == 201
    # Les fiches de la plateforme ne sont pas visibles des boutiques (même activées)
    _activer(client, super_admin, b["id"])
    assert client.get(f"/api/maintenance-equipements/{f['id']}", headers=h).status_code == 404
    # Facture adLyn imprimable (pas de proforma), une seule fois
    assert client.post(f"{base}/{f['id']}/facturer", headers=super_admin, json={"type_document": "PRO"}).status_code == 400
    fac = client.post(f"{base}/{f['id']}/facturer", headers=super_admin, json={
        "lignes": [{"designation": "Remplacement du rouleau", "quantite": 1, "prix_unitaire": 15000}]}).json()
    assert fac["numero"].startswith(f"FMT-{ANNEE}-") and fac["montant"] == 25000
    assert fac["client"]["code_marchand"] == b["code_marchand"]
    assert client.get(f"{base}/{f['id']}", headers=super_admin).json()["facture"]["numero"] == fac["numero"]
    assert client.post(f"{base}/{f['id']}/facturer", headers=super_admin, json={}).status_code == 409


def test_photos(client, atelier):
    h = atelier["h"]
    base = "/api/maintenance-equipements"
    f = client.post(base, headers=h, json={**FICHE, "client_nom": "Photo"}).json()
    r = client.post(f"{base}/{f['id']}/photos", headers=h, files={"fichier": ("imprimante.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    photo = r.json()
    assert "/maintenance/" in photo["url"] and photo["nom"] == "imprimante.png"
    # Formats et poids contrôlés (ceux de WhatsApp)
    assert client.post(f"{base}/{f['id']}/photos", headers=h, files={"fichier": ("a.webp", PNG, "image/webp")}).status_code == 400
    lourde = b"\xff\xd8\xff" + b"\x00" * (5 * 1024 * 1024)
    assert client.post(f"{base}/{f['id']}/photos", headers=h, files={"fichier": ("a.jpg", lourde, "image/jpeg")}).status_code == 400
    assert len(client.get(f"{base}/{f['id']}", headers=h).json()["photos"]) == 1
    assert client.delete(f"{base}/{f['id']}/photos/{photo['id']}", headers=h).status_code == 200
    assert client.get(f"{base}/{f['id']}", headers=h).json()["photos"] == []


def _brancher_whatsapp(monkeypatch, modele=None, modele_image=None):
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_access_token", "jeton-test")
    monkeypatch.setattr(s, "whatsapp_phone_number_id", "123456")
    monkeypatch.setattr(s, "whatsapp_maintenance_template", modele)
    monkeypatch.setattr(s, "whatsapp_maintenance_template_image", modele_image)


def test_envoi_whatsapp(client, super_admin, atelier, monkeypatch):
    h, b = atelier["h"], atelier["boutique"]
    base = "/api/maintenance-equipements"
    f = client.post(base, headers=h, json={**FICHE, "client_id": atelier["client"]["id"], "diagnostic": "Rouleau usé"}).json()
    url = f"{base}/{f['id']}/whatsapp"
    # WhatsApp non branché sur la plateforme
    assert client.post(url, headers=h, json={}).status_code == 503

    # Sans modèle : message libre (texte de la fiche) puis les photos publiées en https
    _brancher_whatsapp(monkeypatch)
    envois = _capturer(monkeypatch)
    client.post(f"{base}/{f['id']}/photos", headers=h, files={"fichier": ("p.png", PNG, "image/png")})
    client.portal.call(lambda: db.maintenance_fiches.update_one(
        {"id": f["id"]}, {"$set": {"photos.0.url": "https://pub-test.r2.dev/p.png"}}))
    r = client.post(url, headers=h, json={}).json()
    assert r["mode"] == "texte" and r["texte"] is True and r["photos_envoyees"] == 1
    assert envois[0]["json"]["to"] == "22670112233" and envois[0]["json"]["type"] == "text"
    texte = envois[0]["json"]["text"]["body"]
    assert f["numero"] in texte and "Rouleau usé" in texte and "10 000 FCFA" in texte and b["nom"] in texte
    assert envois[1]["json"]["image"]["link"] == "https://pub-test.r2.dev/p.png"

    # Modèle à en-tête image demandé mais non configuré : message clair
    assert client.post(url, headers=h, json={"mode": "modele", "modele": "image"}).status_code == 400
    # Modèles configurés : « auto » choisit le modèle (seul moyen hors fenêtre de 24 h)
    _brancher_whatsapp(monkeypatch, "adlyn_fiche_maintenance", "adlyn_fiche_maintenance_photo")
    envois.clear()
    r = client.post(url, headers=h, json={}).json()
    assert r["mode"] == "modele" and r["photos_non_envoyees"] == 1
    modele = envois[0]["json"]["template"]
    assert modele["name"] == "adlyn_fiche_maintenance"
    valeurs = [p["text"] for p in modele["components"][0]["parameters"]]
    assert valeurs[:2] == [b["nom"], f["numero"]] and valeurs[4] == "10 000 FCFA" and valeurs[5] == "—"
    # Modèle à en-tête image : la 1re photo en en-tête
    envois.clear()
    r = client.post(url, headers=h, json={"modele": "image"}).json()
    assert r["photos_envoyees"] == 1
    assert envois[0]["json"]["template"]["components"][0]["parameters"][0]["image"]["link"] == "https://pub-test.r2.dev/p.png"
    # ... refusé sans photo jointe, avec un message explicite
    r = client.post(url, headers=h, json={"modele": "image", "photos": False})
    assert r.status_code == 400 and "en-tête image" in r.json()["detail"]
    assert len(client.get(f"{base}/{f['id']}", headers=h).json()["envois_whatsapp"]) == 3

    # Boutique de démonstration : rien ne part
    client.patch(f"/api/plateforme/boutiques/{b['id']}", headers=super_admin, json={"test": True})
    client.cookies.clear()
    envois.clear()
    assert client.post(url, headers=h, json={}).json()["non_envoye"] is True and envois == []


def test_lien_de_paiement_et_facture_boutique(client, super_admin, atelier, monkeypatch):
    import routes.paiements as paiements

    h, b = atelier["h"], atelier["boutique"]
    base = "/api/maintenance-equipements"
    f = client.post(base, headers=h, json={**FICHE, "client_id": atelier["client"]["id"]}).json()
    # PawaPay non configuré
    assert client.post(f"{base}/{f['id']}/lien-paiement", headers=h, json={}).status_code == 503
    monkeypatch.setattr(get_settings(), "pawapay_api_token_sandbox", "cle-test")
    monkeypatch.setattr(get_settings(), "pawapay_environment", "sandbox")
    envois = _capturer(monkeypatch)
    # Dossier KYC non validé : pas d'encaissement pour la boutique
    assert client.post(f"{base}/{f['id']}/lien-paiement", headers=h, json={}).status_code == 400
    client.post(f"/api/plateforme/boutiques/{b['id']}/kyc/decision", headers=super_admin, json={"statut": "VERIFIE"})
    client.cookies.clear()
    lien = client.post(f"{base}/{f['id']}/lien-paiement", headers=h, json={}).json()
    assert lien["montant"] == 10000 and lien["url"].endswith(f"/paiement/maintenance/{lien['jeton']}")

    # Facture (brouillon) dans « Factures & proformas » : diagnostic + ligne ajoutée
    fac = client.post(f"{base}/{f['id']}/facturer", headers=h, json={
        "lignes": [{"designation": "Rouleau d'entraînement", "quantite": 1, "prix_unitaire": 5000}]}).json()
    doc = client.get(f"/api/documents/{fac['id']}", headers=h).json()
    assert doc["type_document"] == "FAC" and doc["client_id"] == atelier["client"]["id"] and len(doc["lignes"]) == 2
    assert doc["fiche_maintenance_origine"]["numero"] == f["numero"]
    assert client.post(f"{base}/{f['id']}/facturer", headers=h, json={}).status_code == 409
    assert client.post(f"{base}/{f['id']}/facturer", headers=h, json={"type_document": "PRO"}).status_code == 200

    # Page publique du lien : informations sans donnée confidentielle, puis page PawaPay
    info = client.get(f"/api/public/maintenance-paiement/{lien['jeton']}").json()
    assert info == {"numero": f["numero"], "emetteur": b["nom"], "client_nom": "Client Test",
                    "materiel": "Imprimante HP LaserJet 1020", "montant": 10000, "devise": "FCFA", "paye": False,
                    "disponible": True}
    assert client.get("/api/public/maintenance-paiement/jeton-inconnu-0123456789").status_code == 404
    r = client.post(f"/api/public/maintenance-paiement/{lien['jeton']}", json={"telephone": "70112233"})
    assert r.status_code == 200 and r.json()["url"] == "https://pay.exemple/page"
    corps = envois[-1]["json"]
    assert corps["amountDetails"]["amount"] == "10000"
    meta = {k: v for m in corps["metadata"] for k, v in m.items()}
    assert meta["typePaiement"] == "maintenance" and meta["ficheNumero"] == f["numero"] and meta["boutiqueId"] == b["id"]

    # PawaPay confirme : fiche payée, règlement sur la facture, historique et reversements de la boutique
    paiement = client.portal.call(lambda: db.paiements.find_one({"fiche_id": f["id"]}, {"_id": 0}))
    client.portal.call(paiements.appliquer_statut, paiement, {"status": "COMPLETED", "amount": "10000"})
    fiche = client.get(f"{base}/{f['id']}", headers=h).json()
    assert fiche["lien_paiement"]["paye"] is True and fiche["lien_paiement"]["statut"] == "PAYE"
    assert client.get(f"/api/documents/{fac['id']}", headers=h).json()["reglements"][0]["mode"] == "MM"
    journal = client.get("/api/journal-paiements", headers=h).json()["entrees"]
    assert any(e["objet"] == f"Maintenance {f['numero']}" and e["statut"] == "SUCCES" for e in journal)
    rev = client.get("/api/reversements", headers=h).json()
    assert rev["situation"]["a_reverser"] == 10000 and rev["paiements"][0]["fiche_numero"] == f["numero"]
    # Payé : plus de nouveau paiement ni de suppression
    assert client.get(f"/api/public/maintenance-paiement/{lien['jeton']}").json()["paye"] is True
    assert client.post(f"/api/public/maintenance-paiement/{lien['jeton']}", json={}).status_code == 409
    assert client.post(f"{base}/{f['id']}/lien-paiement", headers=h, json={}).status_code == 409
    assert client.delete(f"{base}/{f['id']}", headers=h).status_code == 409


def test_lien_de_paiement_plateforme(client, super_admin, nouvelle_boutique, monkeypatch):
    import routes.paiements as paiements

    b, h = nouvelle_boutique()
    base = "/api/plateforme/maintenance-equipements"
    monkeypatch.setattr(get_settings(), "pawapay_api_token_sandbox", "cle-test")
    envois = _capturer(monkeypatch)
    f = client.post(base, headers=super_admin, json={**FICHE, "boutique_client_id": b["id"], "prix_diagnostic": 20000}).json()
    # Argent dû à adLyn : aucun dossier KYC exigé ; montant personnalisé possible
    lien = client.post(f"{base}/{f['id']}/lien-paiement", headers=super_admin, json={"montant": 15000}).json()
    assert lien["montant"] == 15000
    assert client.get(f"/api/public/maintenance-paiement/{lien['jeton']}").json()["emetteur"] == "adLyn"
    client.post(f"/api/public/maintenance-paiement/{lien['jeton']}", json={})
    meta = {k: v for m in envois[-1]["json"]["metadata"] for k, v in m.items()}
    assert meta["typePaiement"] == "maintenance_plateforme" and meta["boutiqueId"] == b["id"]
    paiement = client.portal.call(lambda: db.paiements.find_one({"fiche_id": f["id"]}, {"_id": 0}))
    client.portal.call(paiements.appliquer_statut, paiement, {"status": "COMPLETED", "amount": "15000"})
    assert client.get(f"{base}/{f['id']}", headers=super_admin).json()["lien_paiement"]["paye"] is True
    # Jamais reversé à la boutique cliente
    assert client.get("/api/reversements", headers=h).json()["situation"]["encaisse"] == 0
