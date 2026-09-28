"""Tests de bout en bout des règles métier et du cloisonnement multi-boutiques.
Lancement : cd backend && python -m pytest tests -q"""
from datetime import date

from utils import montant_en_lettres, nombre_en_lettres

ANNEE = date.today().year


def stock(client, h, produit_id):
    return client.get(f"/api/produits/{produit_id}", headers=h).json()["stock"]


# ---------------------------------------------------------------------------
# Multi-tenant : une boutique ne voit JAMAIS les données d'une autre
# ---------------------------------------------------------------------------
def test_cloisonnement_entre_boutiques(client, boutique_equipee, nouvelle_boutique):
    a = boutique_equipee
    b, hb = nouvelle_boutique()
    assert client.get("/api/produits?source=boutique", headers=hb).json() == []
    assert client.get(f"/api/produits/{a['tel']['id']}", headers=hb).status_code == 404
    assert client.get("/api/clients", headers=hb).json() == []
    # L'en-tête X-Boutique-Id est IGNORÉ pour un gérant (seul le super-admin peut choisir)
    r = client.get("/api/produits?source=boutique", headers={**hb, "X-Boutique-Id": a["boutique"]["id"]})
    assert r.json() == []
    # Même référence autorisée dans deux boutiques différentes
    cat = client.post("/api/categories", headers=hb, json={"nom": "Tel"}).json()
    r = client.post("/api/produits", headers=hb, json={"reference": "T1", "nom": "Autre", "categorie_id": cat["id"],
                                                        "prix_vente": 1})
    assert r.status_code == 201


def test_super_admin_choisit_la_boutique(client, super_admin, boutique_equipee):
    a = boutique_equipee
    assert client.get("/api/produits", headers=super_admin).status_code == 400
    r = client.get("/api/produits?source=boutique", headers={**super_admin, "X-Boutique-Id": a["boutique"]["id"]})
    assert len(r.json()) == 2


def test_numerotation_propre_a_chaque_boutique(client, boutique_equipee, nouvelle_boutique):
    a = boutique_equipee
    _, hb = nouvelle_boutique()
    cli_b = client.post("/api/clients", headers=hb, json={"nom": "X", "telephone": "76000000"}).json()
    p1 = client.post("/api/documents", headers=a["h"], json={"type_document": "PRO", "client_id": a["client"]["id"]}).json()
    p2 = client.post("/api/documents", headers=a["h"], json={"type_document": "PRO", "client_id": a["client"]["id"]}).json()
    pb = client.post("/api/documents", headers=hb, json={"type_document": "PRO", "client_id": cli_b["id"]}).json()
    assert p1["numero"] == f"PRO-{ANNEE}-00001"
    assert p2["numero"] == f"PRO-{ANNEE}-00002"
    assert pb["numero"] == f"PRO-{ANNEE}-00001"
    # Un client d'une autre boutique est refusé
    r = client.post("/api/documents", headers=hb, json={"type_document": "PRO", "client_id": a["client"]["id"]})
    assert r.status_code == 400


def test_roles(client, boutique_equipee):
    a = boutique_equipee
    r = client.post("/api/boutique/equipe", headers=a["h"], json={
        "nom": "Tech", "email": "tech@test.bf", "mot_de_passe": "motdepasse-123", "role": "technicien"})
    assert r.status_code == 201
    tok = client.post("/api/auth/login", json={"email": "tech@test.bf", "password": "motdepasse-123"}).json()["access_token"]
    ht = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/maintenance", headers=ht).status_code == 200
    assert client.post("/api/documents", headers=ht, json={"client_id": a["client"]["id"]}).status_code == 403
    assert client.patch("/api/boutique", headers=ht, json={"slogan": "x"}).status_code == 403
    assert client.get("/api/plateforme/boutiques", headers=a["h"]).status_code == 403


# ---------------------------------------------------------------------------
# Factures / proformas
# ---------------------------------------------------------------------------
def _facture(client, a, qte=2):
    return client.post("/api/documents", headers=a["h"], json={
        "type_document": "FAC", "client_id": a["client"]["id"], "prix_ttc": False, "lignes": [
            {"produit_id": a["tel"]["id"], "quantite": qte, "remise_pct": 10, "taux_tva": 18},
            {"designation": "Configuration", "quantite": 1, "prix_unitaire": 2000, "taux_tva": 0},
        ]}).json()


