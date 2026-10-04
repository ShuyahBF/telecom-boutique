"""Factures et proformas sur plusieurs lignes de détail.

Cycle de vie :
- PROFORMA : numérotée dès sa création (PRO-2026-00001), sans effet sur le
  stock, modifiable tant qu'elle est en brouillon. « Convertir en facture »
  crée une facture brouillon avec les mêmes lignes (possible pour une proforma
  en cours OU acceptée, une seule fois) ; « Convertir et valider » enchaîne la
  validation de la facture en une seule étape.
- FACTURE : reste en BROUILLON (modifiable, sans numéro) jusqu'à sa
  VALIDATION, qui contrôle le stock, attribue le numéro définitif
  (FAC-2026-00001, sans trou) et déstocke. Une facture validée ne se modifie
  ni ne se supprime : on l'ANNULE (le stock est réintégré).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import Contexte, permission
from journal_paiements import journaliser
from routes.tiers import instantane_client
from services import calculer_lignes, entree_stock, est_stockable, prochain_numero, sorties_groupees, statut_paiement
from utils import montant_en_lettres, new_id, now_iso, today_iso, motif_recherche

router = APIRouter(prefix="/documents", tags=["Factures & proformas"])
# Droits requis (voir la table PERMISSIONS dans auth.py)
facturation = permission("facturation")

MODES_REGLEMENT = {"ESP": "Espèces", "OM": "Orange Money", "MOOV": "Moov Money", "MM": "Mobile Money (PawaPay)",
                   "CB": "Carte bancaire", "VIR": "Virement", "CHQ": "Chèque",
                   # Paiement instantané BCEAO (QR de la banque imprimé sur la facture) : saisi à la
                   # main avec la référence bancaire, voir pispi_connecteur.py
                   "PISPI": "PI-SPI (paiement instantané)"}


class LigneSaisie(BaseModel):
    produit_id: Optional[str] = None
    designation: str = Field("", max_length=255)
    quantite: int = Field(1, gt=0)
    prix_unitaire: Optional[int] = Field(None, ge=0)  # vide = prix catalogue du produit
    remise_pct: float = Field(0, ge=0, le=100)
    taux_tva: Optional[float] = Field(None, ge=0, le=100)  # vide = taux par défaut de la boutique


class DocumentSaisie(BaseModel):
    type_document: Literal["FAC", "PRO"] = "FAC"
    client_id: str
    date: str = Field(default_factory=today_iso, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_echeance: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    objet: str = Field("", max_length=200)
    notes: str = Field("", max_length=2000)
    # Prix unitaires saisis TTC (vide = réglage de la boutique, TTC par défaut)
    prix_ttc: Optional[bool] = None
    lignes: list[LigneSaisie] = Field(default_factory=list, max_length=300)


def enrichir(doc: dict, boutique: dict) -> dict:
    """Ajoute les valeurs calculées à l'affichage (paiement, montant en lettres)."""
    return {**doc, **statut_paiement(doc), "total_en_lettres": montant_en_lettres(doc.get("total_ttc", 0), boutique.get("devise", "FCFA")),
            "modifiable": doc.get("statut") == "BROUILLON"}


async def preparer_lignes(ctx: Contexte, lignes: list[dict], prix_ttc: bool) -> tuple[list[dict], dict]:
    """Complète chaque ligne depuis le produit (désignation, prix, référence)
    puis calcule les montants. Une ligne sans produit est une ligne libre
    (« Frais de livraison », « Main d'œuvre »...)."""
    ids = [l["produit_id"] for l in lignes if l.get("produit_id")]
    produits = {p["id"]: p async for p in ctx.tdb.produits.find({"id": {"$in": ids}})} if ids else {}
    completes = []
    for l in lignes:
        p = produits.get(l.get("produit_id")) if l.get("produit_id") else None
        if l.get("produit_id") and not p:
            raise HTTPException(400, "Un produit de la liste n'existe pas dans votre catalogue")
        if not p and not (l.get("designation") or "").strip():
            raise HTTPException(400, "Chaque ligne doit avoir un produit ou une désignation")
        completes.append({
            "produit_id": p["id"] if p else None,
            "reference": p["reference"] if p else "",
            "stockable": bool(p and est_stockable(p)),
            "designation": (l.get("designation") or "").strip() or (p["nom"] if p else ""),
            "quantite": l["quantite"],
            "prix_unitaire": l["prix_unitaire"] if l.get("prix_unitaire") is not None else (p["prix_vente"] if p else 0),
            "remise_pct": l.get("remise_pct") or 0,
            "taux_tva": l.get("taux_tva"),
        })
    return calculer_lignes(completes, ctx.boutique.get("taux_tva_defaut", 18), prix_ttc)


