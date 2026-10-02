"""Sauvegarde générale automatique (Cron Job -> R2) et date de la dernière sauvegarde :
jeton obligatoire, une seule sauvegarde par jour, rétention 7 / 4 / 12, désactivation
sans phrase, alerte au-delà de 26 h, restauration depuis R2, affichage « Mon compte ».
R2 est SIMULÉ en mémoire et la base exportée est une base mongomock propre au test."""
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

import envois_plateforme
import sauvegarde_auto
import transfert_donnees
from config import get_settings
from db import db

JETON = "jeton-de-test-sauvegarde"
PHRASE = "phrase de sauvegarde automatique de test"
URL = "/api/sauvegarde-auto/declencher"


class FauxR2:
    """Bucket R2 en mémoire (mêmes opérations que sauvegarde_auto.StockageR2)."""

    def __init__(self):
        self.fichiers: dict[str, bytes] = {}
        self.echecs = 0

    async def envoyer(self, cle, chemin):
        if self.echecs:
            self.echecs -= 1
            raise RuntimeError("R2 injoignable (simulé)")
        with open(chemin, "rb") as f:
            self.fichiers[cle] = f.read()

    async def lister(self, prefixe):
        return [{"cle": c, "taille": len(v), "date": None} for c, v in self.fichiers.items() if c.startswith(prefixe)]

    async def supprimer(self, cle):
        self.fichiers.pop(cle, None)

    async def telecharger(self, cle, chemin):
        with open(chemin, "wb") as f:
            f.write(self.fichiers[cle])


@pytest.fixture
def auto(client, monkeypatch):
    """Configuration complète simulée : jeton, phrase, R2 en mémoire, base exportée dédiée, e-mails notés."""
    s = get_settings()
    monkeypatch.setattr(s, "sauvegarde_auto_jeton", JETON)
    monkeypatch.setattr(s, "sauvegarde_auto_phrase", PHRASE)
    monkeypatch.setattr(s, "rapport_email", "proprietaire@test.bf")
    r2 = FauxR2()
    monkeypatch.setattr(sauvegarde_auto, "stockage", lambda: r2)
    monkeypatch.setattr(sauvegarde_auto, "r2_configure", lambda: True)
    base = AsyncMongoMockClient()["base_sauvegarde_auto"]
    monkeypatch.setattr(transfert_donnees, "base_brute", lambda: base)
    courriels = []

    async def faux_email(sujet, corps, destinataire):
        courriels.append((sujet, corps, destinataire))
        return "ENVOYE", ""

    monkeypatch.setattr(envois_plateforme, "envoyer_email", faux_email)
    client.portal.call(lambda: base.tlb_boutiques.insert_many([{"id": f"b{i}", "nom": f"Boutique {i}"} for i in range(3)]))
    client.portal.call(lambda: db.sauvegardes_generales.delete_many({}))
    yield {"r2": r2, "base": base, "courriels": courriels}
    client.portal.call(lambda: db.sauvegardes_generales.delete_many({}))
    # Mots de passe refusés pendant le test : effacés (sinon blocage des autres tests de transfert)
    client.portal.call(lambda: db[transfert_donnees.JOURNAL].delete_many({"statut": "MOT_DE_PASSE_REFUSE"}))
    assert transfert_donnees.tache_active() is None


def test_jeton_obligatoire(client, auto, monkeypatch):
    assert client.post(URL).status_code == 401
    assert client.post(URL, headers={"X-Sauvegarde-Jeton": "mauvais"}).status_code == 401
    assert client.post(URL, headers={"X-Sauvegarde-Jeton": JETON[:-1]}).status_code == 401
    assert not auto["r2"].fichiers
    # Jeton non configuré sur le serveur : route fermée
    monkeypatch.setattr(get_settings(), "sauvegarde_auto_jeton", None)
    assert client.post(URL, headers={"X-Sauvegarde-Jeton": JETON}).status_code == 503


def test_sauvegarde_du_jour_une_seule_fois(client, super_admin, auto):
    r = client.post(URL, headers={"X-Sauvegarde-Jeton": JETON})
    assert r.status_code == 202 and r.json()["statut"] == "LANCEE"
    assert len(auto["r2"].fichiers) == 1
    cle, contenu = next(iter(auto["r2"].fichiers.items()))
    assert cle.startswith("sauvegardes-generales/adlyn-auto_") and cle.endswith(".adlexport")
    assert contenu.startswith(b"ADLYNEXP") and b"Boutique 1" not in contenu  # même format chiffré que l'export
    # Deuxième appel le même jour : rien de plus
    r = client.post(URL, headers={"X-Sauvegarde-Jeton": JETON})
    assert r.json()["statut"] == "DEJA_FAITE" and len(auto["r2"].fichiers) == 1
    assert client.post("/api/plateforme/sauvegarde-auto/lancer", headers=super_admin).json()["statut"] == "DEJA_FAITE"
    etat = client.get("/api/plateforme/sauvegarde-auto", headers=super_admin).json()
    assert etat["derniere_reussite"]["documents"] == 3 and etat["alerte"] is False
    assert [f["cle"] for f in etat["fichiers_r2"]] == [cle]
    # Rapport par e-mail (mécanisme d'envoi existant)
    assert len(auto["courriels"]) == 1 and "réussie" in auto["courriels"][0][0]
    assert etat["historique"][0]["rapport"]["statut"] == "ENVOYE"
    # Aucun fichier laissé sur le disque du serveur
    assert not list(transfert_donnees.DOSSIER.glob("auto-*"))


