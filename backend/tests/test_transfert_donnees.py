"""Export / import complet de la base (changement de cluster MongoDB) :
format chiffré, aller-retour, contrôles d'accès, modes d'import, index.

Les bases « source » et « destination » sont des bases EN MÉMOIRE propres à
chaque test (mongomock) : la base de l'application, partagée par les autres
tests, n'est jamais exportée ni écrasée ici."""
import datetime
import io
import time
import uuid
import zipfile

import pytest
from bson import Binary, Decimal128, Int64, ObjectId, json_util
from mongomock_motor import AsyncMongoMockClient

import chiffrement_flux
import transfert_donnees as service

PHRASE = "phrase de test assez longue"
MOT_DE_PASSE = "super-motdepasse"  # mot de passe de test du super-admin (conftest.py)


@pytest.fixture
def bases(client, monkeypatch):
    """Deux bases vierges ; `bases["courante"]` désigne celle vue par l'export / import."""
    etat = {"source": AsyncMongoMockClient()["ancien_cluster"], "cible": AsyncMongoMockClient()["nouveau_cluster"]}
    etat["courante"] = etat["source"]
    monkeypatch.setattr(service, "base_brute", lambda: etat["courante"])
    yield etat
    assert service.tache_active() is None


def _executer(client, coroutine_factory):
    return client.portal.call(coroutine_factory)


def _attendre(client, tache_id, delai=60):
    fin = time.time() + delai
    while time.time() < fin:
        t = client.get(f"/api/plateforme/transfert/taches/{tache_id}").json()
        if t["statut"] != "EN_COURS":
            return t
        time.sleep(0.05)
    raise AssertionError("Tâche trop longue")


def _exporter(client, super_admin, phrase=PHRASE) -> bytes:
    r = client.post("/api/plateforme/transfert/export", headers=super_admin,
                    json={"mot_de_passe": MOT_DE_PASSE, "phrase": phrase, "phrase_confirmation": phrase})
    assert r.status_code == 202, r.text
    t = _attendre(client, r.json()["id"])
    assert t["statut"] == "TERMINE", t
    assert t["fichier_nom"].endswith(".adlexport")
    f = client.get(f"/api/plateforme/transfert/taches/{t['id']}/fichier", headers=super_admin)
    assert f.status_code == 200
    # Téléchargement unique : le fichier a été supprimé du serveur
    assert client.get(f"/api/plateforme/transfert/taches/{t['id']}/fichier", headers=super_admin).status_code == 404
    return f.content


def _importer(client, super_admin, contenu: bytes, mode="vide", phrase=PHRASE, confirmation="", mot_de_passe=MOT_DE_PASSE):
    return client.post("/api/plateforme/transfert/import", headers=super_admin,
                       files={"fichier": ("export.adlexport", io.BytesIO(contenu), "application/octet-stream")},
                       data={"phrase": phrase, "mot_de_passe": mot_de_passe, "mode": mode, "confirmation": confirmation})


DOC_TYPES = {
    "entier": 7, "long": Int64(2 ** 40), "decimal": Decimal128("12345.67"), "reel": 1.5,
    "date": datetime.datetime(2026, 3, 4, 5, 6, 7, 123000), "binaire": b"\x00\x01\xff",
    "uuid": Binary(uuid.UUID("12345678-1234-5678-1234-567812345678").bytes, 4), "oid": ObjectId(),
    "texte": "Ouagadougou — été 🎉", "nul": None, "liste": [1, {"imbrique": True}],
}


def _remplir_source(client, base):
    async def _f():
        await base.tlb_essai.insert_one({"_id": ObjectId(), **DOC_TYPES})
        await base.tlb_essai.insert_many([{"n": i, "nom": f"Produit {i}"} for i in range(2500)])  # plusieurs lots
        await base.tlb_essai.create_index("n", unique=True)
        await base.tlb_essai.create_index([("nom", "text")], name="recherche_texte")
        await base.tlb_essai.create_index("expire_le", expireAfterSeconds=60)
        await base["tlb_clés_été"].insert_one({"_id": "accentué", "valeur": "ça marche"})
        await base.tlb_users.insert_many([
            {"id": "sa-ancien", "email": "admin@ancien.bf", "role": "super_admin", "password_hash": "h1"},
            {"id": "dg-1", "email": "dg@boutique.bf", "role": "dg", "boutique_id": "b1", "password_hash": "h2"}])
        await base.tlb_boutiques.insert_one({"id": "b1", "nom": "Boutique 1"})
        await base.tlb_formules.insert_one({"id": "f1", "code": "MENSUEL", "montant": 6000})
        await base.autre_projet.insert_one({"x": 1})  # collection sans préfixe : exportée aussi
    _executer(client, _f)


