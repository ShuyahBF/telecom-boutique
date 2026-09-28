"""Catalogue de la boutique : catégories et produits (téléphones,
accessoires, pièces détachées, services)."""
from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from auth import Contexte, tout_le_personnel, ventes
from services import entree_stock, est_stockable
from catalogue_public import CHAMPS_PARTAGES
from storage import enregistrer_image, lire_document, lire_image, supprimer_image
from utils import new_id, now_iso, slugifier

router = APIRouter(tags=["Catalogue"])


# ---------------------------------------------------------------------------
# Catégories
# ---------------------------------------------------------------------------
class Categorie(BaseModel):
    nom: str = Field(..., min_length=1, max_length=100)
    ordre: int = 0


@router.get("/categories")
async def lister_categories(ctx: Contexte = Depends(tout_le_personnel)):
    return await ctx.tdb.categories.find({}).sort([("ordre", 1), ("nom", 1)]).to_list(500)


@router.post("/categories", status_code=201)
async def creer_categorie(payload: Categorie, ctx: Contexte = Depends(ventes)):
    doc = {"id": new_id(), "nom": payload.nom.strip(), "slug": slugifier(payload.nom), "ordre": payload.ordre}
    await ctx.tdb.categories.insert_one(doc)
    return doc


@router.put("/categories/{categorie_id}")
async def modifier_categorie(categorie_id: str, payload: Categorie, ctx: Contexte = Depends(ventes)):
    doc = await ctx.tdb.categories.find_one_and_update(
        {"id": categorie_id},
        {"$set": {"nom": payload.nom.strip(), "slug": slugifier(payload.nom), "ordre": payload.ordre}})
    if not doc:
        raise HTTPException(404, "Catégorie introuvable")
    await ctx.tdb.produits.update_many({"categorie_id": categorie_id}, {"$set": {"categorie_nom": doc["nom"]}})
    return doc


