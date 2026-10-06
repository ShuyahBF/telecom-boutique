"""Statistiques du jour demandées par SAWALI (type « stats_du_jour ») sur l'URL de
retour POST /api/webhooks/liluvine-retour : signature HMAC identique aux autres
retours, réponse {"indicateurs": [...], "faits_marquants": [...]}, aucun effet
sur les autres types de retour. Base MongoDB en mémoire (voir conftest.py)."""
import json
import time
from datetime import datetime, timezone

import pytest

import stats_du_jour
import transmission_wa as tw
from config import get_settings
from db import db
from utils import new_id

CLE = "cle-hmac-de-test-stats"
CHEMIN = "/api/webhooks/liluvine-retour"


@pytest.fixture
def reglages(client, monkeypatch):
    """Transmission Liluvine configurée avec une clé de test (aucun secret réel)."""
    s = get_settings()
    monkeypatch.setattr(s, "liluvine_wa_url", "https://sawali.test/api/webhook/liluvine-send")
    monkeypatch.setattr(s, "liluvine_wa_hmac", CLE)
    monkeypatch.setattr(s, "liluvine_wa_emetteur", "adlyn")
    return s


def _poster(client, doc, cle=CLE, horodatage=None):
    """POST signé exactement comme le fait SAWALI."""
    corps = json.dumps(doc).encode()
    ts = str(horodatage or int(time.time()))
    return client.post(CHEMIN, content=corps, headers={
        "Content-Type": "application/json", "X-Emetteur": "sawali", "X-Timestamp": ts,
        "X-Signature": tw.signer(cle, ts, corps)})


def _periode():
    """Période du test : une journée UTC très ancienne (2001-02-03), propre à ce
    fichier, pour ne pas compter les données créées par les autres tests."""
    return "2001-02-03T00:00:00Z", "2001-02-04T00:00:00Z"


def _inserer_donnees(client):
    """Jeu de données : 1 boutique créée dans la période, 2 connexions, 1 facture,
    1 paiement, 1 abonnement, des données HORS période qui ne doivent pas compter."""
    dans, hors = "2001-02-03T10:00:00+00:00", "2001-02-04T00:00:00+00:00"  # « fin » est exclue
    bid = new_id()

    async def inserer():
        await db.boutiques.insert_one({"id": bid, "nom": "Boutique Stats", "actif": True, "created_at": dans})
        await db.connexions_journal.insert_many([
            {"id": new_id(), "boutique_id": bid, "date": dans, "resultat": "SUCCES"},
            {"id": new_id(), "boutique_id": bid, "date": "2001-02-03T23:59:59+00:00", "resultat": "SUCCES"},
            {"id": new_id(), "boutique_id": bid, "date": dans, "resultat": "ECHEC"},
            {"id": new_id(), "boutique_id": bid, "date": hors, "resultat": "SUCCES"}])
        await db.clients.insert_one({"id": new_id(), "boutique_id": bid, "nom": "Client", "created_at": dans})
        await db.documents.insert_many([
            {"id": new_id(), "boutique_id": bid, "type_document": "FAC", "statut": "VALIDE",
             "total_ttc": 250000, "date_validation": dans, "created_at": dans},
            {"id": new_id(), "boutique_id": bid, "type_document": "FAC", "statut": "VALIDE",
             "total_ttc": 1000, "date_validation": hors, "created_at": hors},
            {"id": new_id(), "boutique_id": bid, "type_document": "PRO", "statut": "BROUILLON",
             "total_ttc": 5000, "date_validation": None, "created_at": dans}])
        await db.paiements.insert_one({"id": new_id(), "boutique_id": bid, "montant": 15000, "statut": "paye",
                                       "updated_at": dans, "created_at": dans})
        await db.abonnement_paiements.insert_one({"id": new_id(), "boutique_id": bid, "montant": 10000,
                                                  "created_at": dans})
        await db.parrainages.insert_one({"id": new_id(), "parrain_id": bid, "created_at": dans})

    client.portal.call(inserer)
    return bid


@pytest.fixture
def donnees(client):
    """Insère le jeu de données, puis le SUPPRIME après le test : la boutique fictive
    (incomplète) ne doit pas gêner les autres tests qui parcourent les boutiques."""
    bid = _inserer_donnees(client)
    yield bid

    async def nettoyer():
        await db.boutiques.delete_many({"id": bid})
        for nom in ("connexions_journal", "clients", "documents", "paiements", "abonnement_paiements"):
            await db[nom].delete_many({"boutique_id": bid})
        await db.parrainages.delete_many({"parrain_id": bid})

    client.portal.call(nettoyer)


