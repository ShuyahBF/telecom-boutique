"""Cycle de vie du non-renouvellement (J+103 / J+110 / J+112 / J+113) : calendrier,
suspension, archive chiffrée vérifiée sur R2 puis suppression, échec de vérification sans
suppression + alerte, simulation sans effet, avertissements uniques, conservation et
effacement des archives, réouverture (frais, restauration limitée à la boutique),
exclusion des boutiques de test. R2 et les envois (WhatsApp / SMS / e-mail) sont SIMULÉS."""
from datetime import date, timedelta

import pytest

import cycle_vie
import envois_plateforme
import export_boutique
import sauvegarde_auto
import transfert_donnees
from abonnements import aujourd_hui
from config import get_settings
from db import db

AUJ = aujourd_hui()
PHRASE = "phrase de sauvegarde automatique de test"
JETON = "jeton-de-test-cycle-vie"


class FauxR2:
    """Bucket R2 en mémoire ; `alterer` abîme la copie relue (échec de vérification)."""

    def __init__(self):
        self.fichiers: dict[str, bytes] = {}
        self.alterer = False

    async def envoyer(self, cle, chemin):
        with open(chemin, "rb") as f:
            self.fichiers[cle] = f.read()

    async def lister(self, prefixe):
        return [{"cle": c, "taille": len(v), "date": None} for c, v in self.fichiers.items() if c.startswith(prefixe)]

    async def supprimer(self, cle):
        self.fichiers.pop(cle, None)

    async def telecharger(self, cle, chemin):
        contenu = self.fichiers[cle]
        if self.alterer:
            contenu = contenu[:-40] + bytes(40)  # fin du fichier modifiée
        with open(chemin, "wb") as f:
            f.write(contenu)