@router.delete("/categories/{categorie_id}")
async def supprimer_categorie(categorie_id: str, ctx: Contexte = Depends(ventes)):
    if await ctx.tdb.produits.count_documents({"categorie_id": categorie_id}):
        raise HTTPException(409, "Des produits utilisent encore cette catégorie")
    await ctx.tdb.categories.delete_one({"id": categorie_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Produits
# ---------------------------------------------------------------------------
TypeProduit = Literal["TEL", "ACC", "PIE", "SER"]


class ProduitSaisie(BaseModel):
    reference: str = Field(..., min_length=1, max_length=50)
    nom: str = Field(..., min_length=1, max_length=200)
    type_produit: TypeProduit = "TEL"
    categorie_id: str
    marque: str = Field("", max_length=80)
    description: str = Field("", max_length=5000)
    # Une caractéristique par élément : « Écran : 6,5 pouces »
    caracteristiques: list[str] = Field(default_factory=list, max_length=50)
    prix_achat: int = Field(0, ge=0)
    prix_vente: int = Field(..., ge=0)
    stock_alerte: int = Field(2, ge=0)
    garantie_mois: int = Field(0, ge=0, le=120)
    visible_portail: bool = True
    actif: bool = True
    # Conseils d'utilisation propres à la boutique (affichés sur sa vitrine)
    conseils_utilisation: str = Field("", max_length=5000)


def _controler_mise_en_vente(payload: "ProduitSaisie") -> None:
    """Un produit sans prix ne peut pas être proposé aux clients du portail."""
    if payload.visible_portail and payload.prix_vente <= 0 and payload.type_produit != "SER":
        raise HTTPException(400, "Fixez un prix de vente avant de rendre ce produit visible sur le portail")


class ProduitCreation(ProduitSaisie):
    # Stock de départ (enregistré comme un mouvement d'inventaire)
    stock_initial: int = Field(0, ge=0)


async def _categorie(ctx: Contexte, categorie_id: str) -> dict:
    cat = await ctx.tdb.categories.find_one({"id": categorie_id})
    if not cat:
        raise HTTPException(400, "Catégorie inconnue")
    return cat


@router.get("/produits")
async def lister_produits(q: str = "", categorie_id: str = "", type_produit: str = "", alerte: bool = False,
                          nouveau: bool = False, source: str = "", sans_prix: bool = False,
                          ctx: Contexte = Depends(tout_le_personnel)):
    filtre: dict = {}
    if nouveau:  # ajouts récents du catalogue public, pas encore consultés
        filtre["nouveau"] = True
    if source == "catalogue":
        filtre["catalogue_id"] = {"$ne": None}
    elif source == "boutique":  # téléphones créés par la boutique (informations privées)
        filtre["catalogue_id"] = None
    if sans_prix:
        filtre["prix_vente"] = {"$lte": 0}
    if q:
        motif = re.escape(q.strip())
        filtre["$or"] = [{"nom": {"$regex": motif, "$options": "i"}},
                         {"reference": {"$regex": motif, "$options": "i"}},
                         {"marque": {"$regex": motif, "$options": "i"}}]
    if categorie_id:
        filtre["categorie_id"] = categorie_id
    if type_produit:
        filtre["type_produit"] = type_produit
    produits = await ctx.tdb.produits.find(filtre).sort("nom", 1).to_list(2000)
    if alerte:
        produits = [p for p in produits if est_stockable(p) and p.get("actif", True)
                    and p.get("stock", 0) <= p.get("stock_alerte", 0)]
    return produits


@router.get("/produits/{produit_id}")
async def lire_produit(produit_id: str, ctx: Contexte = Depends(tout_le_personnel)):
    produit = await ctx.tdb.produits.find_one({"id": produit_id})
    if not produit:
        raise HTTPException(404, "Produit introuvable")
    return produit


@router.post("/produits", status_code=201)
async def creer_produit(payload: ProduitCreation, ctx: Contexte = Depends(ventes)):
    if await ctx.tdb.produits.find_one({"reference": payload.reference.strip()}):
        raise HTTPException(409, "Cette référence existe déjà dans votre catalogue")
    _controler_mise_en_vente(payload)
    cat = await _categorie(ctx, payload.categorie_id)
    donnees = payload.model_dump(exclude={"stock_initial"})
    produit = {
        **donnees, "id": new_id(), "reference": payload.reference.strip(), "nom": payload.nom.strip(),
        "slug": slugifier(f"{payload.nom}-{payload.reference}"), "categorie_nom": cat["nom"],
        "caracteristiques": [c.strip() for c in payload.caracteristiques if c.strip()],
        "image_url": None, "image_source": "boutique", "stock": 0, "created_at": now_iso(),
        # Produit créé par la boutique : ses informations ne sont PAS partagées
        "catalogue_id": None, "source": "boutique", "nouveau": False, "documents": [], "modeles_compatibles": [],
    }
    await ctx.tdb.produits.insert_one(produit)
    if payload.stock_initial and est_stockable(produit):
        await entree_stock(ctx.tdb, produit, payload.stock_initial, "INVENT", "", "Stock initial", ctx.auteur)
    return await ctx.tdb.produits.find_one({"id": produit["id"]})


@router.put("/produits/{produit_id}")
async def modifier_produit(produit_id: str, payload: ProduitSaisie, ctx: Contexte = Depends(ventes)):
    actuel = await ctx.tdb.produits.find_one({"id": produit_id})
    if not actuel:
        raise HTTPException(404, "Produit introuvable")
    existant = await ctx.tdb.produits.find_one({"reference": payload.reference.strip()})
    if existant and existant["id"] != produit_id:
        raise HTTPException(409, "Cette référence existe déjà dans votre catalogue")
    _controler_mise_en_vente(payload)
    cat = await _categorie(ctx, payload.categorie_id)
    # Le stock n'est PAS modifiable ici : il ne bouge que par des mouvements
    maj = {**payload.model_dump(), "reference": payload.reference.strip(), "nom": payload.nom.strip(),
           "categorie_nom": cat["nom"], "caracteristiques": [c.strip() for c in payload.caracteristiques if c.strip()]}
    if actuel.get("catalogue_id"):
        # Modèle issu du catalogue public : les informations partagées (nom,
        # caractéristiques...) sont tenues à jour par la plateforme ; la boutique
        # règle seulement ses prix, sa visibilité, son rayon, sa garantie...
        for champ in (*CHAMPS_PARTAGES, "reference"):
            maj[champ] = actuel.get(champ)
    maj["slug"] = actuel.get("slug") if actuel.get("catalogue_id") else slugifier(f"{maj['nom']}-{maj['reference']}")
    maj["nouveau"] = False  # modifié = consulté
    return await ctx.tdb.produits.find_one_and_update({"id": produit_id}, {"$set": maj})


@router.post("/produits/nouveautes/vues")
async def marquer_nouveautes_vues(ctx: Contexte = Depends(tout_le_personnel)):
    """Retire le badge « Nouveau » de tous les produits reçus du catalogue public."""
    res = await ctx.tdb.produits.update_many({"nouveau": True}, {"$set": {"nouveau": False}})
    return {"modifies": res.modified_count}


@router.post("/produits/{produit_id}/vu")
async def marquer_vu(produit_id: str, ctx: Contexte = Depends(tout_le_personnel)):
    produit = await ctx.tdb.produits.find_one_and_update({"id": produit_id}, {"$set": {"nouveau": False}})
    if not produit:
        raise HTTPException(404, "Produit introuvable")
    return produit


@router.post("/produits/{produit_id}/image")
async def envoyer_image_produit(produit_id: str, fichier: UploadFile = File(...), ctx: Contexte = Depends(ventes)):
    produit = await ctx.tdb.produits.find_one({"id": produit_id})
    if not produit:
        raise HTTPException(404, "Produit introuvable")
    contenu, type_mime = await lire_image(fichier)
    url = await enregistrer_image(ctx.boutique["id"], "produits", contenu, type_mime)
    await supprimer_image(ctx.boutique["id"], produit.get("image_url"))
    return await ctx.tdb.produits.find_one_and_update(
        {"id": produit_id}, {"$set": {"image_url": url, "image_source": "boutique"}})


# ---------------------------------------------------------------------------
# Documents privés d'un produit (brochure, fiche technique, manuel, conseils...)
# Ils appartiennent à la boutique et ne sont jamais partagés avec les autres.
# ---------------------------------------------------------------------------
TYPES_DOCUMENT = {"BROCHURE": "Brochure", "FICHE_TECHNIQUE": "Fiche technique", "MANUEL": "Manuel d'utilisation",
                  "CONSEILS": "Conseils d'utilisation", "PHOTO": "Photo", "AUTRE": "Autre"}


@router.get("/produits-types-documents")
async def types_documents(_: Contexte = Depends(tout_le_personnel)):
    return TYPES_DOCUMENT


@router.post("/produits/{produit_id}/documents")
async def ajouter_document(produit_id: str, fichier: UploadFile = File(...), titre: str = Form(..., max_length=150),
                           type_document: str = Form("AUTRE"), visible_clients: bool = Form(False),
                           ctx: Contexte = Depends(ventes)):
    if type_document not in TYPES_DOCUMENT:
        raise HTTPException(400, "Type de document inconnu")
    if not await ctx.tdb.produits.find_one({"id": produit_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Produit introuvable")
    contenu, type_mime = await lire_document(fichier)
    url = await enregistrer_image(ctx.boutique["id"], "documents", contenu, type_mime)
    document = {"id": new_id(), "titre": titre.strip() or fichier.filename, "type": type_document, "url": url,
                "format": type_mime, "visible_clients": visible_clients, "created_at": now_iso()}
    return await ctx.tdb.produits.find_one_and_update({"id": produit_id}, {"$push": {"documents": document}})


class VisibiliteDocument(BaseModel):
    visible_clients: bool


@router.patch("/produits/{produit_id}/documents/{document_id}")
async def visibilite_document(produit_id: str, document_id: str, payload: VisibiliteDocument,
                              ctx: Contexte = Depends(ventes)):
    produit = await ctx.tdb.produits.find_one_and_update(
        {"id": produit_id, "documents.id": document_id},
        {"$set": {"documents.$.visible_clients": payload.visible_clients}})
    if not produit:
        raise HTTPException(404, "Document introuvable")
    return produit


@router.delete("/produits/{produit_id}/documents/{document_id}")
async def supprimer_document(produit_id: str, document_id: str, ctx: Contexte = Depends(ventes)):
    produit = await ctx.tdb.produits.find_one({"id": produit_id})
    doc = next((d for d in (produit or {}).get("documents", []) if d["id"] == document_id), None)
    if not doc:
        raise HTTPException(404, "Document introuvable")
    await ctx.tdb.produits.update_one({"id": produit_id}, {"$pull": {"documents": {"id": document_id}}})
    await supprimer_image(ctx.boutique["id"], doc["url"])
    return await ctx.tdb.produits.find_one({"id": produit_id})