def _demarrage_neuf(client, base):
    """Ce que crée le démarrage d'un serveur neuf : super-admin, formules, index."""
    async def _f():
        await base.tlb_users.insert_one({"id": "sa-neuf", "email": "admin@nouveau.bf", "role": "super_admin",
                                         "password_hash": "h3"})
        await base.tlb_formules.insert_many([{"id": "d1", "code": "MENSUEL"}, {"id": "d2", "code": "ANNUEL"}])
        await base.tlb_boutiques.create_index("id", unique=True)
        await base.tlb_echecs_connexion.insert_one({"cle": "x", "date": "2026"})
    _executer(client, _f)


def _documents(client, base, nom):
    return _executer(client, lambda: base[nom].find({}).sort("_id", 1).to_list(None))


def test_aller_retour_complet(client, super_admin, bases):
    _remplir_source(client, bases["source"])
    contenu = _exporter(client, super_admin)
    # Chiffré : en-tête adLyn, aucune donnée lisible
    assert contenu.startswith(b"ADLYNEXP")
    assert b"Ouagadougou" not in contenu and b"manifest" not in contenu

    # Contenu déchiffré : ZIP avec manifest + une ligne par document
    chemin = service.DOSSIER / "verif.adlexport"
    chemin.write_bytes(contenu)
    with chiffrement_flux.LecteurChiffre(str(chemin), PHRASE) as lecteur, zipfile.ZipFile(lecteur) as archive:
        manifest = json_util.loads(archive.read("manifest.json"))
        assert manifest["application"] == "adlyn" and manifest["version_format"] == 1
        assert manifest["base"] and manifest["date_utc"]
        par_nom = {c["nom"]: c for c in manifest["collections"]}
        assert par_nom["tlb_essai"]["documents"] == 2501 and par_nom["autre_projet"]["documents"] == 1
        assert {i["name"] for i in par_nom["tlb_essai"]["index"]} >= {"_id_", "n_1", "recherche_texte"}
        assert "collections/tlb_clés_été.jsonl" in archive.namelist()
        assert '"$numberLong"' in archive.read("collections/tlb_essai.jsonl").decode().splitlines()[0]
    chemin.unlink()

    # Nouveau cluster : seulement ce que crée le démarrage -> mode « base vide » accepté
    bases["courante"] = bases["cible"]
    _demarrage_neuf(client, bases["cible"])
    r = _importer(client, super_admin, contenu)
    assert r.status_code == 202, r.text
    t = _attendre(client, r.json()["id"])
    assert t["statut"] == "TERMINE", t
    assert t["rapport"]["conforme"] is True, t["rapport"]
    # Types conservés à l'identique, collection par collection
    for nom in ("tlb_essai", "tlb_clés_été", "tlb_boutiques", "autre_projet"):
        avant, apres = _documents(client, bases["source"], nom), _documents(client, bases["cible"], nom)
        assert avant == apres
        assert [{k: type(v) for k, v in d.items()} for d in avant] == [{k: type(v) for k, v in d.items()} for d in apres]
    original = next(d for d in _documents(client, bases["cible"], "tlb_essai") if "long" in d)
    assert isinstance(original["long"], Int64) and isinstance(original["decimal"], Decimal128)
    # Comptes : ceux du FICHIER (le super-admin créé au démarrage est remplacé)
    assert sorted(u["id"] for u in _documents(client, bases["cible"], "tlb_users")) == ["dg-1", "sa-ancien"]
    assert [f["id"] for f in _documents(client, bases["cible"], "tlb_formules")] == ["f1"]
    # Collection absente du fichier : laissée telle quelle
    assert len(_documents(client, bases["cible"], "tlb_echecs_connexion")) == 1
    # Index recréés (dont l'index texte et le TTL)
    index = _executer(client, lambda: bases["cible"].tlb_essai.index_information())
    assert index["n_1"].get("unique") and "recherche_texte" in index
    assert index["expire_le_1"]["expireAfterSeconds"] == 60
    # Journal : export, téléchargement, import (jamais la phrase secrète)
    journal = _executer(client, lambda: service.db[service.JOURNAL].find({}, {"_id": 0}).to_list(None))
    actions = {(j["action"], j["statut"]) for j in journal}
    assert {("export", "TERMINE"), ("telechargement_export", "TERMINE"), ("import", "TERMINE")} <= actions
    assert PHRASE not in str(journal)
    # Écran d'administration
    e = client.get("/api/plateforme/transfert", headers=super_admin).json()
    assert e["tache_en_cours"] is None and e["historique"]


