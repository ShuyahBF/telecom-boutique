"""Sauvegarde et restauration des données d'UNE boutique.

Format de l'archive (extension .tlb.gz.enc) :
  1. toutes les données de la boutique en JSON (fiche, comptes, produits,
     clients, factures, commandes, dossiers SAV, messagerie, paiements...) ;
  2. compressé en gzip ;
  3. chiffré en AES-256-GCM avec la clé SAUVEGARDE_CLE (variable
     d'environnement, jamais stockée dans le code ni en base).
  En-tête du fichier : b"TLB1" + nonce (12 octets) + données chiffrées.
Sans la clé, l'archive est illisible ; toute modification du fichier est
détectée à l'ouverture (AES-GCM authentifie le contenu).

Les images et documents (photos, PDF) restent dans Cloudflare R2 : l'archive
contient leurs adresses, pas les fichiers eux-mêmes.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException

from config import get_settings
from db import SANS_ID, TenantDB, db
from utils import now_iso

MAGIQUE = b"TLB1"
VERSION_FORMAT = 1

# Collections cloisonnées par boutique (toutes filtrées sur boutique_id)
COLLECTIONS_BOUTIQUE = (
    "categories", "produits", "clients", "fournisseurs", "mouvements", "bons_entree", "documents",
    "commandes", "dossiers", "conversations", "modeles_messages", "journal_envois", "journal_paiements",
)


def _cle() -> bytes:
    """Clé AES de 32 octets, fournie en base64 par SAUVEGARDE_CLE."""
    brute = get_settings().sauvegarde_cle
    if not brute:
        raise HTTPException(503, "Sauvegarde non configurée (variable SAUVEGARDE_CLE manquante)")
    try:
        cle = base64.b64decode(brute)
    except ValueError as exc:
        raise HTTPException(503, "SAUVEGARDE_CLE invalide (base64 attendu)") from exc
    if len(cle) != 32:
        raise HTTPException(503, "SAUVEGARDE_CLE doit faire 32 octets (256 bits)")
    return cle


def generer_cle() -> str:
    """Nouvelle clé à mettre dans SAUVEGARDE_CLE (python -c "import sauvegarde; print(sauvegarde.generer_cle())")."""
    return base64.b64encode(os.urandom(32)).decode()


async def exporter(boutique_id: str) -> dict:
    """Toutes les données de la boutique, sous forme de dictionnaire JSON."""
    boutique = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not boutique:
        raise HTTPException(404, "Boutique introuvable")
    tdb = TenantDB(boutique_id)
    donnees = {nom: await getattr(tdb, nom).find({}).to_list(None) for nom in COLLECTIONS_BOUTIQUE}
    return {
        "format": "telecom-boutique", "version": VERSION_FORMAT, "date": now_iso(),
        "boutique": boutique,
        "utilisateurs": await db.users.find({"boutique_id": boutique_id}, SANS_ID).to_list(None),
        "compteurs": await db.compteurs.find({"boutique_id": boutique_id}, SANS_ID).to_list(None),
        "paiements_pawapay": await db.paiements.find({"boutique_id": boutique_id}, SANS_ID).to_list(None),
        "collections": donnees,
    }


def chiffrer(donnees: dict) -> bytes:
    """JSON -> gzip -> AES-256-GCM."""
    brut = gzip.compress(json.dumps(donnees, ensure_ascii=False, default=str).encode("utf-8"), compresslevel=9)
    nonce = os.urandom(12)
    return MAGIQUE + nonce + AESGCM(_cle()).encrypt(nonce, brut, MAGIQUE)


def dechiffrer(archive: bytes) -> dict:
    if not archive.startswith(MAGIQUE) or len(archive) < 30:
        raise HTTPException(400, "Ce fichier n'est pas une sauvegarde TelecomBoutique")
    nonce, chiffre = archive[4:16], archive[16:]
    try:
        brut = AESGCM(_cle()).decrypt(nonce, chiffre, MAGIQUE)
    except Exception as exc:  # noqa: BLE001 — clé différente ou fichier modifié
        raise HTTPException(400, "Sauvegarde illisible : mauvaise clé ou fichier endommagé") from exc
    return json.loads(gzip.decompress(brut).decode("utf-8"))


def nom_fichier(boutique: dict) -> str:
    horodatage = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    return f"sauvegarde_{boutique['code_marchand']}_{horodatage}.tlb.gz.enc"


async def creer_archive(boutique_id: str) -> tuple[str, bytes]:
    donnees = await exporter(boutique_id)
    return nom_fichier(donnees["boutique"]), chiffrer(donnees)


async def restaurer(boutique_id: str, archive: bytes) -> dict:
    """Remplace TOUTES les données de la boutique par celles de l'archive.
    Refusé si l'archive appartient à une autre boutique."""
    donnees = dechiffrer(archive)
    if donnees.get("format") != "telecom-boutique":
        raise HTTPException(400, "Format de sauvegarde inconnu")
    if donnees["boutique"]["id"] != boutique_id:
        raise HTTPException(400, f"Cette sauvegarde appartient à la boutique « {donnees['boutique']['nom']} », pas à celle-ci")
    tdb = TenantDB(boutique_id)
    compte = {}
    for nom in COLLECTIONS_BOUTIQUE:
        collection = getattr(tdb, nom)
        await collection.delete_many({})
        documents = donnees["collections"].get(nom, [])
        for doc in documents:
            await collection.insert_one(doc)
        compte[nom] = len(documents)
    # Fiche de la boutique, comptes du personnel, compteurs de numérotation
    await db.boutiques.replace_one({"id": boutique_id}, donnees["boutique"])
    await db.users.delete_many({"boutique_id": boutique_id})
    for u in donnees.get("utilisateurs", []):
        await db.users.insert_one(dict(u))
    await db.compteurs.delete_many({"boutique_id": boutique_id})
    for c in donnees.get("compteurs", []):
        await db.compteurs.insert_one(dict(c))
    return {"date_sauvegarde": donnees["date"], "documents_restaures": compte}