def test_journee_en_echec_relancable(client, auto):
    auto["r2"].echecs = 1
    assert client.post(URL, headers={"X-Sauvegarde-Jeton": JETON}).json()["statut"] == "LANCEE"
    jour = sauvegarde_auto.jour_local()
    doc = client.portal.call(lambda: db.sauvegardes_generales.find_one({"_id": jour}))
    assert doc["statut"] == "ECHEC" and "injoignable" in doc["erreur"]
    assert "ÉCHEC" in auto["courriels"][-1][0]
    # Le Cron Job rappelle : la journée en échec est refaite
    assert client.post(URL, headers={"X-Sauvegarde-Jeton": JETON}).json()["statut"] == "LANCEE"
    doc = client.portal.call(lambda: db.sauvegardes_generales.find_one({"_id": jour}))
    assert doc["statut"] == "SUCCES" and doc["tentatives"] == 2


def test_desactivee_sans_phrase(client, super_admin, auto, monkeypatch):
    monkeypatch.setattr(get_settings(), "sauvegarde_auto_phrase", None)
    r = client.post(URL, headers={"X-Sauvegarde-Jeton": JETON})
    assert r.status_code == 202 and r.json()["statut"] == "DESACTIVEE"
    assert not auto["r2"].fichiers
    etat = client.get("/api/plateforme/sauvegarde-auto", headers=super_admin).json()
    assert etat["active"] is False and etat["alerte"] is True
    assert any("DÉSACTIVÉE" in a for a in etat["alertes"])
    # Phrase trop courte : désactivée aussi
    monkeypatch.setattr(get_settings(), "sauvegarde_auto_phrase", "courte")
    assert client.post(URL, headers={"X-Sauvegarde-Jeton": JETON}).json()["statut"] == "DESACTIVEE"
    # Réservé au super-administrateur
    assert client.get("/api/plateforme/sauvegarde-auto").status_code == 401


def test_alerte_au_dela_de_26_heures(client, super_admin, auto):
    def inserer(heures):
        fin = (datetime.now(timezone.utc) - timedelta(hours=heures)).isoformat()
        client.portal.call(lambda: db.sauvegardes_generales.insert_one(
            {"_id": f"essai-{heures}", "jour": fin[:10], "statut": "SUCCES", "fin": fin}))

    etat = client.get("/api/plateforme/sauvegarde-auto", headers=super_admin).json()
    assert any("Aucune sauvegarde générale" in a for a in etat["alertes"])
    inserer(27)
    etat = client.get("/api/plateforme/sauvegarde-auto", headers=super_admin).json()
    assert etat["alerte"] is True and any("plus de 26 h" in a for a in etat["alertes"])
    inserer(25)
    etat = client.get("/api/plateforme/sauvegarde-auto", headers=super_admin).json()
    assert etat["alerte"] is False and etat["alertes"] == []


def test_retention_7_4_12():
    debut = date(2025, 1, 1)
    cles = [f"sauvegardes-generales/adlyn-auto_{(debut + timedelta(days=i)).isoformat()}_010000.adlexport"
            for i in range(500)]
    cles.append("sauvegardes-generales/autre-fichier.txt")  # nom inconnu : jamais supprimé
    garder = sauvegarde_auto.a_conserver(cles)
    datees = sorted(c for c in garder if "adlyn-auto_" in c)
    jours = [date.fromisoformat(c.split("_")[1]) for c in datees]
    dernier = debut + timedelta(days=499)
    # Les 7 derniers jours
    assert all(dernier - timedelta(days=i) in jours for i in range(7))
    # Une par mois sur 12 mois, une par semaine sur 4 semaines : au plus 7 + 4 + 12 au total
    assert len({(d.year, d.month) for d in jours}) == 12
    assert len(datees) <= 7 + 4 + 12
    assert min(jours) > dernier - timedelta(days=366)
    assert "sauvegardes-generales/autre-fichier.txt" in garder
    # Deux sauvegardes le même jour : seule la plus récente compte
    meme_jour = ["sauvegardes-generales/adlyn-auto_2026-10-02_010000.adlexport",
                 "sauvegardes-generales/adlyn-auto_2026-10-02_230000.adlexport"]
    assert sauvegarde_auto.a_conserver(meme_jour) == {meme_jour[1]}