def test_totaux_multi_lignes(client, boutique_equipee):
    f = _facture(client, boutique_equipee)
    # 2 x 100 000 - 10 % = 180 000 HT ; TVA 18 % = 32 400 ; + ligne libre 2 000
    assert (f["total_ht"], f["total_tva"], f["total_ttc"]) == (182000, 32400, 214400)
    assert f["numero"] is None and f["statut"] == "BROUILLON"
    assert f["total_en_lettres"] == "Deux cent quatorze mille quatre cents FCFA"


def test_validation_destocke_et_numerote(client, boutique_equipee):
    a = boutique_equipee
    f = _facture(client, a)
    r = client.post(f"/api/documents/{f['id']}/valider", headers=a["h"]).json()
    assert r["numero"] == f"FAC-{ANNEE}-00001" and r["statut"] == "VALIDE"
    assert stock(client, a["h"], a["tel"]["id"]) == 3
    # Plus modifiable, ni supprimable, ni validable une 2e fois
    assert client.put(f"/api/documents/{f['id']}", headers=a["h"], json={"client_id": a["client"]["id"]}).status_code == 409
    assert client.delete(f"/api/documents/{f['id']}", headers=a["h"]).status_code == 409
    assert client.post(f"/api/documents/{f['id']}/valider", headers=a["h"]).status_code == 409
    assert stock(client, a["h"], a["tel"]["id"]) == 3


def test_validation_refusee_si_stock_insuffisant(client, boutique_equipee):
    a = boutique_equipee
    f = _facture(client, a, qte=50)
    r = client.post(f"/api/documents/{f['id']}/valider", headers=a["h"])
    assert r.status_code == 409
    doc = client.get(f"/api/documents/{f['id']}", headers=a["h"]).json()
    assert doc["statut"] == "BROUILLON" and doc["numero"] is None
    assert stock(client, a["h"], a["tel"]["id"]) == 5
    # Aucun numéro consommé : la facture suivante prend bien le n°1
    f2 = _facture(client, a, qte=1)
    assert client.post(f"/api/documents/{f2['id']}/valider", headers=a["h"]).json()["numero"] == f"FAC-{ANNEE}-00001"


def test_annulation_reintegre_le_stock(client, boutique_equipee):
    a = boutique_equipee
    f = _facture(client, a)
    client.post(f"/api/documents/{f['id']}/valider", headers=a["h"])
    r = client.post(f"/api/documents/{f['id']}/annuler", headers=a["h"]).json()
    assert r["statut"] == "ANNULE"
    assert stock(client, a["h"], a["tel"]["id"]) == 5


def test_conversion_proforma(client, boutique_equipee):
    a = boutique_equipee
    pro = client.post("/api/documents", headers=a["h"], json={
        "type_document": "PRO", "client_id": a["client"]["id"], "lignes": [
            {"produit_id": a["tel"]["id"], "quantite": 1}, {"produit_id": a["service"]["id"], "quantite": 1}]}).json()
    assert pro["date_echeance"]  # validité par défaut (15 jours)
    fac = client.post(f"/api/documents/{pro['id']}/convertir", headers=a["h"]).json()
    assert fac["type_document"] == "FAC" and len(fac["lignes"]) == 2
    assert fac["total_ttc"] == pro["total_ttc"]
    assert fac["proforma_origine"]["numero"] == pro["numero"]
    assert client.post(f"/api/documents/{pro['id']}/convertir", headers=a["h"]).status_code == 409


def test_prix_ttc_par_defaut(client, boutique_equipee):
    """Par défaut, le prix catalogue est un prix TTC : la TVA en est extraite."""
    a = boutique_equipee
    f = client.post("/api/documents", headers=a["h"], json={
        "client_id": a["client"]["id"], "lignes": [{"produit_id": a["tel"]["id"], "quantite": 1}]}).json()
    assert f["prix_ttc"] is True
    assert (f["total_ht"], f["total_tva"], f["total_ttc"]) == (84746, 15254, 100000)


def test_reglements(client, boutique_equipee):
    a = boutique_equipee
    f = _facture(client, a, qte=1)
    r = client.post(f"/api/documents/{f['id']}/reglements", headers=a["h"], json={"montant": 50000, "mode": "OM"}).json()
    assert r["statut_paiement"] == "Partiellement payée" and r["reste_a_payer"] == f["total_ttc"] - 50000


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------
def test_bon_entree_valide_une_seule_fois(client, boutique_equipee):
    a = boutique_equipee
    four = client.post("/api/fournisseurs", headers=a["h"], json={"nom": "Fourn"}).json()
    bon = client.post("/api/stock/bons", headers=a["h"], json={
        "fournisseur_id": four["id"], "lignes": [{"produit_id": a["tel"]["id"], "quantite": 10, "prix_achat": 75000}]}).json()
    assert bon["numero"] == f"BE-{ANNEE}-00001"
    assert client.post(f"/api/stock/bons/{bon['id']}/valider", headers=a["h"]).status_code == 200
    assert client.post(f"/api/stock/bons/{bon['id']}/valider", headers=a["h"]).status_code == 409
    p = client.get(f"/api/produits/{a['tel']['id']}", headers=a["h"]).json()
    assert p["stock"] == 15 and p["prix_achat"] == 75000


