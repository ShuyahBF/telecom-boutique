"""Écran « KYC des DG » : liste des DG au KYC pas à jour (absent, refusé, incomplet ;
en attente sur demande), exclusion des boutiques de test et archivées, rappel WhatsApp
aux seuls DG sélectionnés avec message modifiable, 1 rappel par DG et par 24 h, journal."""
from datetime import datetime, timedelta, timezone

import pytest

import envois_plateforme
from db import db

URL = "/api/plateforme/kyc-dg"


@pytest.fixture
def whatsapp(client, monkeypatch):
    envoyes = []

    async def wa(telephone, variables, texte, **kw):
        envoyes.append({"telephone": telephone, "texte": texte, "variables": variables})
        return "ENVOYE", ""

    monkeypatch.setattr(envois_plateforme, "envoyer_whatsapp", wa)
    return envoyes


def regler_kyc(client, b, statut, types=()):
    kyc = {"statut": statut, "motif_rejet": "Pièce illisible" if statut == "REJETE" else "", "verifie_par": "",
           "date_verification": None, "documents": [{"id": t, "type": t, "libelle": t} for t in types]}
    client.portal.call(lambda: db.boutiques.update_one({"id": b["id"]}, {"$set": {"kyc": kyc,
                                                                                  "dg_telephone": "+22670000000"}}))


def lignes(client, super_admin, ids, **params):
    r = client.get(URL, headers=super_admin, params=params)
    assert r.status_code == 200, r.text
    return {x["boutique_id"]: x for x in r.json()["dg"] if x["boutique_id"] in ids}


def test_liste_des_dg_au_kyc_pas_a_jour(client, super_admin, nouvelle_boutique):
    absent, _ = nouvelle_boutique()
    refuse, _ = nouvelle_boutique()
    incomplet, _ = nouvelle_boutique()
    attente, _ = nouvelle_boutique()
    verifie, _ = nouvelle_boutique()
    interne, _ = nouvelle_boutique(test=True)
    archivee, _ = nouvelle_boutique()
    regler_kyc(client, refuse, "REJETE", ["RCCM"])
    regler_kyc(client, incomplet, "EN_ATTENTE", ["RCCM"])
    regler_kyc(client, attente, "EN_ATTENTE", ["PIECE_IDENTITE_DG"])
    regler_kyc(client, verifie, "VERIFIE", ["PIECE_IDENTITE_DG"])
    client.portal.call(lambda: db.boutiques.update_one({"id": archivee["id"]}, {"$set": {"cycle_vie.statut": "ARCHIVE"}}))
    ids = {x["id"] for x in (absent, refuse, incomplet, attente, verifie, interne, archivee)}
    liste = lignes(client, super_admin, ids)
    assert {k: v["etat"] for k, v in liste.items()} == {absent["id"]: "ABSENT", refuse["id"]: "REFUSE",
                                                        incomplet["id"]: "INCOMPLET"}
    assert liste[refuse["id"]]["motif_rejet"] == "Pièce illisible" and liste[absent["id"]]["dg_id"]
    # Dossiers complets en attente de vérification : sur demande seulement
    assert lignes(client, super_admin, ids, inclure_en_attente="true")[attente["id"]]["etat"] == "EN_ATTENTE"
    # Réservé au super-administrateur
    _, h = nouvelle_boutique()
    assert client.get(URL, headers=h).status_code == 403
    assert client.post(f"{URL}/rappels", headers=h, json={"boutique_ids": [absent["id"]]}).status_code == 403


def test_rappel_selectif_limite_24h_et_journal(client, super_admin, nouvelle_boutique, whatsapp):
    a, _ = nouvelle_boutique(nom="Boutique KYC A")
    b, _ = nouvelle_boutique(nom="Boutique KYC B")
    c, _ = nouvelle_boutique(nom="Boutique KYC C")
    a_jour, _ = nouvelle_boutique(nom="Boutique KYC à jour")
    for x in (a, b, c):
        regler_kyc(client, x, "NON_FOURNI")
    regler_kyc(client, a_jour, "VERIFIE", ["PIECE_IDENTITE_DG"])
    message = "Bonjour {dg}, merci de compléter le KYC de {boutique} ({etat}) : {lien}"
    r = client.post(f"{URL}/rappels", headers=super_admin,
                    json={"boutique_ids": [a["id"], b["id"], a_jour["id"]], "message": message})
    assert r.status_code == 200, r.text
    statuts = {x["boutique_id"]: x["statut"] for x in r.json()["resultats"]}
    assert statuts == {a["id"]: "ENVOYE", b["id"]: "ENVOYE", a_jour["id"]: "NON_CONCERNE"}
    # Seuls les DG sélectionnés reçoivent le message, personnalisé
    textes = [w["texte"] for w in whatsapp]
    assert len(textes) == 2 and not any("KYC C" in t for t in textes)
    assert any(t.startswith("Bonjour DG") and "Boutique KYC A" in t and "kyc absent" in t and "/gestion/parametres" in t
               for t in textes)
    # Deuxième envoi dans les 24 h : refusé pour A, accepté pour C
    r = client.post(f"{URL}/rappels", headers=super_admin, json={"boutique_ids": [a["id"], c["id"]], "message": ""})
    statuts = {x["boutique_id"]: x["statut"] for x in r.json()["resultats"]}
    assert statuts == {a["id"]: "LIMITE_24H", c["id"]: "ENVOYE"}
    assert len(whatsapp) == 3 and "dossier d'identification" in whatsapp[-1]["texte"]  # message prédéfini
    liste = lignes(client, super_admin, {a["id"]})
    assert liste[a["id"]]["dernier_rappel"] and liste[a["id"]]["rappel_possible_le"]
    # Journal : chaque tentative, y compris le refus
    journal = [j for j in client.get(f"{URL}/journal", headers=super_admin).json() if j["boutique_id"] == a["id"]]
    assert sorted(j["statut"] for j in journal) == ["ENVOYE", "LIMITE_24H"]
    assert journal[0]["par"] == "super@plateforme-test.bf"
    # 24 h plus tard : nouveau rappel possible
    hier = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    client.portal.call(lambda: db.kyc_rappels_journal.update_many({"boutique_id": a["id"]}, {"$set": {"date": hier}}))
    r = client.post(f"{URL}/rappels", headers=super_admin, json={"boutique_ids": [a["id"]]})
    assert r.json()["resultats"][0]["statut"] == "ENVOYE" and r.json()["envoyes"] == 1


def test_echec_d_envoi_ne_bloque_pas_24h(client, super_admin, nouvelle_boutique, monkeypatch):
    a, _ = nouvelle_boutique()
    regler_kyc(client, a, "REJETE")

    async def wa_hs(telephone, variables, texte, **kw):
        return "NON_CONFIGURE", "WhatsApp non configuré"

    monkeypatch.setattr(envois_plateforme, "envoyer_whatsapp", wa_hs)
    r = client.post(f"{URL}/rappels", headers=super_admin, json={"boutique_ids": [a["id"]]})
    assert r.json()["resultats"][0]["statut"] == "NON_CONFIGURE"
    r = client.post(f"{URL}/rappels", headers=super_admin, json={"boutique_ids": [a["id"]]})
    assert r.json()["resultats"][0]["statut"] == "NON_CONFIGURE"  # pas « LIMITE_24H » : rien n'est parti
    assert client.post(f"{URL}/rappels", headers=super_admin, json={"boutique_ids": []}).status_code == 400