def test_stats_signature_valide(client, reglages, donnees):
    debut, fin = _periode()
    r = _poster(client, {"type": "stats_du_jour", "debut": debut, "fin": fin})
    assert r.status_code == 200, r.text
    corps = r.json()
    indicateurs = {i["cle"]: i for i in corps["indicateurs"]}
    # Format attendu par SAWALI : 4 à 10 indicateurs {cle, libelle, valeur}
    assert 4 <= len(corps["indicateurs"]) <= 10
    assert all(set(i) == {"cle", "libelle", "valeur"} and i["libelle"] for i in corps["indicateurs"])
    # Valeurs : seules les données de la période [debut, fin) sont comptées
    assert indicateurs["connexions"]["valeur"] == 2
    assert indicateurs["boutiques_nouvelles"]["valeur"] == 1
    assert indicateurs["clients_nouveaux"]["valeur"] == 1
    assert indicateurs["factures"]["valeur"] == 1
    assert indicateurs["chiffre_affaires"]["valeur"] == 250000
    assert indicateurs["paiements"]["valeur"] == 1
    assert indicateurs["montant_paiements"]["valeur"] == 15000
    assert indicateurs["abonnements_payes"]["valeur"] == 1
    assert isinstance(indicateurs["boutiques_actives"]["valeur"], int)
    # Faits marquants : 5 phrases au plus, en français
    faits = corps["faits_marquants"]
    assert len(faits) <= 5
    assert any("Boutique Stats" in f and "nouvelle boutique" in f for f in faits)
    assert any("250 000 FCFA" in f for f in faits)
    # La clé HMAC n'apparaît jamais dans la réponse
    assert CLE not in r.text


def test_stats_mauvaise_signature_refusee(client, reglages):
    debut, fin = _periode()
    demande = {"type": "stats_du_jour", "debut": debut, "fin": fin}
    assert _poster(client, demande, cle="mauvaise-cle").status_code == 401
    # Horodatage hors de la fenêtre de ± 5 minutes : refusé aussi
    assert _poster(client, demande, horodatage=int(time.time()) - 600).status_code == 401


def test_stats_periode_invalide(client, reglages):
    # Dates absentes, inversées ou période trop longue : 422
    assert _poster(client, {"type": "stats_du_jour"}).status_code == 422
    assert _poster(client, {"type": "stats_du_jour", "debut": "2001-02-04T00:00:00Z",
                            "fin": "2001-02-03T00:00:00Z"}).status_code == 422
    assert _poster(client, {"type": "stats_du_jour", "debut": "2001-01-01T00:00:00Z",
                            "fin": "2001-03-01T00:00:00Z"}).status_code == 422


def test_stats_periode_vide(client, reglages):
    # Période sans aucune donnée : tout vaut 0, aucun fait marquant lié à la période
    r = _poster(client, {"type": "stats_du_jour", "debut": "1999-01-01T00:00:00Z", "fin": "1999-01-02T00:00:00Z"})
    assert r.status_code == 200
    valeurs = {i["cle"]: i["valeur"] for i in r.json()["indicateurs"]}
    assert valeurs["connexions"] == 0 and valeurs["chiffre_affaires"] == 0 and valeurs["commandes"] == 0


def test_autres_types_de_retour_inchanges(client, reglages):
    # Une désinscription reste enregistrée comme avant (réponse {"ok", "doublon"})
    de = "+22670" + str(int(time.time() * 1000))[-6:]
    r = _poster(client, {"type": "desinscription", "de": de, "date": "2026-10-04T12:00:00Z"})
    assert r.status_code == 200 and r.json() == {"ok": True, "doublon": False}
    # Type inconnu : toujours 422
    assert _poster(client, {"type": "autre"}).status_code == 422
    # Une demande de statistiques n'écrit rien dans les retours
    avant = client.portal.call(lambda: db.liluvine_retours.count_documents({}))
    debut, fin = _periode()
    _poster(client, {"type": "stats_du_jour", "debut": debut, "fin": fin})
    assert client.portal.call(lambda: db.liluvine_retours.count_documents({})) == avant


def test_lire_periode_formats():
    # « Z », « +00:00 » et date sans fuseau sont acceptés et ramenés en UTC
    d, f = stats_du_jour.lire_periode({"debut": "2026-10-05T00:00:00Z", "fin": "2026-10-06T01:00:00+01:00"})
    assert d == "2026-10-05T00:00:00+00:00" and f == "2026-10-06T00:00:00+00:00"
    d, _ = stats_du_jour.lire_periode({"debut": "2026-10-05T00:00:00", "fin": "2026-10-06T00:00:00"})
    assert d == datetime(2026, 10, 5, tzinfo=timezone.utc).isoformat()
