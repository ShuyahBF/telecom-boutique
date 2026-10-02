"""Export et import COMPLETS de la base (changement de cluster MongoDB Atlas).

Usage prévu (super-administrateur uniquement) :
  1. sur l'ancien serveur : « Exporter toutes les données » -> fichier .adlexport ;
  2. dans Render : remplacer MONGO_URL par l'adresse du nouveau cluster ;
  3. sur le nouveau serveur (base vide) : « Importer » ce fichier.

Contenu du fichier (avant chiffrement, voir chiffrement_flux.py) : une archive
ZIP avec
  - manifest.json : application « adlyn », nom de la base, date UTC, version
    du format (1), et pour chaque collection son nombre de documents et ses
    index (tels que renvoyés par list_indexes) ;
  - collections/<nom>.jsonl : un document par ligne, en Extended JSON
    « canonique » (les types MongoDB sont conservés : dates, ObjectId,
    entiers 64 bits, décimaux, binaires...).

Contraintes du serveur Render gratuit (512 Mo de mémoire, requêtes longues
interrompues) : export et import tournent en TÂCHE DE FOND, par lots de
1000 documents, avec un fichier temporaire chiffré sur le disque (jamais de
données en clair sur le disque). Le navigateur suit la progression.

Collections « techniques » (créées automatiquement au démarrage d'un serveur
neuf, donc présentes dans une base « vide ») — mode « Base vide uniquement » :
  - users : le compte super-administrateur créé depuis SUPER_ADMIN_EMAIL /
    SUPER_ADMIN_PASSWORD. Tolérée seulement si elle ne contient QUE des
    super-administrateurs ; vidée puis remplacée par les comptes du fichier ;
  - formules : les formules d'abonnement par défaut. Tolérée seulement si
    elle ne contient que les codes par défaut ; vidée puis remplacée ;
  - echecs_connexion, verrous : traces temporaires (tentatives de connexion
    échouées, verrous des tâches de nuit) ; vidées puis remplacées ;
  - journal_transferts : ce journal ; jamais vidé, les lignes du fichier y
    sont AJOUTÉES (doublons ignorés).
  Les index créés au démarrage ne comptent pas (une collection sans document
  est vide). Toute autre collection du fichier qui contient déjà des
  documents dans la base cible bloque l'import (utiliser alors « Remplacer »).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import tempfile
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from bson import json_util
from bson.json_util import CANONICAL_JSON_OPTIONS
from fastapi import HTTPException
from pymongo.errors import BulkWriteError, PyMongoError

import chiffrement_flux
from abonnements import FORMULES_PAR_DEFAUT
from auth import verify_password
from config import get_settings
from db import SANS_ID, db
from utils import new_id, now_iso

logger = logging.getLogger(__name__)

APPLICATION = "adlyn"
VERSION_FORMAT = 1
EXTENSION = ".adlexport"
LOT = 1000  # documents lus / insérés à la fois
DUREE_VIE_SECONDES = 3600  # fichier d'export supprimé au bout d'une heure s'il n'est pas téléchargé
TAILLE_MAX_IMPORT = 4 * 1024 * 1024 * 1024  # 4 Go
LIGNE_MAX = 64 * 1024 * 1024  # un document MongoDB fait au plus 16 Mo (davantage en JSON)
MANIFEST_MAX = 64 * 1024 * 1024
MODES = ("vide", "remplacer")
MOT_REMPLACER = "REMPLACER"
# Mots de passe erronés tolérés par compte, sur 15 minutes
MAX_ECHECS_MOT_DE_PASSE = 5

# Nom LOGIQUE (sans préfixe) du journal des exports / imports
JOURNAL = "journal_transferts"
# Collections techniques (noms logiques) : voir la docstring du module
TECHNIQUES_REMPLACEES = ("users", "formules", "echecs_connexion", "verrous")
TECHNIQUES_FUSIONNEES = (JOURNAL,)
# Options d'index propres au serveur, à ne pas renvoyer à create_index
_OPTIONS_INDEX_IGNOREES = {"v", "key", "ns", "background", "textIndexVersion", "2dsphereIndexVersion"}

DOSSIER = Path(tempfile.gettempdir()) / "adlyn_transferts"

# Tâches en cours ou récentes (mémoire du serveur) : id -> état. L'id est un
# jeton aléatoire de 256 bits, impossible à deviner.
_taches: dict[str, dict] = {}
# Références des tâches asyncio (sinon Python peut les détruire en cours de route)
_en_cours: dict[str, asyncio.Task] = {}
_boucle_nettoyage: dict[str, asyncio.Task] = {}


class ErreurTransfert(Exception):
    """Erreur expliquée à l'administrateur (message en français)."""