async def _client(ctx: Contexte, client_id: str) -> dict:
    client = await ctx.tdb.clients.find_one({"id": client_id})
    if not client:
        raise HTTPException(400, "Client inconnu")
    return client


async def _lire(ctx: Contexte, document_id: str) -> dict:
    doc = await ctx.tdb.documents.find_one({"id": document_id})
    if not doc:
        raise HTTPException(404, "Document introuvable")
    return doc


async def creer_document(ctx: Contexte, type_document: str, client: dict, lignes_saisies: list[dict],
                         objet: str = "", notes: str = "", date_doc: Optional[str] = None,
                         date_echeance: Optional[str] = None, origine: Optional[dict] = None,
                         prix_ttc: Optional[bool] = None) -> dict:
    """Création commune (écran de saisie, conversion de proforma, commande, SAV)."""
    if prix_ttc is None:
        prix_ttc = bool(ctx.boutique.get("prix_ttc", True))
    lignes, totaux = await preparer_lignes(ctx, lignes_saisies, prix_ttc)
    date_doc = date_doc or today_iso()
    if type_document == "PRO" and not date_echeance:
        jours = int(ctx.boutique.get("validite_proforma_jours", 15))
        date_echeance = (date.fromisoformat(date_doc) + timedelta(days=jours)).isoformat()
    doc = {
        "id": new_id(), "type_document": type_document,
        # Proforma : numéro tout de suite ; facture : à la validation
        "numero": await prochain_numero(ctx.boutique["id"], "PRO") if type_document == "PRO" else None,
        "client_id": client["id"], "client": instantane_client(client), "date": date_doc,
        "date_echeance": date_echeance, "objet": objet, "notes": notes, "statut": "BROUILLON", "prix_ttc": prix_ttc,
        "lignes": lignes, **totaux, "reglements": [], "created_at": now_iso(),
        "date_validation": None, **(origine or {}), "cree_par": ctx.user.get("nom", ""),
    }
    await ctx.tdb.documents.insert_one(doc)
    return doc


@router.get("/modes-reglement")
async def modes_reglement(_: Contexte = Depends(facturation)):
    return MODES_REGLEMENT


@router.get("")
async def lister(type_document: str = "", statut: str = "", q: str = "", ctx: Contexte = Depends(facturation)):
    filtre: dict = {}
    if type_document:
        filtre["type_document"] = type_document
    if statut:
        filtre["statut"] = statut
    if q.strip():
        import re
        motif = motif_recherche(q)
        filtre["$or"] = [{"numero": {"$regex": motif, "$options": "i"}},
                         {"client.nom": {"$regex": motif, "$options": "i"}},
                         {"client.telephone": {"$regex": motif, "$options": "i"}},
                         {"objet": {"$regex": motif, "$options": "i"}}]
    docs = await ctx.tdb.documents.find(filtre, {"_id": 0, "lignes": 0}).sort([("date", -1), ("created_at", -1)]).to_list(500)
    # « convertie » : proforma qui a déjà donné une facture (badge « Convertie » dans la liste)
    # « convertible » : proforma en cours ou acceptée, sans facture (bouton « Convertir en facture »)
    return [{**d, **statut_paiement(d), "convertie": bool(d.get("facture_generee_id")),
             "convertible": proforma_convertible(d)} for d in docs]


@router.get("/{document_id}")
async def lire(document_id: str, ctx: Contexte = Depends(facturation)):
    doc = await _lire(ctx, document_id)
    resultat = enrichir(doc, ctx.boutique)
    resultat["convertible"] = proforma_convertible(doc)
    # Proforma convertie : numéro et statut de la facture générée (lien affiché sur la proforma)
    if doc.get("facture_generee_id"):
        fac = await ctx.tdb.documents.find_one({"id": doc["facture_generee_id"]},
                                               {"_id": 0, "id": 1, "numero": 1, "statut": 1})
        resultat["facture_generee"] = fac
    return resultat


