"""Catalogue PUBLIC commun à toutes les boutiques : téléphones, accessoires
et pièces détachées (avec les modèles de téléphones compatibles).

Fonctionnement :
1. L'administrateur de la plateforme saisit ou corrige des fiches dans la
   journée (collection `catalogue_modeles` = copie de travail). Un assistant
   de recherche (API Claude + recherche web sur les sites des fabricants)
   pré-remplit les fiches.
2. Chaque soir à 23h (réglable), les fiches « prêtes » sont PUBLIÉES
   (collection `catalogue_publie`, seule lue par les boutiques).
3. À la publication :
   - un NOUVEAU modèle est ajouté au catalogue de CHAQUE boutique, sans prix,
     invisible sur son portail, avec le badge « Nouveau » ;
   - un modèle MODIFIÉ met à jour les informations partagées (nom,
     caractéristiques, photo...) chez toutes les boutiques, sans jamais
     toucher à leurs prix, stocks ni documents privés.
4. À la création d'une boutique, tout le catalogue publié est copié chez elle.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError

from config import get_settings
from db import SANS_ID, TenantDB, db
from utils import new_id, now_iso, slugifier

logger = logging.getLogger(__name__)

# Rayon (catégorie) créé automatiquement chez la boutique selon le type
CATEGORIE_PAR_TYPE = {"TEL": "Smartphones", "PIE": "Pièces détachées", "ACC": "Accessoires", "SER": "Services"}

# Informations PARTAGÉES recopiées chez les boutiques (jamais : prix, stock, documents)
CHAMPS_PARTAGES = ("nom", "marque", "type_produit", "description", "caracteristiques", "annee_sortie")


def _instantane(modele: dict) -> dict:
    """Version publiée d'une fiche (ce que voient les boutiques)."""
    return {k: modele.get(k) for k in (
        "id", "reference", "nom", "marque", "type_produit", "annee_sortie", "photo_url", "description",
        "caracteristiques", "modeles_compatibles", "sources")}


async def _categorie_boutique(tdb: TenantDB, type_produit: str, cache: dict) -> dict:
    """Rayon de la boutique correspondant au type (créé s'il n'existe pas)."""
    nom = CATEGORIE_PAR_TYPE.get(type_produit, "Divers")
    if nom in cache:
        return cache[nom]
    cat = await tdb.categories.find_one({"nom": nom})
    if not cat:
        cat = {"id": new_id(), "nom": nom, "slug": slugifier(nom), "ordre": 0}
        await tdb.categories.insert_one(cat)
    cache[nom] = cat
    return cat


async def _compatibles_lisibles(ids: list[str]) -> list[dict]:
    """[id, ...] -> [{catalogue_id, nom}] pour afficher « compatible avec »."""
    if not ids:
        return []
    modeles = {m["id"]: m async for m in db.catalogue_publie.find({"id": {"$in": ids}}, SANS_ID)}
    return [{"catalogue_id": i, "nom": f"{modeles[i]['marque']} {modeles[i]['nom']}".strip()} for i in ids if i in modeles]


async def ajouter_a_boutique(boutique_id: str, publie: dict, nouveau: bool, cache: Optional[dict] = None) -> bool:
    """Copie une fiche publiée dans le catalogue d'une boutique (si absente).
    Le produit arrive SANS prix et INVISIBLE sur le portail : la boutique
    fixe son prix puis décide de le mettre en vente."""
    tdb = TenantDB(boutique_id)
    if await tdb.produits.find_one({"catalogue_id": publie["id"]}, {"_id": 0, "id": 1}):
        return False
    cache = cache if cache is not None else {}
    cat = await _categorie_boutique(tdb, publie["type_produit"], cache)
    reference = publie["reference"]
    if await tdb.produits.find_one({"reference": reference}, {"_id": 0, "id": 1}):
        reference = f"{reference}-CAT"  # la boutique a déjà un produit à elle avec cette référence
    produit = {
        "id": new_id(), "catalogue_id": publie["id"], "source": "catalogue", "reference": reference,
        **{k: publie.get(k) for k in CHAMPS_PARTAGES},
        "slug": slugifier(f"{publie['marque']}-{publie['nom']}-{reference}"),
        "categorie_id": cat["id"], "categorie_nom": cat["nom"],
        "image_url": publie.get("photo_url"), "image_source": "catalogue",
        "modeles_compatibles": await _compatibles_lisibles(publie.get("modeles_compatibles") or []),
        "prix_achat": 0, "prix_vente": 0, "stock": 0, "stock_alerte": 2,
        "garantie_mois": 12 if publie["type_produit"] == "TEL" else 0,
        "visible_portail": False, "actif": True, "nouveau": nouveau,
        "documents": [], "conseils_utilisation": "", "created_at": now_iso(),
    }
    await tdb.produits.insert_one(produit)
    return True