def base_brute():
    """Base MongoDB complète (toutes les collections, sans préfixe automatique).
    Fonction séparée pour que les tests puissent la remplacer."""
    return db._database  # noqa: SLF001 — accès volontaire à la base entière


def _prefixe() -> str:
    return get_settings().mongo_collection_prefix


def _logique(nom: str) -> str:
    """Nom sans le préfixe du projet (tlb_users -> users)."""
    p = _prefixe()
    return nom[len(p):] if p and nom.startswith(p) else nom


# ---------------------------------------------------------------------------
# Tâches de fond : état, nettoyage
# ---------------------------------------------------------------------------
def _maintenant() -> float:
    return time.time()


def tache_active() -> Optional[dict]:
    return next((t for t in _taches.values() if t["statut"] == "EN_COURS"), None)


def _nouvelle_tache(type_: str, user: dict) -> dict:
    if tache_active():
        raise HTTPException(409, "Un export ou un import est déjà en cours : attendez qu'il se termine")
    tache = {"id": secrets.token_urlsafe(32), "type": type_, "statut": "EN_COURS", "etape": "Préparation…",
             "progression": 0, "documents_traites": 0, "documents_total": 0, "debut": now_iso(), "fin": None,
             "erreur": None, "rapport": None, "par": user.get("email", ""), "_creee": _maintenant()}
    _taches[tache["id"]] = tache
    return tache


def publique(tache: dict) -> dict:
    """État renvoyé au navigateur : jamais le chemin du fichier sur le serveur."""
    return {k: v for k, v in tache.items() if not k.startswith("_")}


def lire_tache(tache_id: str) -> dict:
    tache = _taches.get(tache_id)
    if not tache:
        raise HTTPException(404, "Opération introuvable ou expirée")
    return tache


def _supprimer(chemin: Optional[str]) -> None:
    if chemin:
        try:
            os.remove(chemin)
        except FileNotFoundError:
            pass


def nettoyer(tout: bool = False) -> None:
    """Supprime les fichiers temporaires expirés (tous, au démarrage) et oublie
    les tâches terminées depuis plus d'une heure."""
    limite = _maintenant() - DUREE_VIE_SECONDES
    actifs = {t.get("_chemin") for t in _taches.values() if t["statut"] == "EN_COURS"}
    if DOSSIER.exists():
        for f in DOSSIER.iterdir():
            try:
                if str(f) not in actifs and (tout or f.stat().st_mtime < limite):
                    f.unlink()
            except OSError:
                pass
    for tid, t in list(_taches.items()):
        if t["statut"] != "EN_COURS" and t.get("_fini", _maintenant()) < limite:
            _supprimer(t.get("_chemin"))
            _taches.pop(tid, None)
            _en_cours.pop(tid, None)
        elif t["type"] == "export" and t.get("fichier_disponible") and t.get("_fini", _maintenant()) < limite:
            _supprimer(t.get("_chemin"))
            t["fichier_disponible"] = False


async def _boucle() -> None:
    while True:
        await asyncio.sleep(600)
        try:
            nettoyer()
        except Exception:  # noqa: BLE001 — la boucle ne doit jamais s'arrêter
            logger.exception("Nettoyage des fichiers de transfert")


async def au_demarrage() -> None:
    """Au démarrage du serveur : fichiers temporaires d'une exécution précédente
    supprimés, puis nettoyage toutes les 10 minutes."""
    DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
    nettoyer(tout=True)
    if "boucle" not in _boucle_nettoyage or _boucle_nettoyage["boucle"].done():
        _boucle_nettoyage["boucle"] = asyncio.create_task(_boucle())


