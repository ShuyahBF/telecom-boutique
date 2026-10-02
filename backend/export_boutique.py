"""Export, vérification, suppression et restauration des données d'UNE SEULE boutique
au format chiffré des exports complets (.adlexport, voir chiffrement_flux.py et
transfert_donnees.py). Utilisé par le cycle de vie du non-renouvellement (cycle_vie.py).

Quelles données ?
  Toutes les collections du projet (préfixe MONGO_COLLECTION_PREFIX) qui contiennent
  au moins un document portant `boutique_id` = la boutique : elles sont DÉTECTÉES à
  chaque export (aucune liste à tenir à jour quand une nouvelle collection apparaît).
  À la date d'écriture : categories, produits, clients, fournisseurs, mouvements,
  bons_entree, documents, commandes, dossiers, conversations, modeles_messages,
  journal_envois, journal_paiements, maintenance_fiches, maintenance_types,
  caisse_operations, caisse_arrets, caisse_types_paiement, caisse_jetons,
  caisse_receptions, users (les COMPTES de la boutique), compteurs, paiements,
  reversements, sms_envois, sms_factures, sauvegardes, bonus_mouvements,
  abonnement_paiements, abonnement_grace_journal, connexions_journal,
  journal_identifiants, options_sidebar_journal, sessions_activite...
  + la fiche de la boutique elle-même (collection boutiques, filtre `id`).

Règles :
  - NON_ARCHIVEES : traces techniques éphémères (sessions ouvertes) : supprimées,
    jamais archivées ni restaurées ;
  - CONSERVEES : pièces comptables et journaux de la PLATEFORME (paiements
    d'abonnement, factures SMS, reversements, journaux du cycle de vie et des rappels
    KYC) : archivés, mais JAMAIS supprimés ni remplacés (ils restent consultables par
    le super-administrateur et ne sont pas écrasés à la réouverture) ;
  - la fiche de la boutique n'est jamais supprimée (elle passe au statut « ARCHIVÉ »).

Format : archive ZIP chiffrée (même chiffrement que l'export complet) contenant
manifest.json (application « adlyn », type « boutique », boutique_id, nombre de
documents de chaque collection) et collections/<nom logique>.jsonl (Extended JSON
canonique, un document par ligne).
"""
from __future__ import annotations

import asyncio
import zipfile
from datetime import datetime, timezone
from typing import Any

from bson import json_util
from bson.json_util import CANONICAL_JSON_OPTIONS
from pymongo.errors import BulkWriteError

import chiffrement_flux
import transfert_donnees
from config import get_settings

TYPE_ARCHIVE = "boutique"
VERSION_FORMAT = 1
COLLECTION_FICHE = "boutiques"
NON_ARCHIVEES = ("sessions_activite",)
CONSERVEES = ("abonnement_paiements", "sms_factures", "reversements", "cycle_vie_journal",
              "cycle_vie_archives", "cycle_vie_reouvertures", "kyc_rappels_journal")
LOT = transfert_donnees.LOT


class ErreurArchive(Exception):
    """Erreur expliquée au super-administrateur (message en français)."""


def _prefixe() -> str:
    return get_settings().mongo_collection_prefix


def _base():
    return transfert_donnees.base_brute()


def _filtre(logique: str, boutique_id: str) -> dict:
    return {"id": boutique_id} if logique == COLLECTION_FICHE else {"boutique_id": boutique_id}


async def collections_de(boutique_id: str) -> list[str]:
    """Noms LOGIQUES (sans préfixe) des collections contenant des données de la boutique."""
    base, p = _base(), _prefixe()
    trouvees = []
    for nom in sorted(await base.list_collection_names()):
        if nom.startswith("system.") or (p and not nom.startswith(p)):
            continue  # cluster partagé : jamais les collections des autres projets
        logique = nom[len(p):] if p else nom
        if logique in NON_ARCHIVEES:
            continue
        if await base[nom].count_documents(_filtre(logique, boutique_id), limit=1):
            trouvees.append(logique)
    if COLLECTION_FICHE not in trouvees:
        raise ErreurArchive("Fiche de la boutique introuvable")
    return trouvees


async def compter(boutique_id: str, noms: list[str]) -> dict[str, int]:
    base, p = _base(), _prefixe()
    return {n: await base[p + n].count_documents(_filtre(n, boutique_id)) for n in noms}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