@router.get("/{document_id}/qr")
async def qr_document(document_id: str, ctx: Contexte = Depends(facturation)):
    """Adresse du QR code imprimé sur la facture / proforma : page publique de la
    boutique + jeton CHIFFRÉ et signé (boutique, client, empreinte du téléphone,
    n° et date du document). Le numéro de téléphone n'y figure jamais en clair."""
    import jetons_qr

    doc = await _lire(ctx, document_id)
    jeton = jetons_qr.creer_jeton_document(ctx.boutique, doc)
    # Bloc « Payer par PI-SPI » (QR fourni par la banque de la boutique), s'il est actif
    import pispi_connecteur
    return {"url": jetons_qr.url_qr(jeton), "pispi": pispi_connecteur.bloc_impression(ctx.boutique)}


@router.post("", status_code=201)
async def creer(payload: DocumentSaisie, ctx: Contexte = Depends(facturation)):
    client = await _client(ctx, payload.client_id)
    doc = await creer_document(ctx, payload.type_document, client, [l.model_dump() for l in payload.lignes],
                               payload.objet, payload.notes, payload.date, payload.date_echeance,
                               prix_ttc=payload.prix_ttc)
    return enrichir(doc, ctx.boutique)


@router.put("/{document_id}")
async def modifier(document_id: str, payload: DocumentSaisie, ctx: Contexte = Depends(facturation)):
    actuel = await _lire(ctx, document_id)
    if actuel["type_document"] != payload.type_document:
        raise HTTPException(400, "Le type d'un document ne peut pas être changé")
    client = await _client(ctx, payload.client_id)
    prix_ttc = actuel.get("prix_ttc", True) if payload.prix_ttc is None else payload.prix_ttc
    lignes, totaux = await preparer_lignes(ctx, [l.model_dump() for l in payload.lignes], prix_ttc)
    maj = {"prix_ttc": prix_ttc, "client_id": client["id"], "client": instantane_client(client), "date": payload.date,
           "date_echeance": payload.date_echeance, "objet": payload.objet, "notes": payload.notes,
           "lignes": lignes, **totaux}
    # Condition statut=BROUILLON dans le filtre : impossible de modifier un document validé
    doc = await ctx.tdb.documents.find_one_and_update({"id": document_id, "statut": "BROUILLON"}, {"$set": maj})
    if not doc:
        raise HTTPException(409, "Ce document n'est plus modifiable")
    return enrichir(doc, ctx.boutique)


@router.delete("/{document_id}")
async def supprimer(document_id: str, ctx: Contexte = Depends(facturation)):
    """Seul un BROUILLON de facture (sans numéro) peut être supprimé."""
    res = await ctx.tdb.documents.delete_one({"id": document_id, "type_document": "FAC", "statut": "BROUILLON"})
    if not res.deleted_count:
        raise HTTPException(409, "Seul un brouillon de facture peut être supprimé (sinon : annuler)")
    return {"ok": True}


@router.post("/{document_id}/valider")
async def valider(document_id: str, ctx: Contexte = Depends(facturation)):
    # 1) Verrou : BROUILLON -> EN_VALIDATION (atomique : un double-clic ne valide pas deux fois)
    doc = await ctx.tdb.documents.find_one_and_update(
        {"id": document_id, "type_document": "FAC", "statut": "BROUILLON"}, {"$set": {"statut": "EN_VALIDATION"}})
    if not doc:
        raise HTTPException(409, "Seule une facture en brouillon peut être validée")
    reference_temp = f"EN-COURS-{document_id}"  # remplacée par le numéro définitif
    destocke = False
    try:
        if not doc["lignes"]:
            raise HTTPException(400, "Impossible de valider une facture sans ligne")
        # 2) Sorties de stock « tout ou rien » (refus si un article manque)
        besoins: dict[str, int] = {}
        for l in doc["lignes"]:
            if l.get("produit_id") and l.get("stockable"):
                besoins[l["produit_id"]] = besoins.get(l["produit_id"], 0) + l["quantite"]
        if besoins:
            await sorties_groupees(ctx.tdb, besoins, "VENTE", reference_temp, f"Client : {doc['client']['nom']}", ctx.auteur)
            destocke = True
        # Numéro réservé APRÈS le contrôle du stock : un refus ne consomme aucun numéro
        numero = await prochain_numero(ctx.boutique["id"], "FAC")
        await ctx.tdb.mouvements.update_many({"reference": reference_temp}, {"$set": {"reference": numero}})
    except Exception:
        if destocke:  # erreur après la sortie de stock : on remet les articles
            for produit_id, quantite in besoins.items():
                produit = await ctx.tdb.produits.find_one({"id": produit_id})
                await entree_stock(ctx.tdb, produit, quantite, "RETOUR", reference_temp, "Validation interrompue", ctx.auteur)
        await ctx.tdb.documents.update_one({"id": document_id}, {"$set": {"statut": "BROUILLON"}})
        raise
    # 3) Statut définitif
    doc = await ctx.tdb.documents.find_one_and_update(
        {"id": document_id}, {"$set": {"statut": "VALIDE", "numero": numero, "date_validation": now_iso()}})
    return enrichir(doc, ctx.boutique)