def _lancer(tache: dict, coroutine) -> None:
    _en_cours[tache["id"]] = asyncio.create_task(coroutine)


def _terminer(tache: dict, statut: str, erreur: Optional[str] = None) -> None:
    tache.update({"statut": statut, "erreur": erreur, "fin": now_iso(), "_fini": _maintenant()})
    if statut == "TERMINE":
        tache["progression"] = 100


# ---------------------------------------------------------------------------
# Ré-authentification et journal
# ---------------------------------------------------------------------------
async def journaliser(action: str, statut: str, user: dict, ip: str, **details: Any) -> None:
    """Trace de chaque export / import / téléchargement (jamais la phrase secrète)."""
    ligne = {"id": new_id(), "date": now_iso(), "action": action, "statut": statut,
             "user_id": user.get("id"), "email": user.get("email", ""), "ip": ip, **details}
    try:
        await db[JOURNAL].insert_one(ligne)
    except PyMongoError:
        logger.exception("Journal des transferts indisponible")


async def verifier_mot_de_passe(user: dict, mot_de_passe: str, action: str, ip: str) -> None:
    """Chaque action exige le mot de passe du super-administrateur (vérifié ici,
    côté serveur). Après 5 erreurs en 15 minutes, l'action est bloquée."""
    depuis = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    echecs = await db[JOURNAL].count_documents({"user_id": user.get("id"), "statut": "MOT_DE_PASSE_REFUSE",
                                                "date": {"$gte": depuis}})
    if echecs >= MAX_ECHECS_MOT_DE_PASSE:
        raise HTTPException(429, "Trop de mots de passe erronés : réessayez dans 15 minutes")
    ok = bool(mot_de_passe) and await asyncio.to_thread(verify_password, mot_de_passe, user.get("password_hash", ""))
    if not ok:
        await journaliser(action, "MOT_DE_PASSE_REFUSE", user, ip)
        raise HTTPException(403, "Mot de passe incorrect")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def _nom_fichier_export() -> str:
    nom_base = re.sub(r"[^A-Za-z0-9_-]+", "_", get_settings().mongo_db_name) or "base"
    return f"adlyn_{nom_base}_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}{EXTENSION}"


async def lancer_export(user: dict, phrase: str, ip: str) -> dict:
    tache = _nouvelle_tache("export", user)
    tache.update({"fichier_nom": _nom_fichier_export(), "fichier_disponible": False, "taille": 0})
    tache["_chemin"] = str(DOSSIER / f"{tache['id']}{EXTENSION}")
    await journaliser("export", "DEMARRE", user, ip, tache=tache["id"])
    _lancer(tache, _executer_export(tache, phrase, user, ip))
    return tache