async def exporter(boutique_id: str, phrase: str, chemin: str) -> dict:
    """Écrit l'archive chiffrée de la boutique dans `chemin` ; renvoie le manifeste."""
    base, p = _base(), _prefixe()
    noms = await collections_de(boutique_id)
    collections: list[dict] = []
    with open(chemin, "wb") as fichier:
        ecrivain = await asyncio.to_thread(chiffrement_flux.EcrivainChiffre, fichier, phrase)
        archive = zipfile.ZipFile(ecrivain, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6)
        for nom in noms:
            compte = 0
            with archive.open(f"collections/{nom}.jsonl", "w", force_zip64=True) as entree:
                lignes: list[str] = []
                async for doc in base[p + nom].find(_filtre(nom, boutique_id), batch_size=LOT):
                    lignes.append(json_util.dumps(doc, json_options=CANONICAL_JSON_OPTIONS, ensure_ascii=False))
                    if len(lignes) >= LOT:
                        await asyncio.to_thread(entree.write, ("\n".join(lignes) + "\n").encode("utf-8"))
                        compte += len(lignes)
                        lignes = []
                if lignes:
                    await asyncio.to_thread(entree.write, ("\n".join(lignes) + "\n").encode("utf-8"))
                    compte += len(lignes)
            collections.append({"nom": nom, "fichier": f"collections/{nom}.jsonl", "documents": compte})
        manifest = {"application": transfert_donnees.APPLICATION, "type": TYPE_ARCHIVE,
                    "version_format": VERSION_FORMAT, "boutique_id": boutique_id, "prefixe": p,
                    "date_utc": datetime.now(timezone.utc).isoformat(), "collections": collections}
        archive.writestr("manifest.json", json_util.dumps(manifest, json_options=CANONICAL_JSON_OPTIONS,
                                                         ensure_ascii=False, indent=2).encode("utf-8"))
        await asyncio.to_thread(archive.close)
        await asyncio.to_thread(ecrivain.fermer_flux)
    return manifest


# ---------------------------------------------------------------------------
# Lecture / vérification
# ---------------------------------------------------------------------------
def _ouvrir(chemin: str, phrase: str) -> tuple[Any, zipfile.ZipFile, dict]:
    try:
        lecteur = chiffrement_flux.LecteurChiffre(chemin, phrase)
    except chiffrement_flux.ErreurChiffrement as exc:
        raise ErreurArchive(f"Archive illisible : {exc}") from exc
    try:
        archive = zipfile.ZipFile(lecteur)
        manifest = json_util.loads(archive.read("manifest.json").decode("utf-8"), json_options=CANONICAL_JSON_OPTIONS)
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        lecteur.close()
        raise ErreurArchive("Archive invalide : contenu illisible") from exc
    if not isinstance(manifest, dict) or manifest.get("application") != transfert_donnees.APPLICATION \
            or manifest.get("type") != TYPE_ARCHIVE or manifest.get("version_format") != VERSION_FORMAT:
        archive.close()
        lecteur.close()
        raise ErreurArchive("Ce fichier n'est pas une archive de boutique adLyn")
    return lecteur, archive, manifest


def _compter_lignes(archive: zipfile.ZipFile, fichier: str) -> int:
    return sum(1 for _ in transfert_donnees._lecteur_lignes(archive, fichier))  # noqa: SLF001


def _verifier_sync(chemin: str, phrase: str, boutique_id: str, attendus: dict[str, int]) -> dict:
    lecteur, archive, manifest = _ouvrir(chemin, phrase)
    try:
        if manifest.get("boutique_id") != boutique_id:
            raise ErreurArchive("L'archive ne correspond pas à cette boutique")
        lus = {c["nom"]: _compter_lignes(archive, c["fichier"]) for c in manifest.get("collections", [])}
    finally:
        archive.close()
        lecteur.close()
    ecarts = sorted(n for n in set(lus) | set(attendus) if lus.get(n) != attendus.get(n))
    return {"conforme": not ecarts, "ecarts": ecarts, "documents": lus, "total": sum(lus.values())}


