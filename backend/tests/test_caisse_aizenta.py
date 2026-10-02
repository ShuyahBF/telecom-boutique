"""Caisse Aizenta : webhook de Loois (jeton par boutique, validation du contrat v1,
idempotence, remplacement de période, taille maximale, journal) et situation de
caisse (agrégations par période, type, mode de paiement d'origine, caissier)."""
import asyncio
import json
from datetime import date, timedelta

import pytest

import caisse_aizenta
from db import db
from routes import caisse_aizenta as routes_caisse

URL = "/api/webhooks/caisse-aizenta"


@pytest.fixture(autouse=True)
def journal_vide():
    """Tous les appels des tests viennent de la même adresse (« testclient ») :
    on vide le journal pour ne pas déclencher la limitation de fréquence."""
    asyncio.run(db.caisse_receptions.delete_many({}))
    yield


@pytest.fixture
def caisse(client, super_admin, nouvelle_boutique):
    """Boutique neuve (options par défaut) + jeton du webhook généré par le super-admin."""
    b, h = nouvelle_boutique(options_par_defaut=True)
    r = client.post(f"/api/plateforme/caisse-aizenta/boutiques/{b['id']}/jeton", headers=super_admin)
    assert r.status_code == 200, r.text
    return {"boutique": b, "h": h, "jeton": r.json()["jeton"], "code": b["code_marchand"]}


def _op(id_, jour="2026-09-15", montant=10000, **extra):
    return {"id": id_, "date_heure": f"{jour}T09:00:00", "montant": montant, "caissier": "AWA",
            "mode_paiement": "ESPECES", "mode_paiement_code": "1", "mode_paiement_libelle": "Espèces", **extra}


def _envoi(code, operations, du="2026-09-01", au="2026-09-30", **extra):
    return {"version": 1, "code_boutique": code, "source": "Loois", "base": "AIZ_TEST",
            "genere_le": "2026-09-30T18:00:00Z", "periode": {"du": du, "au": au}, "operations": operations, **extra}


def _poster(client, jeton, corps, **entetes):
    return client.post(URL, headers={"Authorization": f"Bearer {jeton}", **entetes}, json=corps)


# ---------------------------------------------------------------------------
# Jeton et authentification
# ---------------------------------------------------------------------------
def test_jeton_haché_et_affiché_une_seule_fois(client, super_admin, caisse):
    etat = client.get(f"/api/plateforme/caisse-aizenta/boutiques/{caisse['boutique']['id']}", headers=super_admin).json()
    assert etat["jeton"]["apercu"] == caisse["jeton"][:8] + "…" and "jeton" not in json.dumps(etat["jeton"]).replace("apercu", "")
    assert etat["webhook_url"].endswith("/api/webhooks/caisse-aizenta")
    stocke = asyncio.run(db.caisse_jetons.find_one({"boutique_id": caisse["boutique"]["id"]}))
    assert stocke["hash"] == caisse_aizenta.hacher_jeton(caisse["jeton"]) and caisse["jeton"] not in str(stocke)
    # Réservé au super-admin
    assert client.post(f"/api/plateforme/caisse-aizenta/boutiques/{caisse['boutique']['id']}/jeton",
                       headers=caisse["h"]).status_code == 403