async def _executer_export(tache: dict, phrase: str, user: dict, ip: str) -> None:
    chemin = tache["_chemin"]
    partiel = chemin + ".partiel"
    try:
        DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
        base = base_brute()
        noms = sorted(n for n in await base.list_collection_names() if not n.startswith("system."))
        tache["documents_total"] = sum([await base[n].estimated_document_count() for n in noms])
        collections: list[dict] = []
        tache["etape"] = "Préparation du chiffrement…"
        with open(partiel, "wb") as fichier:
            ecrivain = await asyncio.to_thread(chiffrement_flux.EcrivainChiffre, fichier, phrase)
            # zipfile écrit en « flux » (sans retour en arrière) dans le fichier chiffré
            archive = zipfile.ZipFile(ecrivain, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6)
            for nom in noms:
                tache["etape"] = f"Export de « {nom} »…"
                collection = base[nom]
                index = [dict(i) async for i in collection.list_indexes()]
                compte = 0
                with archive.open(f"collections/{nom}.jsonl", "w", force_zip64=True) as entree:
                    lignes: list[str] = []
                    async for doc in collection.find({}, batch_size=LOT):
                        lignes.append(json_util.dumps(doc, json_options=CANONICAL_JSON_OPTIONS, ensure_ascii=False))
                        if len(lignes) >= LOT:
                            await asyncio.to_thread(entree.write, ("\n".join(lignes) + "\n").encode("utf-8"))
                            compte += len(lignes)
                            tache["documents_traites"] += len(lignes)
                            tache["progression"] = _pourcentage(tache)
                            lignes = []
                    if lignes:
                        await asyncio.to_thread(entree.write, ("\n".join(lignes) + "\n").encode("utf-8"))
                        compte += len(lignes)
                        tache["documents_traites"] += len(lignes)
                        tache["progression"] = _pourcentage(tache)
                collections.append({"nom": nom, "fichier": f"collections/{nom}.jsonl", "documents": compte,
                                    "index": index})
            manifest = {"application": APPLICATION, "version_format": VERSION_FORMAT,
                        "base": get_settings().mongo_db_name, "prefixe": _prefixe(),
                        "date_utc": datetime.now(timezone.utc).isoformat(), "collections": collections}
            archive.writestr("manifest.json", json_util.dumps(manifest, json_options=CANONICAL_JSON_OPTIONS,
                                                             ensure_ascii=False, indent=2).encode("utf-8"))
            await asyncio.to_thread(archive.close)
            await asyncio.to_thread(ecrivain.fermer_flux)
        os.replace(partiel, chemin)
        total = sum(c["documents"] for c in collections)
        tache.update({"etape": "Export terminé : le fichier est prêt à être téléchargé", "fichier_disponible": True,
                      "taille": os.path.getsize(chemin), "documents_traites": total, "documents_total": total,
                      "rapport": {"collections": [{"nom": c["nom"], "documents": c["documents"]} for c in collections],
                                  "documents": total}})
        _terminer(tache, "TERMINE")
        await journaliser("export", "TERMINE", user, ip, tache=tache["id"], collections=len(collections),
                          documents=total, taille=tache["taille"])
    except Exception as exc:  # noqa: BLE001 — l'erreur est rapportée à l'administrateur
        logger.exception("Échec de l'export complet")
        _supprimer(partiel)
        _supprimer(chemin)
        _terminer(tache, "ECHEC", f"L'export a échoué : {exc}" if not isinstance(exc, ErreurTransfert) else str(exc))
        await journaliser("export", "ECHEC", user, ip, tache=tache["id"], erreur=str(exc)[:300])


def _pourcentage(tache: dict) -> int:
    total = tache["documents_total"] or 1
    return min(99, int(tache["documents_traites"] * 100 / total))


async def fichier_export(tache_id: str, user: dict, ip: str) -> tuple[str, str]:
    """Chemin et nom du fichier d'export à télécharger (une seule fois)."""
    tache = lire_tache(tache_id)
    if tache["type"] != "export" or tache["statut"] != "TERMINE" or not tache.get("fichier_disponible"):
        raise HTTPException(404, "Fichier indisponible (déjà téléchargé ou expiré) : relancez l'export")
    if not os.path.exists(tache["_chemin"]):
        tache["fichier_disponible"] = False
        raise HTTPException(404, "Fichier expiré : relancez l'export")
    await journaliser("telechargement_export", "TERMINE", user, ip, tache=tache_id, taille=tache.get("taille"))
    return tache["_chemin"], tache["fichier_nom"]


