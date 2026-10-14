"""Lot 52 — contacts d'adLyn lus (signés) par SAWALI : signature, personnel des boutiques seulement, rien d'autre."""
import time

import export_contacts_sawali as E
from db import db

CHEMIN = "/api/sawali/contacts"
CLE = "cle-contacts-test"


def _entetes(requete, cle=CLE):
    ts = str(int(time.time()))
    return {"X-Timestamp": ts, "X-Signature": E.signer(cle, ts, CHEMIN, requete)}


def test_signature_et_peremption():
    s = E.signer("k", "1700000000", CHEMIN, "limite=5&page=1")
    assert E.signature_valide("k", "1700000000", s, CHEMIN, "limite=5&page=1", maintenant=1700000100)
    assert not E.signature_valide("k", "1700000000", s, CHEMIN, "limite=5&page=2", maintenant=1700000100)
    assert not E.signature_valide("k", "1700000000", s, CHEMIN, "limite=5&page=1", maintenant=1700000400)
    assert not E.signature_valide("k", "abc", s, CHEMIN, "", maintenant=1700000100)


def test_refus_sans_cle_ou_signature(client, monkeypatch):
    monkeypatch.delenv("SAWALI_CONTACTS_HMAC", raising=False)
    assert client.get(CHEMIN).status_code == 503
    monkeypatch.setenv("SAWALI_CONTACTS_HMAC", CLE)
    assert client.get(CHEMIN).status_code == 401
    assert client.get(f"{CHEMIN}?limite=5&page=1", headers=_entetes("limite=5&page=1", cle="autre")).status_code == 401


def test_personnel_des_boutiques_seulement(client, monkeypatch):
    monkeypatch.setenv("SAWALI_CONTACTS_HMAC", CLE)
    client.portal.call(db.boutiques.insert_one, {"id": "b-sc1", "nom": "Boutique Soleil"})
    client.portal.call(db.users.insert_many, [
        {"id": "u-sc1", "nom": "Awa DG", "telephone": "+22670112233", "role": "dg", "boutique_id": "b-sc1", "actif": True, "password_hash": "x"},
        {"id": "u-sc2", "nom": "Inactif", "telephone": "+22670112244", "role": "vendeur", "boutique_id": "b-sc1", "actif": False},
        {"id": "u-sc3", "nom": "Sans numéro", "telephone": "", "role": "vendeur", "boutique_id": "b-sc1", "actif": True},
        {"id": "u-sc4", "nom": "Super", "telephone": "+22670999999", "role": "super_admin", "actif": True}])
    q = "limite=500&page=1"
    r = client.get(f"{CHEMIN}?{q}", headers=_entetes(q))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["plateforme"] == "adLyn"
    awa = next(c for c in d["contacts"] if c["id"] == "u-sc1")
    assert awa == {"id": "u-sc1", "nom": "Awa DG", "telephone": "22670112233", "role": "dg", "societe": "adLyn · Boutique Soleil"}
    ids = {c["id"] for c in d["contacts"]}
    assert not ({"u-sc2", "u-sc3", "u-sc4"} & ids)             # inactif, sans numéro et super-administrateur absents
    assert all("password_hash" not in c and "mot_de_passe" not in c for c in d["contacts"])