def test_sortie_manuelle_limitee_au_stock(client, boutique_equipee):
    a = boutique_equipee
    r = client.post("/api/stock/mouvements", headers=a["h"], json={"produit_id": a["tel"]["id"], "sens": "S", "quantite": 99, "motif": "CASSE"})
    assert r.status_code == 409
    r = client.post("/api/stock/mouvements", headers=a["h"], json={"produit_id": a["tel"]["id"], "sens": "S", "quantite": 1, "motif": "CASSE"})
    assert r.status_code == 201
    assert stock(client, a["h"], a["tel"]["id"]) == 4
    mouvements = client.get("/api/stock/mouvements", headers=a["h"]).json()
    assert [m["motif"] for m in mouvements][:2] == ["CASSE", "INVENT"]


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------
def test_dossier_maintenance_complet(client, boutique_equipee):
    a = boutique_equipee
    cat = a["cat"]
    piece = client.post("/api/produits", headers=a["h"], json={
        "reference": "P1", "nom": "Écran", "type_produit": "PIE", "categorie_id": cat["id"], "prix_vente": 20000,
        "stock_initial": 3}).json()
    d = client.post("/api/maintenance", headers=a["h"], json={
        "client_id": a["client"]["id"], "marque": "Tecno", "modele": "Camon", "panne_declaree": "Écran cassé",
        "code_deverrouillage": "1234", "devis_montant": 10000, "acompte": 5000}).json()
    assert d["numero"] == f"MNT-{ANNEE}-00001" and len(d["code_suivi"]) == 6
    d = client.post(f"/api/maintenance/{d['id']}/pieces", headers=a["h"], json={"produit_id": piece["id"]}).json()
    assert stock(client, a["h"], piece["id"]) == 2
    d = client.post(f"/api/maintenance/{d['id']}/statut", headers=a["h"], json={"statut": "REPARATION", "commentaire": "Pièce reçue"}).json()
    assert [h["statut"] for h in d["historique"]] == ["RECU", "REPARATION"]
    fac = client.post(f"/api/maintenance/{d['id']}/facture", headers=a["h"]).json()
    assert fac["total_ttc"] == 30000 and fac["total_regle"] == 5000
    # Les pièces (déjà déstockées) ne sont pas déstockées une 2e fois à la validation
    client.post(f"/api/documents/{fac['id']}/valider", headers=a["h"])
    assert stock(client, a["h"], piece["id"]) == 2
    # Retirer une pièce la remet en stock
    client.delete(f"/api/maintenance/{d['id']}/pieces/{d['pieces'][0]['id']}", headers=a["h"])
    assert stock(client, a["h"], piece["id"]) == 3


# ---------------------------------------------------------------------------
# Portail public
# ---------------------------------------------------------------------------
def test_annuaire_et_recherche(client, nouvelle_boutique):
    b, _ = nouvelle_boutique(nom="Galaxy Phone Center", code_marchand="gpc-226")
    noms = [x["nom"] for x in client.get("/api/public/boutiques", params={"q": "galaxy"}).json()]
    assert "Galaxy Phone Center" in noms
    par_code = client.get("/api/public/boutiques", params={"q": "GPC226"}).json()
    assert [x["slug"] for x in par_code] == [b["slug"]]
    assert "messagerie" not in par_code[0]  # jamais les réglages privés
    assert client.get(f"/api/public/b/{b['slug']}").status_code == 200
    assert client.get("/api/public/b/GPC226").json()["id"] == b["id"]  # accès par code (QR / saisie)


