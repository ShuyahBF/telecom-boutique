"""Connexion MongoDB (Motor) : préfixage automatique des collections ET
cloisonnement automatique par boutique (multi-tenant).

Deux niveaux de protection, pour qu'un oubli soit impossible :

1. `db.<nom>` -> collection `tlb_<nom>` (comme beauthentik : le cluster
   Atlas est partagé avec d'autres projets).
2. `TenantDB(boutique_id).<nom>` -> la même collection, mais CHAQUE lecture,
   écriture ou suppression est automatiquement limitée aux documents de
   cette boutique (le filtre `boutique_id` est ajouté par le code, jamais
   fourni par l'utilisateur). Toutes les routes métier passent par
   TenantDB : une boutique ne peut donc jamais lire les données d'une autre.
"""
from __future__ import annotations

from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ReturnDocument

from config import get_settings

# Projection par défaut : on ne renvoie jamais le champ interne "_id" de MongoDB
SANS_ID = {"_id": 0}


class PrefixedDatabase:
    def __init__(self, database: AsyncIOMotorDatabase, prefix: str):
        self._database = database
        self._prefix = prefix

    def __getattr__(self, name: str) -> AsyncIOMotorCollection:
        return self._database[f"{self._prefix}{name}"]

    def __getitem__(self, name: str) -> AsyncIOMotorCollection:
        return self._database[f"{self._prefix}{name}"]


def _make_client(mongo_url: str):
    # MONGO_URL=mongomock:// -> base EN MÉMOIRE (tests, développement sans
    # réseau). Ne jamais utiliser en production : rien n'est conservé.
    if mongo_url.startswith("mongomock://"):
        from mongomock_motor import AsyncMongoMockClient

        return AsyncMongoMockClient()
    from motor.motor_asyncio import AsyncIOMotorClient

    return AsyncIOMotorClient(mongo_url)


_settings = get_settings()
_client = _make_client(_settings.mongo_url)
_raw_db = _client[_settings.mongo_db_name]

db = PrefixedDatabase(_raw_db, _settings.mongo_collection_prefix)


class TenantCollection:
    """Collection vue « depuis une boutique » : le filtre boutique_id est
    ajouté à toutes les opérations, et imposé à tous les documents insérés."""

    def __init__(self, collection: AsyncIOMotorCollection, boutique_id: str):
        self._c = collection
        self.boutique_id = boutique_id

    def _f(self, filtre: Optional[dict]) -> dict:
        # Le boutique_id est posé EN DERNIER : il écrase toute valeur qui
        # aurait pu se glisser dans le filtre fourni.
        return {**(filtre or {}), "boutique_id": self.boutique_id}

    async def find_one(self, filtre: Optional[dict] = None, projection: Optional[dict] = None, **kw):
        return await self._c.find_one(self._f(filtre), projection or SANS_ID, **kw)

    def find(self, filtre: Optional[dict] = None, projection: Optional[dict] = None, **kw):
        return self._c.find(self._f(filtre), projection or SANS_ID, **kw)

    async def count_documents(self, filtre: Optional[dict] = None) -> int:
        return await self._c.count_documents(self._f(filtre))

    async def insert_one(self, doc: dict):
        doc = {**doc, "boutique_id": self.boutique_id}
        # copy() : Motor ajoute "_id" au dictionnaire inséré, on garde l'original propre
        return await self._c.insert_one(doc.copy())

    async def update_one(self, filtre: dict, maj: dict, **kw):
        return await self._c.update_one(self._f(filtre), maj, **kw)

    async def update_many(self, filtre: dict, maj: dict, **kw):
        return await self._c.update_many(self._f(filtre), maj, **kw)

    async def find_one_and_update(self, filtre: dict, maj: dict, apres: bool = True, **kw):
        doc = await self._c.find_one_and_update(
            self._f(filtre), maj,
            return_document=ReturnDocument.AFTER if apres else ReturnDocument.BEFORE, **kw,
        )
        # "_id" retiré ici plutôt que par projection (la base de test en
        # mémoire renvoie None quand on combine projection et AFTER)
        if doc:
            doc.pop("_id", None)
        return doc

    async def delete_one(self, filtre: dict):
        return await self._c.delete_one(self._f(filtre))

    async def delete_many(self, filtre: Optional[dict] = None):
        return await self._c.delete_many(self._f(filtre))


class TenantDB:
    """Accès aux données d'UNE boutique : `tdb.produits.find(...)`."""

    def __init__(self, boutique_id: str):
        if not boutique_id:
            raise ValueError("boutique_id obligatoire")
        self.boutique_id = boutique_id

    def __getattr__(self, name: str) -> TenantCollection:
        return TenantCollection(db[name], self.boutique_id)


async def index_identifiants(users: AsyncIOMotorCollection) -> None:
    """Index d'unicité des identifiants de connexion (e-mail, téléphone), chacun
    FACULTATIF : index « partiel », un compte sans e-mail n'entre pas dans l'index
    de l'e-mail. L'ancien index « email_1 » (e-mail obligatoire) est remplacé."""
    existants = await users.index_information()
    if "email_1" in existants and not existants["email_1"].get("partialFilterExpression"):
        await users.drop_index("email_1")
    await users.create_index("email", unique=True, name="email_connexion",
                             partialFilterExpression={"email": {"$type": "string"}})
    await users.create_index("telephone", unique=True, name="telephone_connexion",
                             partialFilterExpression={"telephone": {"$type": "string"}})