@pytest.fixture
def cv(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sauvegarde_auto_phrase", PHRASE)
    monkeypatch.setattr(s, "sauvegarde_auto_jeton", JETON)
    monkeypatch.setattr(s, "rapport_email", "proprietaire@test.bf")
    r2 = FauxR2()
    monkeypatch.setattr(sauvegarde_auto, "stockage", lambda: r2)
    monkeypatch.setattr(sauvegarde_auto, "r2_configure", lambda: True)
    envois = {"whatsapp": [], "sms": [], "email": []}

    async def wa(telephone, variables, texte, **kw):
        envois["whatsapp"].append((telephone, texte))
        return "ENVOYE", ""

    async def sms(telephone, texte):
        envois["sms"].append((telephone, texte))
        return "ENVOYE", ""

    async def email(sujet, corps, destinataire):
        envois["email"].append((sujet, corps, destinataire))
        return "ENVOYE", ""

    monkeypatch.setattr(envois_plateforme, "envoyer_whatsapp", wa)
    monkeypatch.setattr(envois_plateforme, "envoyer_sms", sms)
    monkeypatch.setattr(envois_plateforme, "envoyer_email", email)
    client.portal.call(lambda: db.parametres_plateforme.delete_many({"_id": cycle_vie.ID_PARAMETRES}))
    yield {"r2": r2, "envois": envois}
    client.portal.call(lambda: db.parametres_plateforme.delete_many({"_id": cycle_vie.ID_PARAMETRES}))
    client.portal.call(lambda: db.verrous.delete_many({"_id": {"$regex": "^cycle-vie-"}}))


def fixer_echeance(client, super_admin, b, jours):
    r = client.patch(f"/api/plateforme/abonnements/boutiques/{b['id']}", headers=super_admin,
                     json={"echeance": (AUJ + timedelta(days=jours)).isoformat()})
    assert r.status_code == 200, r.text


def executer(client, jour=None, simulation=None):
    return client.portal.call(lambda: cycle_vie.executer(jour, "test", simulation))


def actions_de(rapport, b):
    return [(a["action"], a["statut"]) for a in rapport["actions"] if a["boutique_id"] == b["id"]]


def fiche(client, b):
    return client.portal.call(lambda: db.boutiques.find_one({"id": b["id"]}, {"_id": 0}))


def compter(client, collection, b):
    return client.portal.call(lambda: db[collection].count_documents({"boutique_id": b["id"]}))


def dg_email(client, b):
    return client.portal.call(lambda: db.users.find_one({"boutique_id": b["id"], "role": "dg"}))["email"]


# ---------------------------------------------------------------------------
# Calendrier (fonction pure)
# ---------------------------------------------------------------------------
def test_calendrier_103_110_112_113():
    echeance = date(2026, 1, 1)
    b = {"id": "x", "abonnement": {"echeance": echeance.isoformat()}}
    j = lambda n: echeance + timedelta(days=n)  # noqa: E731
    cal = cycle_vie.calendrier(b, j(0))
    assert (cal["avertissement_le"], cal["suspension_le"], cal["dernier_avis_le"], cal["archivage_le"]) == (
        j(103).isoformat(), j(110).isoformat(), j(112).isoformat(), j(113).isoformat())
    assert cycle_vie.actions_dues(b, j(102)) == []
    assert cycle_vie.actions_dues(b, j(103)) == ["AVERTISSEMENT_J103"]
    marques = {"echeance": echeance.isoformat(), "avertissements": {"J103": {"jour": j(103).isoformat()}}}
    b["cycle_vie"] = marques
    assert cycle_vie.actions_dues(b, j(105)) == []  # déjà averti
    assert cycle_vie.actions_dues(b, j(110)) == ["SUSPENSION"]
    # Suspendue (J+110) et avertie : rien à J+111, dernier avis à J+112
    b.update({"actif": False, "suspension": {"motif": "NON_RENOUVELE"}})
    marques.update({"suspendu_le": "x", "statut": cycle_vie.STATUT_SUSPENDU})
    marques["avertissements"]["J110"] = {"jour": j(110).isoformat()}
    assert cycle_vie.actions_dues(b, j(111)) == []
    assert cycle_vie.actions_dues(b, j(112)) == ["AVERTISSEMENT_J112"]
    marques["avertissements"]["J112"] = {"jour": j(113).isoformat()}  # dernier avis envoyé en retard (J+113)
    assert cycle_vie.actions_dues(b, j(113)) == []  # jamais d'archivage le jour même du dernier avis
    assert cycle_vie.actions_dues(b, j(114)) == ["ARCHIVAGE"]
    # Suspension levée à la main : cycle en pause
    b.update({"actif": True, "suspension": None})
    assert cycle_vie.actions_dues(b, j(120)) == []
    assert cycle_vie.calendrier(b, j(120))["etape"] == "EN_PAUSE"
    # Une nouvelle échéance (paiement) remet tout à zéro
    b["abonnement"]["echeance"] = j(130).isoformat()
    assert cycle_vie.cycle(b) == {} and cycle_vie.actions_dues(b, j(140)) == []
    # Boutique de test : jamais
    assert cycle_vie.actions_dues({**b, "test": True, "abonnement": {"echeance": echeance.isoformat()}}, j(200)) == []


# ---------------------------------------------------------------------------
# Avertissements, suspension
# ---------------------------------------------------------------------------
def test_avertissement_j103_une_seule_fois(client, super_admin, nouvelle_boutique, cv):
    b, h = nouvelle_boutique()
    fixer_echeance(client, super_admin, b, -103)
    assert actions_de(executer(client), b) == [("AVERTISSEMENT_J103", "FAIT")]
    assert len([t for _, t in cv["envois"]["whatsapp"] if b["nom"] in t]) == 1
    assert any(b["nom"] in sujet for sujet, _, dest in cv["envois"]["email"] if dest.startswith("gerant"))
    # Deuxième passage (même jour ou les jours suivants) : rien de plus
    assert actions_de(executer(client), b) == []
    assert actions_de(executer(client, AUJ + timedelta(days=2)), b) == []
    assert len([t for _, t in cv["envois"]["whatsapp"] if b["nom"] in t]) == 1
    journal = client.portal.call(lambda: db.cycle_vie_journal.count_documents(
        {"boutique_id": b["id"], "action": "AVERTISSEMENT_J103"}))
    assert journal == 1
    assert fiche(client, b)["actif"] is True
    # Le rapport quotidien part au super-administrateur
    assert any("Cycle de vie" in sujet and dest == "proprietaire@test.bf" for sujet, _, dest in cv["envois"]["email"])


def test_suspension_j110(client, super_admin, nouvelle_boutique, cv):
    b, h = nouvelle_boutique()
    fixer_echeance(client, super_admin, b, -110)
    assert client.get(f"/api/public/b/{b['slug']}").status_code == 200
    assert actions_de(executer(client), b) == [("SUSPENSION", "FAIT")]
    f = fiche(client, b)
    assert f["actif"] is False and f["suspension"]["motif"] == "NON_RENOUVELE"
    assert f["cycle_vie"]["statut"] == "SUSPENDU_NON_RENOUVELE" and "J110" in f["cycle_vie"]["avertissements"]
    # Plus aucun accès pour le personnel, même la page Abonnement ; vitrine fermée
    for url in ("/api/produits", "/api/boutique/abonnement"):
        r = client.get(url, headers=h)
        assert r.status_code == 403 and "suspendue" in r.json()["detail"]
    assert client.get(f"/api/public/b/{b['slug']}").status_code == 404
    # Le super-administrateur garde l'accès
    assert client.get("/api/produits", headers={**super_admin, "X-Boutique-Id": b["id"]}).status_code == 200
    # Avertissement J+110 : une seule fois
    assert actions_de(executer(client), b) == []
    assert len([t for _, t in cv["envois"]["whatsapp"] if b["nom"] in t and "SUSPENDUE" in t]) == 1


def test_boutique_de_test_exclue(client, super_admin, nouvelle_boutique, cv):
    b, _ = nouvelle_boutique(test=True)
    fixer_echeance(client, super_admin, b, -200)
    rapport = executer(client)
    assert actions_de(rapport, b) == []
    assert fiche(client, b)["actif"] is True and not cv["r2"].fichiers
    assert b["id"] not in [x["id"] for x in client.get("/api/plateforme/cycle-vie", headers=super_admin).json()["boutiques"]]


# ---------------------------------------------------------------------------
# Archive vérifiée puis suppression ; échec de vérification
# ---------------------------------------------------------------------------
def test_archive_verifiee_puis_suppression(client, super_admin, boutique_equipee, nouvelle_boutique, cv):
    b = boutique_equipee["boutique"]
    nb = compter(client, "produits", b)  # 2 produits + ceux du catalogue public déjà publié
    email = dg_email(client, b)
    autre, h_autre = nouvelle_boutique()
    produits_autre = compter(client, "produits", autre)
    fixer_echeance(client, super_admin, b, -113)
    # J+113 : suspension + avertissements J+110 et J+112 ; l'archivage attend le lendemain
    assert actions_de(executer(client), b) == [("SUSPENSION", "FAIT"), ("AVERTISSEMENT_J112", "FAIT")]
    assert not cv["r2"].fichiers and compter(client, "produits", b) == nb
    async def releve():
        return await export_boutique.compter(b["id"], await export_boutique.collections_de(b["id"]))

    attendus = client.portal.call(releve)
    assert attendus["produits"] == nb and attendus["users"] == 1 and attendus["clients"] == 1
    # Le lendemain : archive envoyée sur R2, relue, vérifiée, puis suppression
    assert actions_de(executer(client, AUJ + timedelta(days=1)), b) == [("ARCHIVAGE", "ARCHIVEE")]
    [cle] = cv["r2"].fichiers
    assert cle.startswith("archives-locataires/") and cle.endswith(".adlexport")
    assert cv["r2"].fichiers[cle].startswith(b"ADLYNEXP") and b"Client Test" not in cv["r2"].fichiers[cle]
    for collection in ("produits", "clients", "categories", "users", "mouvements", "sessions_activite"):
        assert compter(client, collection, b) == 0, collection
    f = fiche(client, b)
    assert f["cycle_vie"]["statut"] == "ARCHIVE" and f["cycle_vie"]["archive"]["cle"] == cle
    assert f["cycle_vie"]["archive"]["comptes"]["produits"] == nb and f["actif"] is False
    # Les autres boutiques ne sont pas touchées
    assert compter(client, "produits", autre) == produits_autre
    assert client.get("/api/produits", headers=h_autre).status_code == 200
    # Le DG ne peut plus se connecter (compte supprimé)
    r = client.post("/api/auth/login", json={"code_boutique": b["code_marchand"], "email": email,
                                             "password": "motdepasse-123"})
    assert r.status_code in (400, 401, 403)
    # Plus rien à faire ensuite
    assert actions_de(executer(client, AUJ + timedelta(days=2)), b) == []
    etat = client.get("/api/plateforme/cycle-vie", headers=super_admin).json()
    assert any(a["cle"] == cle for a in etat["archives"])


def test_echec_de_verification_aucune_suppression(client, super_admin, boutique_equipee, cv):
    b = boutique_equipee["boutique"]
    nb = compter(client, "produits", b)  # 2 produits + ceux du catalogue public déjà publié
    fixer_echeance(client, super_admin, b, -113)
    executer(client)
    cv["r2"].alterer = True
    assert actions_de(executer(client, AUJ + timedelta(days=1)), b) == [("ARCHIVAGE", "ECHEC")]
    # Rien n'est supprimé, la copie non vérifiée est retirée de R2, alerte au super-admin
    assert compter(client, "produits", b) == nb and compter(client, "users", b) == 1
    assert not cv["r2"].fichiers
    f = fiche(client, b)
    assert f["cycle_vie"]["statut"] == "SUSPENDU_NON_RENOUVELE" and f["cycle_vie"]["archivage_echecs"] == 1
    alerte = client.portal.call(lambda: db.cycle_vie_journal.find_one({"boutique_id": b["id"], "niveau": "ALERTE"}))
    assert alerte and "AUCUNE donnée n'a été supprimée" in alerte["message"]
    assert any("ALERTE" in sujet for sujet, _, _ in cv["envois"]["email"])
    # Le lendemain, R2 de nouveau fiable : l'archivage réussit
    cv["r2"].alterer = False
    assert actions_de(executer(client, AUJ + timedelta(days=2)), b) == [("ARCHIVAGE", "ARCHIVEE")]
    assert compter(client, "produits", b) == 0


def test_sans_phrase_aucune_suppression(client, super_admin, boutique_equipee, cv, monkeypatch):
    b = boutique_equipee["boutique"]
    nb = compter(client, "produits", b)  # 2 produits + ceux du catalogue public déjà publié
    fixer_echeance(client, super_admin, b, -113)
    executer(client)
    monkeypatch.setattr(get_settings(), "sauvegarde_auto_phrase", None)
    assert actions_de(executer(client, AUJ + timedelta(days=1)), b) == [("ARCHIVAGE", "ECHEC")]
    assert compter(client, "produits", b) == nb and not cv["r2"].fichiers


# ---------------------------------------------------------------------------
# Simulation, interrupteur, paramètres
# ---------------------------------------------------------------------------
def test_simulation_sans_effet(client, super_admin, boutique_equipee, cv):
    b = boutique_equipee["boutique"]
    nb = compter(client, "produits", b)  # 2 produits + ceux du catalogue public déjà publié
    fixer_echeance(client, super_admin, b, -120)
    r = client.put("/api/plateforme/cycle-vie/parametres", headers=super_admin, json={"simulation": True})
    assert r.status_code == 200 and r.json()["simulation"] is True
    avant = fiche(client, b)
    rapport = client.post("/api/plateforme/cycle-vie/executer", headers=super_admin, json={}).json()
    assert rapport["simulation"] is True
    assert actions_de(rapport, b) == [("SUSPENSION", "SIMULE"), ("AVERTISSEMENT_J112", "SIMULE")]
    # Le lendemain (simulé) : l'archivage serait fait
    rapport = executer(client, AUJ + timedelta(days=1))
    assert ("ARCHIVAGE", "SIMULE") not in actions_de(rapport, b)  # la simulation ne mémorise rien
    assert fiche(client, b) == avant and compter(client, "produits", b) == nb
    assert not cv["r2"].fichiers
    assert not [t for _, t in cv["envois"]["whatsapp"] if b["nom"] in t]
    assert any("SIMULATION" in sujet for sujet, _, _ in cv["envois"]["email"])  # rapport quotidien


def test_simulation_d_une_boutique_deja_avertie_prevoit_l_archivage(client, super_admin, boutique_equipee, cv):
    b = boutique_equipee["boutique"]
    nb = compter(client, "produits", b)  # 2 produits + ceux du catalogue public déjà publié
    fixer_echeance(client, super_admin, b, -113)
    executer(client)  # réel : suspension + dernier avis
    rapport = executer(client, AUJ + timedelta(days=1), simulation=True)
    assert actions_de(rapport, b) == [("ARCHIVAGE", "SIMULE")]
    assert compter(client, "produits", b) == nb and not cv["r2"].fichiers


def test_interrupteur_general(client, super_admin, nouvelle_boutique, cv):
    b, _ = nouvelle_boutique()
    fixer_echeance(client, super_admin, b, -115)
    client.put("/api/plateforme/cycle-vie/parametres", headers=super_admin, json={"actif": False})
    rapport = executer(client)
    assert rapport["statut"] == "DESACTIVE" and actions_de(rapport, b) == []
    assert fiche(client, b)["actif"] is True


def test_parametres_et_droits(client, super_admin, nouvelle_boutique, cv):
    _, h = nouvelle_boutique()
    etat = client.get("/api/plateforme/cycle-vie", headers=super_admin).json()
    assert etat["parametres"]["actif"] is True and etat["parametres"]["simulation"] is False
    assert etat["parametres"]["conservation_jours"] == 365 and etat["parametres"]["frais_montant"] == 0
    assert client.put("/api/plateforme/cycle-vie/parametres", headers=super_admin,
                      json={"conservation_jours": 0}).status_code == 400
    assert client.put("/api/plateforme/cycle-vie/parametres", headers=super_admin,
                      json={"frais_montant": -1}).status_code == 400
    p = client.put("/api/plateforme/cycle-vie/parametres", headers=super_admin,
                   json={"conservation_jours": 730, "frais_montant": 10000, "frais_devise": "eur"}).json()
    assert (p["conservation_jours"], p["frais_montant"], p["frais_devise"]) == (730, 10000, "EUR")
    assert client.get("/api/plateforme/cycle-vie", headers=h).status_code == 403
    assert client.put("/api/plateforme/cycle-vie/parametres", headers=h, json={"actif": False}).status_code == 403


def test_route_du_cron(client, cv):
    url = "/api/cycle-vie/declencher"
    assert client.post(url).status_code == 401
    assert client.post(url, headers={"X-Sauvegarde-Jeton": "mauvais"}).status_code == 401
    r = client.post(url, headers={"X-Sauvegarde-Jeton": JETON})
    assert r.status_code == 202 and r.json()["statut"] == "LANCEE"
    assert client.post(url, headers={"X-Sauvegarde-Jeton": JETON}).json()["statut"] == "DEJA_FAITE"
    derniere = client.portal.call(lambda: db.cycle_vie_executions.find_one({"declencheur": "cron"}))
    assert derniere and derniere["jour"] == AUJ.isoformat()


# ---------------------------------------------------------------------------
# Conservation des archives, réouverture
# ---------------------------------------------------------------------------
def _archiver(client, super_admin, b):
    fixer_echeance(client, super_admin, b, -113)
    executer(client)
    assert ("ARCHIVAGE", "ARCHIVEE") in actions_de(executer(client, AUJ + timedelta(days=1)), b)
    return fiche(client, b)["cycle_vie"]["archive"]


def test_conservation_puis_effacement_de_l_archive(client, super_admin, boutique_equipee, cv):
    b = boutique_equipee["boutique"]
    nb = compter(client, "produits", b)  # 2 produits + ceux du catalogue public déjà publié
    archive = _archiver(client, super_admin, b)
    assert archive["cle"] in cv["r2"].fichiers
    # Durée de conservation non atteinte : l'archive reste
    executer(client, AUJ + timedelta(days=30))
    assert archive["cle"] in cv["r2"].fichiers
    # Conservation réduite à 10 jours : effacée au passage suivant (une seule fois)
    client.put("/api/plateforme/cycle-vie/parametres", headers=super_admin, json={"conservation_jours": 10})
    rapport = executer(client, AUJ + timedelta(days=30))
    assert [a["statut"] for a in rapport["archives_effacees"] if a["boutique_id"] == b["id"]] == ["EFFACEE"]
    assert archive["cle"] not in cv["r2"].fichiers
    assert fiche(client, b)["cycle_vie"]["archive"]["efface_le"]
    assert not [a for a in executer(client, AUJ + timedelta(days=31))["archives_effacees"] if a["boutique_id"] == b["id"]]
    # Réouverture devenue impossible
    r = client.post(f"/api/plateforme/cycle-vie/boutiques/{b['id']}/reouvrir", headers=super_admin,
                    json={"mode": "ESPECES", "montant": 0})
    assert r.status_code == 410


def test_reouverture_frais_et_restauration_limitee(client, super_admin, boutique_equipee, nouvelle_boutique, cv):
    b = boutique_equipee["boutique"]
    nb = compter(client, "produits", b)  # 2 produits + ceux du catalogue public déjà publié
    email = dg_email(client, b)
    autre, h_autre = nouvelle_boutique()
    client.post("/api/categories", headers=h_autre, json={"nom": "Rayon autre"})
    categories_autre = compter(client, "categories", autre)
    _archiver(client, super_admin, b)
    # Une donnée apparue après l'archivage (ex. catalogue) est remplacée par l'archive
    client.portal.call(lambda: db.produits.insert_one({"id": "intrus", "boutique_id": b["id"], "reference": "X"}))
    client.put("/api/plateforme/cycle-vie/parametres", headers=super_admin,
               json={"frais_montant": 5000, "frais_devise": "FCFA"})
    url = f"/api/plateforme/cycle-vie/boutiques/{b['id']}/reouvrir"
    r = client.post(url, headers=super_admin, json={"mode": "ESPECES", "montant": 1000})
    assert r.status_code == 400 and "5000 FCFA" in r.json()["detail"]
    assert compter(client, "users", b) == 0  # rien n'a été restauré
    r = client.post(url, headers=super_admin, json={"mode": "ESPECES", "montant": 5000, "reference": "Reçu 12",
                                                     "formule": "MENSUEL", "montant_abonnement": 5000})
    assert r.status_code == 200, r.text
    f = fiche(client, b)
    assert f["actif"] is True and f["suspension"] is None and f["cycle_vie"]["statut"] == "REOUVERT"
    assert date.fromisoformat(f["abonnement"]["echeance"]) > AUJ  # nouvelle échéance
    assert compter(client, "produits", b) == nb and compter(client, "clients", b) == 1 and compter(client, "users", b) == 1
    assert not client.portal.call(lambda: db.produits.find_one({"id": "intrus"}))
    # L'autre boutique n'est pas touchée
    assert compter(client, "categories", autre) == categories_autre
    # Le DG retrouve son compte et sa boutique
    login = client.post("/api/auth/login", json={"code_boutique": b["code_marchand"], "email": email,
                                                 "password": "motdepasse-123"})
    assert login.status_code == 200, login.text
    client.cookies.clear()
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/produits", headers=h).status_code == 200
    reouv = client.portal.call(lambda: db.cycle_vie_reouvertures.find_one({"boutique_id": b["id"]}))
    assert reouv["statut"] == "TERMINEE" and reouv["montant"] == 5000 and reouv["devise"] == "FCFA"
    assert client.post(url, headers=super_admin, json={"mode": "ESPECES", "montant": 5000}).status_code == 400


def test_reouverture_gratuite_par_defaut(client, super_admin, boutique_equipee, cv):
    b = boutique_equipee["boutique"]
    nb = compter(client, "produits", b)  # 2 produits + ceux du catalogue public déjà publié
    _archiver(client, super_admin, b)
    r = client.post(f"/api/plateforme/cycle-vie/boutiques/{b['id']}/reouvrir", headers=super_admin,
                    json={"mode": "OFFERT", "montant": 0})
    assert r.status_code == 200, r.text
    assert fiche(client, b)["abonnement"]["echeance"] == AUJ.isoformat()


def test_restauration_refuse_l_archive_d_une_autre_boutique(client, boutique_equipee, nouvelle_boutique, cv):
    b = boutique_equipee["boutique"]
    nb = compter(client, "produits", b)  # 2 produits + ceux du catalogue public déjà publié
    autre, _ = nouvelle_boutique()
    chemin = str(transfert_donnees.DOSSIER / "essai-autre.adlexport")
    client.portal.call(lambda: export_boutique.exporter(b["id"], PHRASE, chemin))
    with pytest.raises(export_boutique.ErreurArchive):
        client.portal.call(lambda: export_boutique.restaurer(chemin, PHRASE, autre["id"]))
    with pytest.raises(export_boutique.ErreurArchive):  # mauvaise phrase
        client.portal.call(lambda: export_boutique.restaurer(chemin, "une autre phrase secrète", b["id"]))
    assert compter(client, "produits", b) == nb
    import os
    os.remove(chemin)