def apres_telechargement(tache_id: str) -> None:
    """Le fichier d'export est supprimé du serveur dès qu'il a été envoyé."""
    tache = _taches.get(tache_id)
    if tache:
        _supprimer(tache.get("_chemin"))
        tache["fichier_disponible"] = False


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
async def preparer_import(user: dict, upload, phrase: str, mode: str, ip: str) -> dict:
    """Enregistre le fichier envoyé sur le disque (par morceaux), contrôle la
    phrase secrète, puis lance l'import en tâche de fond."""
    tache = _nouvelle_tache("import", user)
    chemin = str(DOSSIER / f"{tache['id']}.import")
    tache.update({"mode": mode, "fichier_nom": getattr(upload, "filename", "") or "", "_chemin": chemin})
    try:
        DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
        tache["etape"] = "Réception du fichier…"
        taille = 0
        with open(chemin, "wb") as f:
            while True:
                morceau = await upload.read(1024 * 1024)
                if not morceau:
                    break
                taille += len(morceau)
                if taille > TAILLE_MAX_IMPORT:
                    raise HTTPException(413, "Fichier trop volumineux")
                await asyncio.to_thread(f.write, morceau)
        tache["taille"] = taille

        def _controle() -> None:
            with open(chemin, "rb") as f:
                chiffrement_flux.ouvrir_cle(chiffrement_flux.lire_entete(f), phrase)

        try:
            await asyncio.to_thread(_controle)
        except chiffrement_flux.ErreurChiffrement as exc:
            raise HTTPException(400, str(exc)) from exc
    except BaseException:
        _supprimer(chemin)
        _taches.pop(tache["id"], None)
        raise
    await journaliser("import", "DEMARRE", user, ip, tache=tache["id"], mode=mode, taille=taille)
    _lancer(tache, _executer_import(tache, phrase, mode, user, ip))
    return tache


def _valider_manifest(manifest: Any, archive: zipfile.ZipFile) -> list[dict]:
    if not isinstance(manifest, dict) or manifest.get("application") != APPLICATION:
        raise ErreurTransfert("Ce fichier ne provient pas d'adLyn")
    if manifest.get("version_format") != VERSION_FORMAT:
        raise ErreurTransfert(f"Version du fichier non prise en charge ({manifest.get('version_format')})")
    collections = manifest.get("collections")
    if not isinstance(collections, list):
        raise ErreurTransfert("Fichier invalide : liste des collections absente")
    noms = archive.namelist()
    vus = set()
    for c in collections:
        nom = c.get("nom") if isinstance(c, dict) else None
        if (not isinstance(nom, str) or not nom or len(nom) > 200 or "$" in nom or "\0" in nom
                or nom.startswith("system.") or nom in vus):
            raise ErreurTransfert(f"Fichier invalide : nom de collection incorrect ({nom!r})")
        vus.add(nom)
        if c.get("fichier") != f"collections/{nom}.jsonl" or c["fichier"] not in noms:
            raise ErreurTransfert(f"Fichier invalide : données de « {nom} » absentes")
        if not isinstance(c.get("documents"), int) or not isinstance(c.get("index", []), list):
            raise ErreurTransfert(f"Fichier invalide : description de « {nom} » incorrecte")
    return collections


async def _remplacable(base, nom: str) -> bool:
    """Mode « base vide » : une collection technique déjà remplie au démarrage
    peut-elle être remplacée sans risque ? (voir la docstring du module)"""
    logique = _logique(nom)
    collection = base[nom]
    if logique == "users":
        return await collection.count_documents({"role": {"$ne": "super_admin"}}) == 0
    if logique == "formules":
        codes = [f["code"] for f in FORMULES_PAR_DEFAUT]
        return await collection.count_documents({"code": {"$nin": codes}}) == 0
    return logique in TECHNIQUES_REMPLACEES or logique in TECHNIQUES_FUSIONNEES


def definition_vers_index(definition: dict) -> tuple[list, dict]:
    """Transforme une définition renvoyée par list_indexes en arguments de
    create_index. Index texte : MongoDB les décrit avec les clés internes
    « _fts / _ftsx » ; les champs indexés sont alors reconstruits depuis
    `weights`."""
    cle = list(dict(definition["key"]).items())
    noms = [k for k, _ in cle]
    if "_fts" in noms:
        poids = dict(definition.get("weights") or {})
        # Champs ordinaires placés avant _fts (préfixe) et après _ftsx (suffixe)
        debut_texte = noms.index("_fts")
        fin_texte = noms.index("_ftsx") if "_ftsx" in noms else debut_texte
        avant = [(k, v) for k, v in cle[:debut_texte]]
        apres = [(k, v) for k, v in cle[fin_texte + 1:] if k not in ("_fts", "_ftsx")]
        cle = avant + [(champ, "text") for champ in poids] + apres
    options = {k: v for k, v in dict(definition).items() if k not in _OPTIONS_INDEX_IGNOREES}
    return cle, options