async def verifier(chemin: str, phrase: str, boutique_id: str, attendus: dict[str, int]) -> dict:
    """Déchiffre ENTIÈREMENT l'archive et compare le nombre de documents de chaque
    collection avec `attendus` (comptes relevés dans la base)."""
    return await asyncio.to_thread(_verifier_sync, chemin, phrase, boutique_id, attendus)


# ---------------------------------------------------------------------------
# Suppression et restauration (limitées à la boutique)
# ---------------------------------------------------------------------------
async def supprimer(boutique_id: str, noms: list[str]) -> dict[str, int]:
    """Supprime les données de la boutique (comptes compris), sauf sa fiche et les
    collections CONSERVEES ; les traces éphémères (NON_ARCHIVEES) sont aussi effacées."""
    base, p = _base(), _prefixe()
    supprimes = {}
    for nom in [*noms, *NON_ARCHIVEES]:
        if nom == COLLECTION_FICHE or nom in CONSERVEES:
            continue
        res = await base[p + nom].delete_many({"boutique_id": boutique_id})
        supprimes[nom] = res.deleted_count
    return supprimes


def _documents(archive: zipfile.ZipFile, fichier: str) -> list[dict]:
    return list(transfert_donnees._lecteur_lignes(archive, fichier))  # noqa: SLF001


async def restaurer(chemin: str, phrase: str, boutique_id: str) -> dict:
    """Mode « remplacement » LIMITÉ À LA BOUTIQUE : pour chaque collection de l'archive,
    les documents de cette boutique sont supprimés puis réinsérés depuis l'archive.
    Un document qui n'appartient pas à la boutique est refusé (jamais d'écriture chez
    une autre boutique). La fiche est renvoyée (champ « fiche ») sans être écrite :
    c'est l'appelant qui la fusionne avec l'état de réouverture."""
    lecteur, archive, manifest = await asyncio.to_thread(_ouvrir, chemin, phrase)
    base, p = _base(), _prefixe()
    rapport, avertissements, fiche = [], [], None
    try:
        if manifest.get("boutique_id") != boutique_id:
            raise ErreurArchive("L'archive ne correspond pas à cette boutique")
        # 1. Contrôle COMPLET avant toute écriture
        a_restaurer = []
        for c in manifest.get("collections", []):
            nom = c.get("nom") if isinstance(c, dict) else None
            if not isinstance(nom, str) or not nom or "$" in nom or "\0" in nom or nom.startswith("system.") \
                    or c.get("fichier") != f"collections/{nom}.jsonl":
                raise ErreurArchive(f"Archive invalide : nom de collection incorrect ({nom!r})")
            docs = await asyncio.to_thread(_documents, archive, c["fichier"])
            if nom == COLLECTION_FICHE:
                fiche = next((d for d in docs if d.get("id") == boutique_id), None)
                continue
            if nom in CONSERVEES or nom in NON_ARCHIVEES:
                continue  # jamais supprimées : rien à remettre
            etrangers = [d for d in docs if d.get("boutique_id") != boutique_id]
            if etrangers:
                raise ErreurArchive(f"Archive invalide : {len(etrangers)} document(s) d'une autre boutique dans « {nom} »")
            a_restaurer.append((nom, c.get("documents"), docs))
        if fiche is None:
            raise ErreurArchive("Archive invalide : fiche de la boutique absente")
        # 2. Remplacement collection par collection (filtre boutique_id uniquement)
        for nom, attendus, docs in a_restaurer:
            collection = base[p + nom]
            await collection.delete_many({"boutique_id": boutique_id})
            inseres = 0
            for i in range(0, len(docs), LOT):
                try:
                    inseres += len((await collection.insert_many(docs[i:i + LOT], ordered=False)).inserted_ids)
                except BulkWriteError as exc:
                    details = exc.details or {}
                    inseres += details.get("nInserted", 0)
                    erreurs = details.get("writeErrors", [])
                    avertissements.append(f"{nom} : {len(erreurs)} document(s) non restauré(s) "
                                          f"({(erreurs[0].get('errmsg', '') if erreurs else '')[:120]})")
            rapport.append({"nom": nom, "attendus": attendus, "restaures": inseres})
    finally:
        archive.close()
        lecteur.close()
    fiche.pop("_id", None)
    return {"collections": rapport, "avertissements": avertissements, "fiche": fiche,
            "documents": sum(r["restaures"] for r in rapport)}