async def ensure_indexes() -> None:
    # Plateforme
    await db.boutiques.create_index("id", unique=True)
    await db.boutiques.create_index("slug", unique=True)
    await db.boutiques.create_index("code_marchand", unique=True)
    # Identifiants de connexion : e-mail ET téléphone uniques sur toute la plateforme,
    # mais chacun FACULTATIF (index « partiel » : un compte sans e-mail n'entre pas
    # dans l'index de l'e-mail). L'ancien index (e-mail obligatoire) est remplacé.
    await index_identifiants(db.users)
    # Codes de vérification, limites d'envoi, blocages : effacés automatiquement à expiration
    await db.codes_verification.create_index([("user_id", 1), ("objet", 1)])
    await db.codes_verification.create_index("expire_le", expireAfterSeconds=0)
    for collection in (db.limites_codes, db.echecs_codes, db.blocages_codes):
        await collection.create_index([("cle", 1), ("date", 1)])
        await collection.create_index("expire_le", expireAfterSeconds=0)
    await db.journal_identifiants.create_index([("boutique_id", 1), ("date", -1)])
    # Connexion (anti force brute) et webhook (anti-rejeu : nonces effacés après 7 jours)
    await db.echecs_connexion.create_index([("cle", 1), ("date", 1)])
    await db.echecs_connexion.create_index("expire_le", expireAfterSeconds=0)
    await db.webhook_journal.create_index([("ip", 1), ("date", -1)])
    await db.webhook_nonces.create_index("expire_le", expireAfterSeconds=0)
    await db.compteurs.create_index([("boutique_id", 1), ("prefixe", 1), ("annee", 1)], unique=True)
    # Données des boutiques : toujours indexées en commençant par boutique_id
    await db.produits.create_index([("boutique_id", 1), ("reference", 1)], unique=True)
    await db.produits.create_index([("boutique_id", 1), ("slug", 1)])
    await db.categories.create_index([("boutique_id", 1), ("ordre", 1)])
    await db.clients.create_index([("boutique_id", 1), ("telephone", 1)])
    await db.fournisseurs.create_index([("boutique_id", 1), ("nom", 1)])
    await db.mouvements.create_index([("boutique_id", 1), ("date", -1)])
    await db.mouvements.create_index([("boutique_id", 1), ("produit_id", 1)])
    await db.bons_entree.create_index([("boutique_id", 1), ("date", -1)])
    await db.documents.create_index([("boutique_id", 1), ("date", -1)])
    await db.documents.create_index([("boutique_id", 1), ("numero", 1)])
    await db.commandes.create_index([("boutique_id", 1), ("numero", 1)], unique=True)
    await db.dossiers.create_index([("boutique_id", 1), ("numero", 1)], unique=True)
    await db.conversations.create_index("jeton", unique=True)
    await db.conversations.create_index([("boutique_id", 1), ("date_maj", -1)])
    await db.modeles_messages.create_index([("boutique_id", 1), ("code", 1)], unique=True)
    await db.journal_envois.create_index([("boutique_id", 1), ("date", -1)])
    await db.paiements.create_index("deposit_id", unique=True)
    # Abonnements
    await db.formules.create_index("code", unique=True)
    await db.abonnement_paiements.create_index([("boutique_id", 1), ("created_at", -1)])
    await db.abonnement_rappels_journal.create_index("date")
    # Journal des connexions au back-office des boutiques
    await db.connexions_journal.create_index([("boutique_id", 1), ("date", -1)])
    # Reversements PawaPay aux boutiques
    await db.paiements.create_index([("boutique_id", 1), ("statut", 1), ("reversement_id", 1)])
    await db.reversements.create_index([("boutique_id", 1), ("created_at", -1)])
    # Service SMS
    await db.sms_envois.create_index([("boutique_id", 1), ("telephone", 1), ("date", -1)])
    await db.sms_envois.create_index([("statut", 1), ("facture_id", 1), ("jour", 1)])
    await db.sms_factures.create_index([("boutique_id", 1), ("created_at", -1)])
    # Référentiel mondial des appareils
    # En base de test en mémoire (mongomock), un index d'unicité rend l'import des
    # ~40 000 appareils extrêmement lent : index simple dans ce cas seulement
    # (l'unicité est de toute façon garantie par le code d'import).
    await db.referentiel_appareils.create_index("cle", unique=not _settings.mongo_url.startswith("mongomock://"))
    await db.referentiel_appareils.create_index([("marque", 1), ("nom", 1)])
    await db.paiements.create_index([("statut", 1), ("created_at", 1)])
    # Parrainage entre boutiques : une boutique n'a qu'un parrain ; journal des bonus
    await db.parrainages.create_index("filleul_id", unique=True)
    await db.parrainages.create_index([("parrain_id", 1), ("created_at", -1)])
    await db.bonus_mouvements.create_index([("boutique_id", 1), ("created_at", -1)])
    await db.bonus_mouvements.create_index("reference")
    # Maintenance des équipements : fiches par espace (boutique ou « plateforme ») et lien de paiement public
    await db.maintenance_fiches.create_index([("boutique_id", 1), ("date_reception", -1)])
    await db.maintenance_fiches.create_index("lien_paiement.jeton")
    await db.maintenance_types.create_index([("boutique_id", 1), ("libelle", 1)])