def test_jeton_valide_invalide_ou_autre_boutique(client, super_admin, caisse, nouvelle_boutique):
    corps = _envoi(caisse["code"], [_op("RC-1")])
    assert _poster(client, caisse["jeton"], corps).status_code == 200
    # Sans jeton / jeton faux
    assert client.post(URL, json=corps).status_code == 401
    r = _poster(client, "aiz_faux", corps)
    assert r.status_code == 401 and r.json()["detail"] == "Jeton invalide pour cette boutique"
    # Jeton d'une AUTRE boutique : refusé (un jeton ne vaut que pour sa boutique)
    autre, _ = nouvelle_boutique(options_par_defaut=True)
    jeton_autre = client.post(f"/api/plateforme/caisse-aizenta/boutiques/{autre['id']}/jeton", headers=super_admin).json()["jeton"]
    assert _poster(client, jeton_autre, corps).status_code == 401
    # Boutique inconnue : même réponse
    assert _poster(client, caisse["jeton"], _envoi("ZZZZZZ", [_op("RC-1")])).status_code == 401
    # Code en en-tête différent du corps
    assert _poster(client, caisse["jeton"], corps, **{"X-Code-Boutique": autre["code_marchand"]}).status_code == 400
    # Code fourni seulement en en-tête : accepté
    sans_code = {k: v for k, v in corps.items() if k != "code_boutique"}
    assert _poster(client, caisse["jeton"], sans_code, **{"X-Code-Boutique": caisse["code"]}).status_code == 200
    # Régénération : l'ancien jeton cesse de fonctionner
    nouveau = client.post(f"/api/plateforme/caisse-aizenta/boutiques/{caisse['boutique']['id']}/jeton",
                          headers=super_admin).json()["jeton"]
    assert _poster(client, caisse["jeton"], corps).status_code == 401
    assert _poster(client, nouveau, corps).status_code == 200


# ---------------------------------------------------------------------------
# Validation du contrat v1
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("modif,attendu", [
    (lambda c: c.update(version=2), "version"),
    (lambda c: c["operations"][0].update(montant="15000"), "operations[0].montant : nombre attendu"),
    (lambda c: c["operations"][0].update(type="VOL"), "operations[0].type : valeur non autorisée"),
    (lambda c: c["operations"][0].update(mode_paiement="BITCOIN"), "operations[0].mode_paiement"),
    (lambda c: c["operations"][0].pop("id"), "operations[0].id : champ obligatoire manquant"),
    (lambda c: c["operations"][0].update(date_heure="hier"), "operations[0].date_heure : date/heure invalide"),
    (lambda c: c["operations"][0].update(inconnu=1), "operations[0].inconnu : champ inconnu"),
    (lambda c: c["operations"][0].update(telephone="70000000"), "téléphone du client ne doit pas être transmis"),
    (lambda c: c["operations"][0].update(date_heure="2026-10-05T10:00:00"), "en dehors de la période"),
    (lambda c: c["operations"].append(dict(c["operations"][0])), "en double"),
    (lambda c: c.update(periode={"du": "2026-09-30", "au": "2026-09-01"}), "antérieur"),
])
def test_validation_stricte_messages_clairs(client, caisse, modif, attendu):
    corps = _envoi(caisse["code"], [_op("RC-1")])
    modif(corps)
    r = _poster(client, caisse["jeton"], corps)
    assert r.status_code == 422, r.text
    assert any(attendu in e for e in r.json()["erreurs"]), r.json()["erreurs"]
    # Rien n'a été enregistré
    assert asyncio.run(db.caisse_operations.count_documents({"boutique_id": caisse["boutique"]["id"]})) == 0


def test_taille_maximale(client, caisse, monkeypatch):
    monkeypatch.setattr(routes_caisse, "TAILLE_MAX_CORPS", 2000)
    corps = _envoi(caisse["code"], [_op(f"RC-{i}") for i in range(50)])
    r = _poster(client, caisse["jeton"], corps)
    assert r.status_code == 413 and "volumineux" in r.json()["detail"]