@router.post("/{document_id}/annuler")
async def annuler(document_id: str, ctx: Contexte = Depends(facturation)):
    avant = await ctx.tdb.documents.find_one_and_update(
        {"id": document_id, "statut": {"$in": ["BROUILLON", "VALIDE"]}}, {"$set": {"statut": "ANNULE"}}, apres=False)
    if not avant:
        raise HTTPException(409, "Document introuvable ou déjà annulé")
    if avant["type_document"] == "FAC" and avant["statut"] == "VALIDE":
        # Réintégration du stock vendu
        for l in avant["lignes"]:
            if l.get("produit_id") and l.get("stockable"):
                produit = await ctx.tdb.produits.find_one({"id": l["produit_id"]})
                if produit:
                    await entree_stock(ctx.tdb, produit, l["quantite"], "RETOUR", avant["numero"],
                                       "Annulation de facture", ctx.auteur)
    return enrichir(await _lire(ctx, document_id), ctx.boutique)


def proforma_convertible(doc: dict) -> bool:
    """Vrai pour une proforma en cours (BROUILLON) ou acceptée (VALIDE) qui n'a pas
    encore donné de facture."""
    return (doc.get("type_document") == "PRO" and doc.get("statut") in ("BROUILLON", "VALIDE")
            and not doc.get("facture_generee_id"))


# Marqueur posé pendant la création de la facture : il « réserve » la proforma, pour
# qu'un double-clic (ou deux postes en même temps) ne crée jamais deux factures
CONVERSION_EN_COURS = "EN_COURS"


@router.post("/{document_id}/convertir")
async def convertir(document_id: str, valider_facture: bool = False, ctx: Contexte = Depends(facturation)):
    """Proforma (en cours ou acceptée) -> facture brouillon reprenant toutes ses lignes.
    Une proforma ne se convertit qu'UNE fois (sinon 409). Avec ?valider_facture=true
    (« Convertir et valider »), la facture est aussitôt validée (numéro définitif,
    sortie de stock) ; si la validation est refusée (stock insuffisant...), la facture
    reste en brouillon et le motif est renvoyé dans « validation_erreur »."""
    # 1) Réservation atomique : proforma convertible -> statut VALIDE (acceptée) + marqueur
    filtre = {"id": document_id, "type_document": "PRO", "statut": {"$in": ["BROUILLON", "VALIDE"]},
              "facture_generee_id": None}  # None = champ absent ou vide
    pro = await ctx.tdb.documents.find_one_and_update(
        filtre, {"$set": {"statut": "VALIDE", "facture_generee_id": CONVERSION_EN_COURS}}, apres=False)
    if not pro:
        existant = await ctx.tdb.documents.find_one({"id": document_id})
        if not existant:
            raise HTTPException(404, "Document introuvable")
        if existant.get("type_document") != "PRO":
            raise HTTPException(409, "Seule une proforma peut être convertie en facture")
        if existant.get("facture_generee_id"):
            raise HTTPException(409, "Cette proforma a déjà été convertie en facture")
        raise HTTPException(409, "Seule une proforma en cours ou acceptée peut être convertie")
    # 2) Création de la facture brouillon (en cas d'erreur, la proforma est remise comme avant)
    try:
        client = await ctx.tdb.clients.find_one({"id": pro["client_id"]}) or {"id": pro["client_id"], **pro["client"]}
        lignes = [{k: l.get(k) for k in ("produit_id", "designation", "quantite", "prix_unitaire", "remise_pct", "taux_tva")}
                  for l in pro["lignes"]]
        facture = await creer_document(ctx, "FAC", client, lignes, pro.get("objet", ""), pro.get("notes", ""),
                                       origine={"proforma_origine": {"id": pro["id"], "numero": pro["numero"]}},
                                       prix_ttc=pro.get("prix_ttc", True))
    except Exception:
        await ctx.tdb.documents.update_one({"id": pro["id"]}, {"$set": {"statut": pro["statut"]},
                                                               "$unset": {"facture_generee_id": ""}})
        raise
    await ctx.tdb.documents.update_one({"id": pro["id"]}, {"$set": {"facture_generee_id": facture["id"],
                                                                    "date_conversion": now_iso()}})
    # 3) « Convertir et valider » : validation immédiate de la facture créée
    if valider_facture:
        try:
            return await valider(facture["id"], ctx)
        except HTTPException as exc:
            # La facture existe (brouillon) : on la renvoie avec le motif du refus
            return {**enrichir(await _lire(ctx, facture["id"]), ctx.boutique), "validation_erreur": str(exc.detail)}
    return enrichir(facture, ctx.boutique)