def _lecteur_lignes(archive: zipfile.ZipFile, fichier: str):
    """Documents d'un fichier .jsonl, lus ligne par ligne (jamais en entier)."""
    with archive.open(fichier) as flux:
        while True:
            ligne = flux.readline(LIGNE_MAX + 1)
            if not ligne:
                return
            if len(ligne) > LIGNE_MAX:
                raise ErreurTransfert(f"Document trop volumineux dans {fichier}")
            ligne = ligne.strip()
            if ligne:
                yield json_util.loads(ligne.decode("utf-8"), json_options=CANONICAL_JSON_OPTIONS)


def _lot_suivant(generateur) -> list:
    lot = []
    for doc in generateur:
        lot.append(doc)
        if len(lot) >= LOT:
            break
    return lot


async def _executer_import(tache: dict, phrase: str, mode: str, user: dict, ip: str) -> None:
    chemin = tache["_chemin"]
    lecteur = archive = None
    try:
        # 1. Vérification COMPLÈTE du fichier avant de toucher à la base
        tache["etape"] = "Vérification du fichier (déchiffrement)…"

        def _progression(lu: int, total: int) -> None:
            tache["progression"] = min(20, int(lu * 20 / max(total, 1)))

        try:
            lecteur = await asyncio.to_thread(chiffrement_flux.LecteurChiffre, chemin, phrase, _progression)
            archive = await asyncio.to_thread(zipfile.ZipFile, lecteur)
            info = archive.getinfo("manifest.json")
            if info.file_size > MANIFEST_MAX:
                raise ErreurTransfert("Fichier invalide : description trop volumineuse")
            manifest = json_util.loads((await asyncio.to_thread(archive.read, "manifest.json")).decode("utf-8"),
                                       json_options=CANONICAL_JSON_OPTIONS)
        except chiffrement_flux.ErreurChiffrement as exc:
            raise ErreurTransfert(str(exc)) from exc
        except (zipfile.BadZipFile, KeyError, ValueError) as exc:
            raise ErreurTransfert("Fichier invalide : contenu illisible") from exc
        collections = _valider_manifest(manifest, archive)
        tache["documents_total"] = sum(c["documents"] for c in collections)
        tache["source"] = {"base": manifest.get("base"), "date_utc": manifest.get("date_utc")}

        # 2. Contrôle de la base cible selon le mode choisi
        base = base_brute()
        tache["etape"] = "Contrôle de la base de destination…"
        existants = {c["nom"]: await base[c["nom"]].count_documents({}) for c in collections}
        if mode == "vide":
            bloquantes = [n for n, nb in existants.items() if nb and not await _remplacable(base, n)]
            if bloquantes:
                raise ErreurTransfert(
                    "La base de destination contient déjà des données (" + ", ".join(sorted(bloquantes)[:10])
                    + (" …" if len(bloquantes) > 10 else "") + "). Aucune donnée n'a été modifiée. "
                    "Choisissez le mode « Remplacer » si vous voulez écraser ces données.")

        # 3. Import collection par collection
        rapport: list[dict] = []
        avertissements: list[str] = []
        for c in collections:
            nom = c["nom"]
            collection = base[nom]
            tache["etape"] = f"Import de « {nom} »…"
            logique = _logique(nom)
            if existants[nom] and logique not in TECHNIQUES_FUSIONNEES:
                # « Remplacer », ou collection technique créée au démarrage (mode « base vide »)
                await collection.delete_many({})
            inseres = doublons = lus = 0
            generateur = _lecteur_lignes(archive, c["fichier"])
            while True:
                lot = await asyncio.to_thread(_lot_suivant, generateur)
                if not lot:
                    break
                lus += len(lot)
                try:
                    resultat = await collection.insert_many(lot, ordered=False)
                    inseres += len(resultat.inserted_ids)
                except BulkWriteError as exc:
                    details = exc.details or {}
                    inseres += details.get("nInserted", 0)
                    erreurs = details.get("writeErrors", [])
                    doublons += sum(1 for e in erreurs if e.get("code") == 11000)
                    autres = [e for e in erreurs if e.get("code") != 11000]
                    if autres:
                        avertissements.append(f"{nom} : {len(autres)} document(s) refusé(s) ({autres[0].get('errmsg', '')[:120]})")
                tache["documents_traites"] += len(lot)
                tache["progression"] = 20 + int(tache["documents_traites"] * 75 / max(tache["documents_total"], 1))
            if doublons and logique not in TECHNIQUES_FUSIONNEES:
                avertissements.append(f"{nom} : {doublons} document(s) en double ignoré(s)")
            if lus != c["documents"]:
                avertissements.append(f"{nom} : {lus} document(s) lu(s) au lieu de {c['documents']} annoncé(s)")
            # Index (sauf _id_, créé d'office) — un index déjà présent et identique est sans effet
            index_crees = 0
            for definition in c.get("index", []):
                if definition.get("name") == "_id_":
                    continue
                try:
                    cle, options = definition_vers_index(definition)
                    await collection.create_index(cle, **options)
                    index_crees += 1
                except Exception as exc:  # noqa: BLE001 — signalé dans le rapport
                    avertissements.append(f"{nom} : index « {definition.get('name')} » non recréé ({str(exc)[:120]})")
            rapport.append({"nom": nom, "attendus": c["documents"], "importes": inseres,
                            "dans_la_base": await collection.count_documents({}), "index": index_crees})

        # 4. Comparaison des nombres de documents
        tache["etape"] = "Vérification des nombres de documents…"
        ecarts = [r["nom"] for r in rapport if r["dans_la_base"] < r["attendus"]
                  or (_logique(r["nom"]) not in TECHNIQUES_FUSIONNEES and r["dans_la_base"] != r["attendus"])]
        for nom in ecarts:
            avertissements.append(f"{nom} : le nombre de documents ne correspond pas au fichier")
        if manifest.get("base") != get_settings().mongo_db_name:
            avertissements.append(f"Base d'origine « {manifest.get('base')} », importée dans « {get_settings().mongo_db_name} »")
        tache["rapport"] = {"collections": rapport, "avertissements": avertissements, "conforme": not ecarts,
                            "documents": sum(r["importes"] for r in rapport)}
        tache["etape"] = "Import terminé"
        _terminer(tache, "TERMINE")
        await journaliser("import", "TERMINE", user, ip, tache=tache["id"], mode=mode, collections=len(rapport),
                          documents=tache["rapport"]["documents"], ecarts=ecarts)
    except Exception as exc:  # noqa: BLE001 — l'erreur est rapportée à l'administrateur
        if not isinstance(exc, ErreurTransfert):
            logger.exception("Échec de l'import complet")
        message = str(exc) if isinstance(exc, ErreurTransfert) else f"L'import a échoué : {exc}"
        _terminer(tache, "ECHEC", message)
        await journaliser("import", "ECHEC", user, ip, tache=tache["id"], mode=mode, erreur=message[:300])
    finally:
        for objet in (archive, lecteur):
            if objet is not None:
                try:
                    objet.close()
                except Exception:  # noqa: BLE001
                    pass
        _supprimer(chemin)  # le fichier importé ne reste jamais sur le serveur


# ---------------------------------------------------------------------------
# Informations pour la page d'administration
# ---------------------------------------------------------------------------
async def etat_base() -> dict:
    base = base_brute()
    noms = [n for n in await base.list_collection_names() if not n.startswith("system.")]
    documents = 0
    for n in noms:
        documents += await base[n].estimated_document_count()
    active = tache_active()
    historique = await db[JOURNAL].find({}, SANS_ID).sort("date", -1).to_list(20)
    return {"base": get_settings().mongo_db_name, "collections": len(noms), "documents": documents,
            "tache_en_cours": publique(active) if active else None, "historique": historique,
            "phrase_min": chiffrement_flux.PHRASE_MIN, "extension": EXTENSION}


# Dossier temporaire privé, créé dès le chargement du module
try:
    DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
except OSError:  # pragma: no cover — disque en lecture seule : créé plus tard
    pass