def test_mauvaise_phrase_et_fichier_altere(client, super_admin, bases):
    _remplir_source(client, bases["source"])
    contenu = _exporter(client, super_admin)
    bases["courante"] = bases["cible"]
    # Phrase secrète incorrecte : refusée tout de suite, rien n'est lancé
    r = _importer(client, super_admin, contenu, phrase="mauvaise phrase secrète")
    assert r.status_code == 400 and "Phrase secrète incorrecte" in r.json()["detail"]
    # Fichier qui n'est pas un export adLyn
    r = _importer(client, super_admin, b"PK\x03\x04 pas un export")
    assert r.status_code == 400 and "n'est pas un export" in r.json()["detail"]
    # Fichier modifié en son milieu : détecté avant toute écriture dans la base
    abime = bytearray(contenu)
    abime[len(abime) // 2] ^= 0x01
    t = _attendre(client, _importer(client, super_admin, bytes(abime)).json()["id"])
    assert t["statut"] == "ECHEC" and "altéré" in t["erreur"]
    # Fichier tronqué (téléchargement interrompu)
    t = _attendre(client, _importer(client, super_admin, contenu[:-100]).json()["id"])
    assert t["statut"] == "ECHEC" and ("incomplet" in t["erreur"] or "altéré" in t["erreur"])
    assert _executer(client, lambda: bases["cible"].list_collection_names()) == []


def test_reserve_au_super_admin_et_mot_de_passe(client, super_admin, nouvelle_boutique, bases):
    _, dg = nouvelle_boutique()
    demande = {"mot_de_passe": MOT_DE_PASSE, "phrase": PHRASE, "phrase_confirmation": PHRASE}
    assert client.post("/api/plateforme/transfert/export", headers=dg, json=demande).status_code == 403
    assert client.get("/api/plateforme/transfert", headers=dg).status_code == 403
    assert _importer(client, dg, b"x").status_code == 403
    assert client.post("/api/plateforme/transfert/export", json=demande).status_code == 401
    # Phrase secrète : 12 caractères minimum, confirmée à l'identique
    court = {**demande, "phrase": "trop court", "phrase_confirmation": "trop court"}
    assert client.post("/api/plateforme/transfert/export", headers=super_admin, json=court).status_code == 400
    differente = {**demande, "phrase_confirmation": PHRASE + "!"}
    assert "identiques" in client.post("/api/plateforme/transfert/export", headers=super_admin, json=differente).json()["detail"]
    # Mot de passe faux : refusé et journalisé ; bloqué après 5 erreurs
    faux = {**demande, "mot_de_passe": "pas le bon"}
    try:
        for _ in range(service.MAX_ECHECS_MOT_DE_PASSE):
            r = client.post("/api/plateforme/transfert/export", headers=super_admin, json=faux)
            assert r.status_code == 403 and r.json()["detail"] == "Mot de passe incorrect"
        assert _importer(client, super_admin, b"x", mot_de_passe="pas le bon").status_code == 429
        assert client.post("/api/plateforme/transfert/export", headers=super_admin, json=demande).status_code == 429
    finally:
        _executer(client, lambda: service.db[service.JOURNAL].delete_many({"statut": "MOT_DE_PASSE_REFUSE"}))
    # Mode « remplacer » : il faut taper REMPLACER
    r = _importer(client, super_admin, b"x", mode="remplacer", confirmation="oui")
    assert r.status_code == 400 and "REMPLACER" in r.json()["detail"]
    assert _importer(client, super_admin, b"x", mode="tout").status_code == 400


def test_base_vide_refusee_puis_remplacer(client, super_admin, bases):
    _remplir_source(client, bases["source"])
    contenu = _exporter(client, super_admin)
    bases["courante"] = cible = bases["cible"]

    async def _occuper():
        await cible.tlb_boutiques.insert_one({"id": "b-existante", "nom": "Déjà là"})
        await cible.tlb_users.insert_one({"id": "dg-x", "email": "x@x.bf", "role": "dg"})
        await cible.tlb_hors_fichier.insert_one({"garde": True})
    _executer(client, _occuper)
    # Base non vide : refus, aucune donnée modifiée
    t = _attendre(client, _importer(client, super_admin, contenu).json()["id"])
    assert t["statut"] == "ECHEC" and "tlb_boutiques" in t["erreur"] and "tlb_users" in t["erreur"]
    assert [b["id"] for b in _documents(client, cible, "tlb_boutiques")] == ["b-existante"]
    # Remplacer : les collections du fichier sont vidées puis importées ; les autres restent
    r = _importer(client, super_admin, contenu, mode="remplacer", confirmation="REMPLACER")
    assert r.status_code == 202, r.text
    t = _attendre(client, r.json()["id"])
    assert t["statut"] == "TERMINE" and t["rapport"]["conforme"], t
    assert [b["id"] for b in _documents(client, cible, "tlb_boutiques")] == ["b1"]
    assert sorted(u["id"] for u in _documents(client, cible, "tlb_users")) == ["dg-1", "sa-ancien"]
    assert len(_documents(client, cible, "tlb_hors_fichier")) == 1
    # Un second import « base vide » est maintenant refusé (données présentes)
    t = _attendre(client, _importer(client, super_admin, contenu).json()["id"])
    assert t["statut"] == "ECHEC"


def test_index_texte_reconstruit_depuis_weights():
    # Définition telle que renvoyée par un vrai serveur MongoDB
    definition = {"v": 2, "key": {"boutique_id": 1, "_fts": "text", "_ftsx": 1}, "name": "recherche",
                  "weights": {"nom": 10, "description": 1}, "default_language": "french",
                  "language_override": "langue", "textIndexVersion": 3}
    cle, options = service.definition_vers_index(definition)
    assert cle == [("boutique_id", 1), ("nom", "text"), ("description", "text")]
    assert options == {"name": "recherche", "weights": {"nom": 10, "description": 1},
                       "default_language": "french", "language_override": "langue"}
    cle, options = service.definition_vers_index({"v": 2, "key": {"expire_le": 1}, "name": "expire_le_1",
                                                  "expireAfterSeconds": 0, "background": True})
    assert cle == [("expire_le", 1)] and options == {"name": "expire_le_1", "expireAfterSeconds": 0}


def test_chiffrement_par_blocs(tmp_path):
    """Plusieurs blocs : lecture dans le désordre, blocs permutés ou fichier rallongé refusés."""
    donnees = bytes(range(256)) * 50  # 12 800 octets -> 13 blocs de 1024
    chemin = tmp_path / "f.adlexport"
    with open(chemin, "wb") as f:
        e = chiffrement_flux.EcrivainChiffre(f, PHRASE, taille_bloc=1024)
        e.write(donnees[:5000])
        e.write(donnees[5000:])
        e.fermer_flux()
    with chiffrement_flux.LecteurChiffre(str(chemin), PHRASE) as lecteur:
        assert lecteur.taille == len(donnees)
        lecteur.seek(-300, io.SEEK_END)
        assert lecteur.read(300) == donnees[-300:]
        lecteur.seek(1000)
        assert lecteur.read(2100) == donnees[1000:3100]
    with pytest.raises(chiffrement_flux.PhraseIncorrecte):
        chiffrement_flux.LecteurChiffre(str(chemin), "une autre phrase secrète")
    brut = chemin.read_bytes()
    pas = 17 + 1024 + 16
    debut = chiffrement_flux.TAILLE_ENTETE
    permute = brut[:debut] + brut[debut + pas:debut + 2 * pas] + brut[debut:debut + pas] + brut[debut + 2 * pas:]
    for contenu in (permute, brut + b"\x00"):
        chemin.write_bytes(contenu)
        with pytest.raises(chiffrement_flux.ErreurChiffrement):
            chiffrement_flux.LecteurChiffre(str(chemin), PHRASE)