def test_boutique_suspendue_invisible(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique()
    client.patch(f"/api/plateforme/boutiques/{b['id']}", headers=super_admin, json={"actif": False})
    assert client.get(f"/api/public/b/{b['slug']}").status_code == 404
    assert client.get("/api/produits", headers=h).status_code == 403


def test_commande_publique_et_suivi(client, boutique_equipee):
    a = boutique_equipee
    slug = a["boutique"]["slug"]
    produits = client.get(f"/api/public/b/{slug}/produits").json()
    tel = next(p for p in produits["produits"] if p["reference"] == "T1")
    assert "prix_achat" not in tel and tel["disponible"]
    r = client.post(f"/api/public/b/{slug}/commandes", json={
        "nom": "Nouveau Client", "telephone": "+226 71 00 00 01",
        "lignes": [{"produit_id": tel["id"], "quantite": 2}]})
    assert r.status_code == 201, r.text
    cmd = r.json()
    assert cmd["total"] == 200000 and cmd["redirect_url"] is None
    ok = client.get(f"/api/public/b/{slug}/commandes/suivi", params={"numero": cmd["numero"], "telephone": "+226 71 00 00 01"})
    assert ok.status_code == 200 and ok.json()["statut"] == "RECUE"
    assert client.get(f"/api/public/b/{slug}/commandes/suivi", params={"numero": cmd["numero"], "telephone": "70000000"}).status_code == 404
    # Stock insuffisant refusé
    r = client.post(f"/api/public/b/{slug}/commandes", json={"nom": "X Y", "telephone": "70000000",
                                                              "lignes": [{"produit_id": tel["id"], "quantite": 99}]})
    assert r.status_code == 409
    # Côté personnel : changement de statut + facture
    commande = client.get("/api/commandes", headers=a["h"]).json()[0]
    client.post(f"/api/commandes/{commande['id']}/statut", headers=a["h"], json={"statut": "CONFIRMEE"})
    fac = client.post(f"/api/commandes/{commande['id']}/facture", headers=a["h"]).json()
    assert fac["total_ttc"] == 200000  # prix payé par le client = TTC
    assert client.post(f"/api/commandes/{commande['id']}/facture", headers=a["h"]).status_code == 409


def test_produit_d_une_autre_boutique_refuse_au_panier(client, boutique_equipee, nouvelle_boutique):
    a = boutique_equipee
    b, _ = nouvelle_boutique()
    r = client.post(f"/api/public/b/{b['slug']}/commandes", json={
        "nom": "Pirate", "telephone": "70000000", "lignes": [{"produit_id": a["tel"]["id"], "quantite": 1}]})
    assert r.status_code == 400


def test_suivi_reparation_public(client, boutique_equipee):
    a = boutique_equipee
    slug = a["boutique"]["slug"]
    d = client.post("/api/maintenance", headers=a["h"], json={
        "client_id": a["client"]["id"], "marque": "Tecno", "modele": "Z", "panne_declaree": "x", "code_deverrouillage": "9999"}).json()
    url = f"/api/public/b/{slug}/maintenance/suivi"
    par_tel = client.get(url, params={"numero": d["numero"], "secret": "70 11 22 33"})
    assert par_tel.status_code == 200 and "code_deverrouillage" not in par_tel.json()
    assert client.get(url, params={"numero": d["numero"], "secret": d["code_suivi"].lower()}).status_code == 200
    assert client.get(url, params={"numero": d["numero"], "secret": "123456789"}).status_code == 404


def test_demande_conseil_et_reponse(client, boutique_equipee):
    a = boutique_equipee
    slug = a["boutique"]["slug"]
    jeton = client.post(f"/api/public/b/{slug}/conseils", json={
        "nom": "Ali", "telephone": "70998877", "sujet": "Quel téléphone ?", "texte": "Budget 100 000"}).json()["jeton"]
    conv = client.get("/api/conversations", headers=a["h"]).json()[0]
    assert conv["non_lus"] == 1
    client.post(f"/api/conversations/{conv['id']}/repondre", headers=a["h"], json={"texte": "Le Galaxy A15 !"})
    fil = client.get(f"/api/public/b/{slug}/conseils/{jeton}").json()
    assert [m["auteur_type"] for m in fil["messages"]] == ["CLIENT", "EQUIPE"]
    assert fil["statut"] == "REPONDU"
    # Le jeton d'une boutique ne fonctionne pas sur une autre
    assert client.get(f"/api/public/b/inexistante/conseils/{jeton}").status_code == 404


# ---------------------------------------------------------------------------
# Paiement PawaPay (statut appliqué une seule fois, montant contrôlé)
# ---------------------------------------------------------------------------
def test_paiement_pawapay_applique(client, boutique_equipee):
    from db import db
    from routes.paiements import appliquer_statut

    a = boutique_equipee
    slug = a["boutique"]["slug"]
    tel_id = a["tel"]["id"]
    cmd = client.post(f"/api/public/b/{slug}/commandes", json={
        "nom": "Payeur", "telephone": "70101010", "lignes": [{"produit_id": tel_id, "quantite": 1}]}).json()
    commande = next(c for c in client.get("/api/commandes", headers=a["h"]).json() if c["numero"] == cmd["numero"])
    paiement = {"deposit_id": "dep-1", "boutique_id": a["boutique"]["id"], "commande_id": commande["id"],
                "commande_numero": cmd["numero"], "montant": 100000, "statut": "en_attente", "created_at": "2026"}
    client.portal.call(lambda: db.paiements.insert_one(dict(paiement)))
    # Montant différent : rien n'est validé
    r = client.portal.call(lambda: appliquer_statut(paiement, {"status": "COMPLETED", "amount": "50000"}))
    assert r["ok"] is False
    client.portal.call(lambda: db.paiements.update_one({"deposit_id": "dep-1"}, {"$set": {"statut": "en_attente"}}))
    r1 = client.portal.call(lambda: appliquer_statut(paiement, {"status": "COMPLETED", "amount": "100000"}))
    r2 = client.portal.call(lambda: appliquer_statut(paiement, {"status": "COMPLETED", "amount": "100000"}))
    assert r1["applique"] is True and r2["applique"] is False  # idempotent
    commande = client.get(f"/api/commandes/{commande['id']}", headers=a["h"]).json()
    assert commande["paiement"]["statut"] == "PAYEE"
    fac = client.post(f"/api/commandes/{commande['id']}/facture", headers=a["h"]).json()
    assert fac["statut_paiement"] == "Payée"
    assert client.get("/api/paiements/dep-1").json()["statut"] == "paye"


def test_mobile_money_indisponible_sans_cle(client, boutique_equipee):
    a = boutique_equipee
    slug = a["boutique"]["slug"]
    assert client.get(f"/api/public/b/{slug}").json()["paiement_mobile_money"] is False
    r = client.post(f"/api/public/b/{slug}/commandes", json={
        "nom": "X Y", "telephone": "70000000", "mode_paiement": "MOBILE_MONEY",
        "lignes": [{"produit_id": a["tel"]["id"], "quantite": 1}]})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Messagerie et utilitaires
# ---------------------------------------------------------------------------
def test_messagerie_parametrable(client, boutique_equipee):
    a = boutique_equipee
    modeles = client.get("/api/boutique/messagerie/modeles", headers=a["h"]).json()
    assert {m["code"] for m in modeles} >= {"CMD_RECUE", "MAINT_STATUT"}
    client.put("/api/boutique/messagerie/modeles/MAINT_DEPOT", headers=a["h"],
               json={"sujet": "Dossier {{ dossier.numero }} chez {{ boutique.nom }}", "corps": "Code {{ dossier.code_suivi }}", "actif": True})
    r = client.put("/api/boutique/messagerie", headers=a["h"], json={"email_actif": False, "smtp_hote": "smtp.test",
                                                                      "smtp_mot_de_passe": "secret"})
    assert r.json()["a_mot_de_passe"] is True and "smtp_mot_de_passe" not in r.json()
    d = client.post("/api/maintenance", headers=a["h"], json={
        "client_id": a["client"]["id"], "marque": "A", "modele": "B", "panne_declaree": "x"}).json()
    import time
    time.sleep(0.2)  # l'envoi se fait en tâche de fond
    journal = client.get("/api/boutique/messagerie/journal", headers=a["h"]).json()
    envoi = next(j for j in journal if j["code"] == "MAINT_DEPOT")
    assert envoi["sujet"] == f"Dossier {d['numero']} chez {a['boutique']['nom']}"
    assert envoi["statut"] == "NON_ENVOYE"  # e-mail désactivé : seulement journalisé


def test_montant_en_lettres():
    assert nombre_en_lettres(71) == "soixante et onze"
    assert nombre_en_lettres(80) == "quatre-vingts"
    assert nombre_en_lettres(200000) == "deux cent mille"
    assert nombre_en_lettres(80000) == "quatre-vingt mille"
    assert nombre_en_lettres(1250500) == "un million deux cent cinquante mille cinq cents"
    assert montant_en_lettres(214400) == "Deux cent quatorze mille quatre cents FCFA"


def test_tableau_de_bord(client, boutique_equipee):
    a = boutique_equipee
    f = _facture(client, a, qte=1)
    client.post(f"/api/documents/{f['id']}/valider", headers=a["h"])
    tdb = client.get("/api/tableau-de-bord", headers=a["h"]).json()
    assert tdb["ca_mois_ht"] == f["total_ht"] and tdb["nb_factures_mois"] == 1
    assert len(tdb["ventes_30_jours"]) == 30