def test_retention_appliquee_dans_r2(client, auto):
    for i in range(40):
        jour = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
        auto["r2"].fichiers[f"sauvegardes-generales/adlyn-auto_{jour}_010000.adlexport"] = b"x"
    assert client.post(URL, headers={"X-Sauvegarde-Jeton": JETON}).json()["statut"] == "LANCEE"
    doc = client.portal.call(lambda: db.sauvegardes_generales.find_one({"_id": sauvegarde_auto.jour_local()}))
    assert doc["statut"] == "SUCCES" and doc["purges"] > 0
    assert len(auto["r2"].fichiers) == 41 - doc["purges"]
    assert any(c.endswith(doc["fichier"]) for c in auto["r2"].fichiers)


def test_restauration_depuis_r2(client, super_admin, auto):
    assert client.post(URL, headers={"X-Sauvegarde-Jeton": JETON}).json()["statut"] == "LANCEE"
    cle = next(iter(auto["r2"].fichiers))
    client.portal.call(lambda: auto["base"].tlb_boutiques.insert_one({"id": "intruse", "nom": "Ajoutée après"}))
    url = "/api/plateforme/sauvegarde-auto/restaurer"
    # Garde-fous existants : mot REMPLACER et mot de passe du super-administrateur
    assert client.post(url, headers=super_admin, json={"cle": cle, "mot_de_passe": "super-motdepasse"}).status_code == 400
    assert client.post(url, headers=super_admin, json={"cle": cle, "mot_de_passe": "faux", "confirmation": "REMPLACER"}).status_code == 403
    assert client.post(url, headers=super_admin, json={"cle": "sauvegardes-generales/../x", "mot_de_passe": "super-motdepasse",
                                                       "confirmation": "REMPLACER"}).status_code == 400
    r = client.post(url, headers=super_admin, json={"cle": cle, "mot_de_passe": "super-motdepasse", "confirmation": "REMPLACER"})
    assert r.status_code == 202, r.text
    fin = time.time() + 60
    while time.time() < fin:
        t = client.get(f"/api/plateforme/transfert/taches/{r.json()['id']}").json()
        if t["statut"] != "EN_COURS":
            break
        time.sleep(0.05)
    assert t["statut"] == "TERMINE", t
    noms = client.portal.call(lambda: auto["base"].tlb_boutiques.distinct("nom"))
    assert sorted(noms) == ["Boutique 0", "Boutique 1", "Boutique 2"]
    assert not list(transfert_donnees.DOSSIER.glob("restauration-*"))


def test_date_des_dernieres_sauvegardes(client, super_admin, nouvelle_boutique, auto):
    b, h = nouvelle_boutique()
    url = "/api/auth/sauvegardes/dernieres"
    r = client.get(url, headers=h).json()
    assert r == {"generale": None, "boutique": None, "a_une_boutique": True}  # « Aucune sauvegarde enregistrée »

    async def remplir():
        await db.sauvegardes_generales.insert_one({"_id": "2026-10-01", "jour": "2026-10-01", "statut": "SUCCES",
                                                   "fin": "2026-10-01T22:30:00+00:00"})
        await db.sauvegardes_generales.insert_one({"_id": "2026-10-02", "jour": "2026-10-02", "statut": "ECHEC",
                                                   "fin": "2026-10-02T22:30:00+00:00"})
        await db.sauvegardes.insert_one({"id": "s1", "boutique_id": b["id"], "statut": "SUCCES",
                                         "date": "2026-09-30T00:05:00+00:00"})
        await db.sauvegardes.insert_one({"id": "s2", "boutique_id": b["id"], "statut": "ECHEC",
                                         "date": "2026-10-01T00:05:00+00:00"})
        await db.sauvegardes.insert_one({"id": "s3", "boutique_id": "autre-boutique", "statut": "SUCCES",
                                         "date": "2026-10-02T00:05:00+00:00"})

    client.portal.call(remplir)
    r = client.get(url, headers=h).json()
    # Fuseau de la plateforme : Africa/Ouagadougou (UTC+0)
    assert r["generale"]["texte"] == "01/10/2026 22:30"
    assert r["boutique"]["texte"] == "30/09/2026 00:05"
    # Super-administrateur : sauvegarde générale, et celle de la boutique qu'il consulte
    r = client.get(url, headers=super_admin).json()
    assert r["generale"]["texte"] == "01/10/2026 22:30" and r["boutique"] is None and r["a_une_boutique"] is False
    r = client.get(url, headers={**super_admin, "X-Boutique-Id": b["id"]}).json()
    assert r["boutique"]["texte"] == "30/09/2026 00:05"
    assert client.get(url).status_code == 401