class ReglementSaisie(BaseModel):
    montant: int = Field(..., gt=0)
    mode: Literal["ESP", "OM", "MOOV", "MM", "CB", "VIR", "CHQ", "PISPI"] = "ESP"
    date: str = Field(default_factory=today_iso, pattern=r"^\d{4}-\d{2}-\d{2}$")
    reference: str = Field("", max_length=60)


@router.post("/{document_id}/reglements")
async def ajouter_reglement(document_id: str, payload: ReglementSaisie, ctx: Contexte = Depends(facturation)):
    # PI-SPI : la référence bancaire du virement est obligatoire (rapprochement avec le relevé)
    if payload.mode == "PISPI" and not payload.reference.strip():
        raise HTTPException(400, "Indiquez la référence bancaire du paiement PI-SPI")
    reglement = {"id": new_id(), **payload.model_dump(), "saisi_par": ctx.user.get("nom", ""), "created_at": now_iso()}
    doc = await ctx.tdb.documents.find_one_and_update(
        {"id": document_id, "type_document": "FAC", "statut": {"$ne": "ANNULE"}}, {"$push": {"reglements": reglement}})
    if not doc:
        raise HTTPException(409, "Règlement impossible sur ce document")
    await journaliser(ctx.boutique["id"], f"reglement-{reglement['id']}", canal="CAISSE", mode=payload.mode,
                      montant=payload.montant, statut="SUCCES", objet=f"Facture {doc.get('numero') or '(brouillon)'}",
                      reference=payload.reference, client_nom=doc["client"]["nom"], saisi_par=ctx.user.get("nom", ""),
                      devise=ctx.boutique.get("devise", "FCFA"), liens={"document_id": doc["id"]})
    if payload.mode == "PISPI":
        # Trace de l'encaissement PI-SPI (collection pispi_transactions, statut « rapproche »)
        from routes.pispi import enregistrer_transaction
        await enregistrer_transaction(ctx, doc, reglement)
    return enrichir(doc, ctx.boutique)


@router.delete("/{document_id}/reglements/{reglement_id}")
async def supprimer_reglement(document_id: str, reglement_id: str, ctx: Contexte = Depends(facturation)):
    avant = await ctx.tdb.documents.find_one_and_update(
        {"id": document_id}, {"$pull": {"reglements": {"id": reglement_id, "mode": {"$ne": "MM"}}}}, apres=False)
    if not avant:
        raise HTTPException(404, "Document introuvable")
    retire = next((r for r in avant.get("reglements", []) if r["id"] == reglement_id and r.get("mode") != "MM"), None)
    if retire:
        # L'historique garde la trace du règlement, marqué « Annulé »
        await journaliser(ctx.boutique["id"], f"reglement-{reglement_id}", canal="CAISSE", mode=retire["mode"],
                          montant=retire["montant"], statut="ANNULE", motif=f"Supprimé par {ctx.user.get('nom', '')}",
                          objet=f"Facture {avant.get('numero') or '(brouillon)'}", client_nom=avant["client"]["nom"])
        if retire["mode"] == "PISPI":
            from routes.pispi import rejeter_transaction
            await rejeter_transaction(ctx, reglement_id, ctx.user.get("nom", ""))
    return enrichir(await _lire(ctx, document_id), ctx.boutique)