def test_limitation_de_frequence(client, caisse, monkeypatch):
    monkeypatch.setattr(routes_caisse, "APPELS_MAX_MINUTE", 3)
    corps = _envoi(caisse["code"], [_op("RC-1")])
    codes = [_poster(client, caisse["jeton"], corps).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


# ---------------------------------------------------------------------------
# Idempotence et remplacement de période
# ---------------------------------------------------------------------------
def test_idempotence_et_remplacer_periode(client, caisse):
    bid = caisse["boutique"]["id"]
    corps = _envoi(caisse["code"], [_op("RC-1"), _op("RC-2", montant=5000)])
    r = _poster(client, caisse["jeton"], corps).json()
    assert r["operations_nouvelles"] == 2 and r["operations_mises_a_jour"] == 0
    # Même envoi une seconde fois : aucun doublon, mise à jour seulement
    corps["operations"][1]["montant"] = 7000
    r = _poster(client, caisse["jeton"], corps).json()
    assert r["operations_nouvelles"] == 0 and r["operations_mises_a_jour"] == 2
    ops = asyncio.run(db.caisse_operations.find({"boutique_id": bid}, {"_id": 0}).to_list(None))
    assert len(ops) == 2 and {o["id_aizenta"]: o["montant"] for o in ops} == {"RC-1": 10000, "RC-2": 7000}
    # Sans remplacer_periode, une opération absente de l'envoi est conservée
    _poster(client, caisse["jeton"], _envoi(caisse["code"], [_op("RC-3")]))
    assert asyncio.run(db.caisse_operations.count_documents({"boutique_id": bid})) == 3
    # Avec remplacer_periode : la période ne contient plus QUE l'envoi ; hors période, rien ne bouge
    _poster(client, caisse["jeton"], _envoi(caisse["code"], [_op("RC-AOUT", jour="2026-08-10")],
                                            du="2026-08-01", au="2026-08-31"))
    r = _poster(client, caisse["jeton"], _envoi(caisse["code"], [_op("RC-2", montant=7000)], remplacer_periode=True)).json()
    assert r["operations_supprimees"] == 2
    ids = {o["id_aizenta"] for o in asyncio.run(db.caisse_operations.find({"boutique_id": bid}).to_list(None))}
    assert ids == {"RC-2", "RC-AOUT"}
    # Période vidée entièrement (liste vide + remplacer_periode)
    _poster(client, caisse["jeton"], _envoi(caisse["code"], [], du="2026-08-01", au="2026-08-31", remplacer_periode=True))
    assert {o["id_aizenta"] for o in asyncio.run(db.caisse_operations.find({"boutique_id": bid}).to_list(None))} == {"RC-2"}


def test_telephone_jamais_stocke_et_types_paiement_memorises(client, caisse):
    corps = _envoi(caisse["code"], [_op("RC-1", mode_paiement_libelle="", mode_paiement_code="7",
                                        reference="RA-0001", code_client="C001", observation="acompte",
                                        cheque={"numero": "123", "date": "2026-09-15", "echeance": "2026-10-15"})],
                   types_paiement=[{"code": "7", "libelle": "Orange Money", "mode_paiement": "MOBILE_MONEY"}])
    assert _poster(client, caisse["jeton"], corps).status_code == 200
    op = asyncio.run(db.caisse_operations.find_one({"boutique_id": caisse["boutique"]["id"]}, {"_id": 0}))
    assert "telephone" not in json.dumps(op).lower()
    assert op["cheque"] == {"numero": "123", "date": "2026-09-15", "echeance": "2026-10-15"}
    # Libellé repris du référentiel TypePaiementCaisse reçu
    s = client.get("/api/caisse-aizenta/situation?du=2026-09-01&au=2026-09-30", headers=caisse["h"]).json()
    assert s["par_mode"][0]["libelle"] == "Orange Money" and s["par_mode"][0]["codes"] == ["7"]


def test_journal_des_receptions(client, super_admin, caisse):
    _poster(client, caisse["jeton"], _envoi(caisse["code"], [_op("RC-1"), _op("RC-2")]))
    corps = _envoi(caisse["code"], [_op("RC-3", montant="x")])
    _poster(client, caisse["jeton"], corps)
    lignes = client.get(f"/api/plateforme/caisse-aizenta/receptions?boutique_id={caisse['boutique']['id']}",
                        headers=super_admin).json()
    assert [l["resultat"] for l in lignes] == ["REFUSEE", "ACCEPTEE"]
    assert lignes[1]["nb_operations"] == 2 and lignes[1]["date"] and lignes[1]["periode"]["du"] == "2026-09-01"
    assert lignes[0]["code_http"] == 422 and lignes[0]["erreurs"]


# ---------------------------------------------------------------------------
# Situation de caisse
# ---------------------------------------------------------------------------
def test_calculs_par_type_mode_caissier():
    ops = [
        {"montant": 10000, "type": "REGLEMENT", "mode_paiement": "ESPECES", "mode_libelle": "Espèces", "caissier": "AWA"},
        {"montant": 5000, "type": "REGLEMENT", "mode_paiement": "MOBILE_MONEY", "mode_libelle": "Orange Money", "caissier": "AWA"},
        {"montant": 2500.5, "type": "VENTE", "mode_paiement": "ESPECES", "mode_libelle": "Espèces", "caissier": "ALI"},
        {"montant": -3000, "type": "DEPENSE", "mode_paiement": "ESPECES", "mode_libelle": "Espèces", "caissier": "ALI"},
        {"montant": 20000, "type": "FOND_DE_CAISSE", "mode_paiement": "ESPECES", "mode_libelle": "Espèces", "caissier": ""},
    ]
    s = caisse_aizenta.calculer_situation(ops)
    assert s["nb_operations"] == 5
    assert s["total_encaisse"] == 17500.5 and s["total_sorties"] == 3000 and s["fond_de_caisse"] == 20000
    assert s["solde_net"] == 14500.5
    par_type = {g["type"]: g for g in s["par_type"]}
    assert par_type["REGLEMENT"]["total"] == 15000 and par_type["REGLEMENT"]["nb"] == 2
    assert par_type["DEPENSE"]["sorties"] == 3000 and par_type["DEPENSE"]["libelle"] == "Dépense"
    par_mode = {g["libelle"]: g for g in s["par_mode"]}
    assert par_mode["Espèces"]["total"] == 29500.5 and par_mode["Orange Money"]["total"] == 5000
    par_caissier = {g["libelle"]: g for g in s["par_caissier"]}
    assert par_caissier["AWA"]["entrees"] == 15000 and par_caissier["ALI"]["total"] == -499.5
    assert par_caissier["(non renseigné)"]["entrees"] == 0  # le fond de caisse n'est pas un encaissement


def test_situation_bornes_de_dates_et_filtres(client, caisse):
    ops = [_op("A", jour="2026-09-01", montant=1000), _op("B", jour="2026-09-15", montant=2000, caissier="ALI"),
           _op("C", jour="2026-09-30", montant=4000, type="VENTE", mode_paiement_libelle="Wave", mode_paiement_code="9"),
           _op("D", jour="2026-09-30", montant=-500, type="DEPENSE", libelle="Carburant")]
    ops[2]["date_heure"] = "2026-09-30T23:59:59"
    _poster(client, caisse["jeton"], _envoi(caisse["code"], ops,
                                            arrets_caisse=[{"id": "AR-1", "date_heure": "2026-09-30T20:00:00", "caissier": "AWA",
                                                            "montant_theorique": 5000, "montant_compte": 4500}]))
    h = caisse["h"]
    # Bornes incluses
    s = client.get("/api/caisse-aizenta/situation?du=2026-09-01&au=2026-09-01", headers=h).json()
    assert s["nb_operations"] == 1 and s["total_encaisse"] == 1000 and s["arrets_caisse"] == []
    s = client.get("/api/caisse-aizenta/situation?du=2026-09-02&au=2026-09-30", headers=h).json()
    assert s["nb_operations"] == 3 and s["total_encaisse"] == 6000 and s["total_sorties"] == 500 and s["solde_net"] == 5500
    assert s["arrets_caisse"][0]["ecart"] == -500  # écart calculé : compté - théorique
    assert s["derniere_reception"]["nb_operations"] == 4 and s["alerte_reception"] is False
    # Défaut : aujourd'hui (Ouagadougou, UTC+0) -> aucune opération de septembre
    s = client.get("/api/caisse-aizenta/situation", headers=h).json()
    assert s["periode"]["du"] == s["periode"]["au"] == caisse_aizenta.aujourd_hui().isoformat()
    assert client.get("/api/caisse-aizenta/situation?du=2026-09-30&au=2026-09-01", headers=h).status_code == 400
    assert client.get("/api/caisse-aizenta/situation?du=30/09/2026", headers=h).status_code == 400
    # Liste détaillée : tri récent d'abord, filtres, pagination
    base = "/api/caisse-aizenta/operations?du=2026-09-01&au=2026-09-30"
    r = client.get(base + "&par_page=2", headers=h).json()
    assert r["total"] == 4 and [l["id_aizenta"] for l in r["lignes"]] == ["C", "D"]
    assert client.get(base + "&par_page=2&page=2", headers=h).json()["lignes"][1]["id_aizenta"] == "A"
    assert [l["id_aizenta"] for l in client.get(base + "&mode=Wave", headers=h).json()["lignes"]] == ["C"]
    assert [l["id_aizenta"] for l in client.get(base + "&caissier=ALI", headers=h).json()["lignes"]] == ["B"]
    assert [l["id_aizenta"] for l in client.get(base + "&type=DEPENSE", headers=h).json()["lignes"]] == ["D"]
    assert [l["id_aizenta"] for l in client.get(base + "&q=carbu", headers=h).json()["lignes"]] == ["D"]
    # Export CSV (séparateur « ; », BOM pour Excel)
    r = client.get("/api/caisse-aizenta/operations.csv?du=2026-09-01&au=2026-09-30", headers=h)
    assert r.status_code == 200 and r.text.startswith("﻿Date et heure;") and "Carburant" in r.text
    assert "attachment" in r.headers["content-disposition"]


def test_heure_avec_fuseau_convertie_en_utc():
    assert caisse_aizenta.lire_date_heure("2026-10-01T00:30:00+01:00").isoformat() == "2026-09-30T23:30:00"
    assert caisse_aizenta.lire_date_heure("2026-10-01").isoformat() == "2026-10-01T00:00:00"
    assert caisse_aizenta.lire_date_heure("2026-10-01T08:00:00Z").isoformat() == "2026-10-01T08:00:00"


def test_alerte_si_aucune_reception_depuis_24h(client, caisse):
    s = client.get("/api/caisse-aizenta/situation", headers=caisse["h"]).json()
    assert s["derniere_reception"] is None and s["alerte_reception"] is True and s["a_des_donnees"] is False
    assert s["jeton_configure"] is True
    hier = (date.today() - timedelta(days=2)).isoformat() + "T08:00:00+00:00"
    asyncio.run(db.caisse_receptions.insert_one({"id": "x", "date": hier, "boutique_id": caisse["boutique"]["id"],
                                                 "resultat": "ACCEPTEE", "nb_operations": 1, "ip": "autre"}))
    s = client.get("/api/caisse-aizenta/situation", headers=caisse["h"]).json()
    assert s["derniere_reception"]["date"] == hier and s["alerte_reception"] is True


def test_cloisonnement_entre_boutiques(client, super_admin, caisse, nouvelle_boutique):
    _poster(client, caisse["jeton"], _envoi(caisse["code"], [_op("RC-1")]))
    _, h_autre = nouvelle_boutique(options_par_defaut=True)
    s = client.get("/api/caisse-aizenta/situation?du=2026-09-01&au=2026-09-30", headers=h_autre).json()
    assert s["nb_operations"] == 0


def test_exemple_de_la_documentation(client, caisse):
    """L'exemple complet de docs/caisse-aizenta.md est accepté et donne les totaux annoncés."""
    import re
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[2] / "docs" / "caisse-aizenta.md").read_text(encoding="utf-8")
    exemple = json.loads(re.search(r"## 4\. Exemple complet.*?```json\n(.*?)```", doc, re.S).group(1))
    exemple["code_boutique"] = caisse["code"]
    r = _poster(client, caisse["jeton"], exemple)
    assert r.status_code == 200, r.text
    s = client.get("/api/caisse-aizenta/situation?du=2026-10-01&au=2026-10-01", headers=caisse["h"]).json()
    assert (s["total_encaisse"], s["total_sorties"], s["solde_net"], s["fond_de_caisse"]) == (135000.5, 3500, 131500.5, 25000)
    assert s["arrets_caisse"][0]["ecart"] == -500
    # La dépense ne porte que le code « 1 » : libellée grâce au référentiel reçu
    assert {m["libelle"] for m in s["par_mode"]} == {"Espèces", "Orange Money", "Chèque"}