async def copier_catalogue_dans_boutique(boutique_id: str) -> int:
    """Première initialisation d'une boutique : TOUT le catalogue publié est copié
    (sans badge « Nouveau » : c'est le catalogue de départ)."""
    n, cache = 0, {}
    async for publie in db.catalogue_publie.find({}, SANS_ID):
        if await ajouter_a_boutique(boutique_id, publie, nouveau=False, cache=cache):
            n += 1
    return n


async def publier(declencheur: str = "planification") -> dict:
    """Publie toutes les fiches prêtes et répercute chez les boutiques."""
    a_publier = await db.catalogue_modeles.find(
        {"statut": "PRET", "supprime": {"$ne": True}, "$or": [{"publie": {"$ne": True}}, {"modifie_apres_publication": True}]},
        SANS_ID).to_list(10000)
    boutiques = [b["id"] async for b in db.boutiques.find({}, {"_id": 0, "id": 1})]
    nouveaux, mises_a_jour = 0, 0
    # Les téléphones d'abord : les pièces y font référence (« compatible avec »)
    a_publier.sort(key=lambda m: 0 if m["type_produit"] == "TEL" else 1)
    for modele in a_publier:
        version = int(modele.get("version_publiee") or 0) + 1
        publie = {**_instantane(modele), "version": version, "date_publication": now_iso()}
        deja = await db.catalogue_publie.find_one({"id": modele["id"]}, {"_id": 0, "id": 1})
        await db.catalogue_publie.update_one({"id": modele["id"]}, {"$set": publie}, upsert=True)
        if deja:
            mises_a_jour += 1
            # Mise à jour des informations partagées chez toutes les boutiques
            maj = {k: publie.get(k) for k in CHAMPS_PARTAGES}
            maj["modeles_compatibles"] = await _compatibles_lisibles(publie.get("modeles_compatibles") or [])
            await db.produits.update_many({"catalogue_id": modele["id"]}, {"$set": maj})
            # La photo n'est remplacée que si la boutique n'a pas mis la sienne
            await db.produits.update_many({"catalogue_id": modele["id"], "image_source": "catalogue"},
                                          {"$set": {"image_url": publie.get("photo_url")}})
        else:
            nouveaux += 1
            for boutique_id in boutiques:
                await ajouter_a_boutique(boutique_id, publie, nouveau=True)
        await db.catalogue_modeles.update_one({"id": modele["id"]}, {"$set": {
            "publie": True, "modifie_apres_publication": False, "version_publiee": version,
            "date_publication": publie["date_publication"]}})
    rapport = {"id": new_id(), "date": now_iso(), "declencheur": declencheur,
               "nouveaux": nouveaux, "mises_a_jour": mises_a_jour, "boutiques": len(boutiques)}
    await db.catalogue_publications.insert_one(rapport.copy())
    return rapport


# ---------------------------------------------------------------------------
# Publication automatique chaque soir
# ---------------------------------------------------------------------------
def prochaine_publication(maintenant: Optional[datetime] = None) -> datetime:
    """Date et heure de la prochaine publication (23h00 heure locale par défaut)."""
    s = get_settings()
    tz = ZoneInfo(s.fuseau_horaire)
    maintenant = maintenant or datetime.now(tz)
    cible = maintenant.replace(hour=s.catalogue_heure_publication, minute=0, second=0, microsecond=0)
    return cible if cible > maintenant else cible + timedelta(days=1)


async def boucle_publication() -> None:
    """Démarrée avec le serveur. Si plusieurs serveurs tournent en même temps,
    un verrou en base (un document par jour) garantit qu'une seule
    publication a lieu par soir."""
    tz = ZoneInfo(get_settings().fuseau_horaire)
    while True:
        cible = prochaine_publication()
        await asyncio.sleep(max((cible - datetime.now(tz)).total_seconds(), 1))
        try:
            await db.verrous.insert_one({"_id": f"publication-catalogue-{cible.date().isoformat()}", "date": now_iso()})
        except DuplicateKeyError:
            continue  # un autre serveur s'en est déjà chargé
        try:
            rapport = await publier("planification")
            logger.info("Catalogue publié : %s", rapport)
        except Exception as exc:  # noqa: BLE001 — la boucle ne doit jamais s'arrêter
            logger.exception("Échec de la publication du catalogue")
            await db.catalogue_echecs.insert_one({"id": new_id(), "date": now_iso(), "erreur": str(exc)[:500]})


# ---------------------------------------------------------------------------
# Assistant de recherche des fiches techniques (API Claude + recherche web)
# ---------------------------------------------------------------------------
SCHEMA_FICHE = {
    "type": "object",
    "properties": {
        "trouve": {"type": "boolean"},
        "marque": {"type": "string"},
        "nom": {"type": "string"},
        "reference_fabricant": {"type": "string"},
        "annee_sortie": {"type": "integer"},
        "description": {"type": "string"},
        "caracteristiques": {"type": "array", "items": {"type": "string"}},
        "photo_url": {"type": "string"},
        "pieces_detachees": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "string"}},
        "remarques": {"type": "string"},
    },
    "required": ["trouve", "marque", "nom", "reference_fabricant", "annee_sortie", "description",
                 "caracteristiques", "photo_url", "pieces_detachees", "sources", "remarques"],
    "additionalProperties": False,
}

CONSIGNES_RECHERCHE = """Tu aides l'administrateur d'une plateforme de boutiques de téléphonie en Afrique de l'Ouest
à remplir le catalogue commun des téléphones. Pour le modèle demandé, cherche sur le web dans cet ordre :
1. les sites officiels des fabricants (apple.com, samsung.com, store.google.com, tecno-mobile.com,
   infinixmobility.com, itel-life.com, nokia.com, xiaomi.com, oppo.com, vivo.com...), qui font foi ;
2. les grandes bases de fiches techniques pour compléter et recouper :
   - gsmarena.com (la plus complète, en anglais ; son « Phone Finder » couvre des milliers de modèles) ;
   - kimovil.com/fr (en français, couvre aussi les marques chinoises peu connues en Europe) ;
   - phonesdata.com/fr (en français, plus de 9 000 téléphones de 230 marques).
Quand deux sources se contredisent, retiens le site du fabricant et signale l'écart dans remarques.
Réponds en français (les pages françaises de Kimovil et PhonesData aident pour les libellés).

- caracteristiques : une ligne par caractéristique, au format « Libellé : valeur », dans cet ordre quand
  c'est connu : Écran, Processeur, Mémoire vive, Stockage, Carte mémoire, Appareil photo arrière, Appareil
  photo avant, Batterie, Charge, Système d'exploitation (version d'origine et dernière mise à jour
  annoncée), Réseaux (2G/3G/4G/5G), Double SIM / eSIM, NFC, Wi-Fi, Bluetooth, Connecteur, Dimensions,
  Poids, Indice d'étanchéité, Couleurs. N'invente rien : omets une ligne que tu n'as pas pu vérifier.
- description : 2 à 3 phrases neutres pour un client (à qui s'adresse ce téléphone).
- photo_url : adresse directe d'une image du produit (fichier .jpg/.png/.webp), de préférence celle du site
  du fabricant (visuel de presse), sinon chaîne vide.
- pieces_detachees : les pièces de rechange courantes pour ce modèle (écran complet, batterie, connecteur
  de charge, vitre arrière, caméra arrière, haut-parleur...), en précisant la référence de pièce si elle
  est connue.
- sources : les adresses des pages utilisées.
- trouve = false si le modèle est introuvable ou ambigu (explique pourquoi dans remarques, et propose les
  modèles possibles).
- remarques : incertitudes, variantes régionales (mémoire, 4G/5G), points à vérifier."""


async def rechercher_fiche(marque: str, modele: str, precisions: str = "") -> dict:
    """Interroge Claude (avec recherche web) et renvoie une PROPOSITION de fiche.
    Rien n'est enregistré : l'administrateur relit et valide."""
    import anthropic

    s = get_settings()
    if not s.anthropic_api_key:
        raise RuntimeError("Assistant de recherche non configuré (clé ANTHROPIC_API_KEY manquante)")
    client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)
    demande = f"Modèle à rechercher : {marque} {modele}".strip()
    if precisions:
        demande += f"\nPrécisions : {precisions}"
    messages: list = [{"role": "user", "content": demande}]
    reponse = None
    # La recherche web tourne côté Anthropic ; si elle est longue, l'API rend la main
    # avec stop_reason = "pause_turn" et on relance pour qu'elle reprenne où elle en était.
    for _ in range(5):
        reponse = await client.beta.messages.create(
            model=s.catalogue_ia_modele,
            max_tokens=16000,
            system=CONSIGNES_RECHERCHE,
            messages=messages,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA_FICHE}},
            # Si le modèle principal refuse, l'API réessaie automatiquement avec un autre
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if reponse.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": reponse.content}]
    if reponse is None or reponse.stop_reason == "refusal":
        raise RuntimeError("La recherche n'a pas abouti pour ce modèle")
    texte = next((b.text for b in reversed(reponse.content) if b.type == "text"), "")
    try:
        return json.loads(texte)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Réponse de l'assistant illisible, réessayez") from exc
