"""Règles métier partagées : numérotation automatique, stock, calcul des
lignes de facture. Écrites pour rester justes même si deux vendeurs
travaillent au même instant (opérations atomiques MongoDB)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable, Optional

from fastapi import HTTPException
from pymongo import ReturnDocument

from db import TenantDB, db
from utils import arrondi, new_id, now_iso


# ---------------------------------------------------------------------------
# Numérotation : FAC-2026-00001, PRO-..., CMD-..., MNT-..., BE-...
# ---------------------------------------------------------------------------
async def prochain_numero(boutique_id: str, prefixe: str) -> str:
    """Réserve le prochain numéro de CETTE boutique pour ce préfixe et cette
    année. $inc est atomique côté MongoDB : deux ventes simultanées
    n'obtiennent jamais le même numéro. La série repart à 1 chaque année."""
    annee = date.today().year
    compteur = await db.compteurs.find_one_and_update(
        {"boutique_id": boutique_id, "prefixe": prefixe, "annee": annee},
        {"$inc": {"dernier": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return f"{prefixe}-{annee}-{compteur['dernier']:05d}"


# ---------------------------------------------------------------------------
# Stock : on n'écrit JAMAIS le stock directement, chaque variation est un
# mouvement (journal), et la mise à jour du produit est atomique.
# ---------------------------------------------------------------------------
MOTIFS = {
    "ACHAT": "Réception fournisseur",
    "VENTE": "Vente / facture",
    "MAINT": "Pièce utilisée en maintenance",
    "RETOUR": "Retour / annulation",
    "CASSE": "Casse / perte",
    "INVENT": "Ajustement d'inventaire",
    "AUTRE": "Autre",
}


def est_stockable(produit: dict) -> bool:
    """Les services (main d'œuvre...) ne se stockent pas."""
    return produit.get("type_produit") != "SER"


async def _journaliser(tdb: TenantDB, produit: dict, sens: str, quantite: int, motif: str,
                       reference: str, commentaire: str, auteur: Optional[dict]) -> dict:
    mouvement = {
        "id": new_id(), "produit_id": produit["id"], "produit_nom": produit["nom"],
        "produit_reference": produit.get("reference", ""), "sens": sens, "quantite": quantite,
        "motif": motif, "reference": reference, "commentaire": commentaire,
        "date": now_iso(), **(auteur or {"user_id": None, "user_nom": "Système"}),
    }
    await tdb.mouvements.insert_one(mouvement)
    return mouvement


async def entree_stock(tdb: TenantDB, produit: dict, quantite: int, motif: str,
                       reference: str = "", commentaire: str = "", auteur: Optional[dict] = None) -> dict:
    await tdb.produits.update_one({"id": produit["id"]}, {"$inc": {"stock": quantite}})
    return await _journaliser(tdb, produit, "E", quantite, motif, reference, commentaire, auteur)


async def sortie_stock(tdb: TenantDB, produit: dict, quantite: int, motif: str,
                       reference: str = "", commentaire: str = "", auteur: Optional[dict] = None) -> dict:
    """Sortie de stock REFUSÉE si le stock est insuffisant. La condition
    « stock >= quantité » est vérifiée PAR MongoDB au moment de la mise à
    jour : impossible de vendre deux fois le dernier téléphone."""
    res = await tdb.produits.update_one(
        {"id": produit["id"], "stock": {"$gte": quantite}}, {"$inc": {"stock": -quantite}}
    )
    if not res.modified_count:
        actuel = await tdb.produits.find_one({"id": produit["id"]}, {"_id": 0, "stock": 1})
        raise HTTPException(409, f"Stock insuffisant pour « {produit['nom']} » : "
                                 f"{(actuel or {}).get('stock', 0)} disponible(s), {quantite} demandé(s).")
    return await _journaliser(tdb, produit, "S", quantite, motif, reference, commentaire, auteur)


async def sorties_groupees(tdb: TenantDB, besoins: dict[str, int], motif: str, reference: str,
                           commentaire: str, auteur: Optional[dict]) -> None:
    """Plusieurs sorties « tout ou rien » (validation d'une facture) : si un
    seul article manque, les sorties déjà faites sont annulées et RIEN n'est
    déstocké. Fonctionne sans transaction (donc aussi sur la base de test)."""
    produits = {p["id"]: p async for p in tdb.produits.find({"id": {"$in": list(besoins)}})}
    faits: list[tuple[dict, int]] = []
    try:
        for produit_id, quantite in besoins.items():
            produit = produits.get(produit_id)
            if not produit:
                raise HTTPException(404, "Un produit de la facture n'existe plus")
            res = await tdb.produits.update_one(
                {"id": produit_id, "stock": {"$gte": quantite}}, {"$inc": {"stock": -quantite}}
            )
            if not res.modified_count:
                raise HTTPException(409, f"Stock insuffisant pour « {produit['nom']} » "
                                         f"({produit.get('stock', 0)} disponible(s), {quantite} demandé(s)).")
            faits.append((produit, quantite))
    except HTTPException:
        # Annulation des sorties déjà appliquées (compensation)
        for produit, quantite in faits:
            await tdb.produits.update_one({"id": produit["id"]}, {"$inc": {"stock": quantite}})
        raise
    for produit, quantite in faits:
        await _journaliser(tdb, produit, "S", quantite, motif, reference, commentaire, auteur)


# ---------------------------------------------------------------------------
# Lignes de facture / proforma
# ---------------------------------------------------------------------------
def calculer_lignes(lignes: Iterable[dict], taux_tva_defaut: float, prix_ttc: bool = False) -> tuple[list[dict], dict]:
    """Calcule chaque ligne (HT après remise, TVA, TTC) et les totaux.

    prix_ttc=True : les prix unitaires saisis sont des prix TTC (prix
    affichés en boutique et sur le portail) ; la TVA en est extraite.
    prix_ttc=False : prix HT, la TVA s'ajoute. Les montants sont TOUJOURS
    recalculés par le serveur, jamais repris tels quels du navigateur."""
    resultat, total_ht, total_tva = [], 0, 0
    for l in lignes:
        quantite = int(l.get("quantite") or 0)
        pu = arrondi(l.get("prix_unitaire") or 0)
        remise = Decimal(str(l.get("remise_pct") or 0))
        tva = Decimal(str(l.get("taux_tva") if l.get("taux_tva") is not None else taux_tva_defaut))
        brut = Decimal(pu * quantite) * (1 - remise / 100)
        if prix_ttc:
            ttc = arrondi(brut)
            ht = arrondi(Decimal(ttc) * 100 / (100 + tva))
            montant_tva = ttc - ht
            pu_ht = arrondi(Decimal(pu) * 100 / (100 + tva))
        else:
            ht = arrondi(brut)
            montant_tva = arrondi(Decimal(ht) * tva / 100)
            pu_ht = pu
        resultat.append({
            **l, "quantite": quantite, "prix_unitaire": pu, "prix_unitaire_ht": pu_ht, "remise_pct": float(remise),
            "taux_tva": float(tva), "montant_ht": ht, "montant_tva": montant_tva, "montant_ttc": ht + montant_tva,
        })
        total_ht += ht
        total_tva += montant_tva
    return resultat, {"total_ht": total_ht, "total_tva": total_tva, "total_ttc": total_ht + total_tva}


def statut_paiement(doc: dict) -> dict:
    """Réglé / reste à payer / libellé, à partir des règlements enregistrés."""
    regle = sum(int(r.get("montant", 0)) for r in doc.get("reglements", []))
    reste = max(int(doc.get("total_ttc", 0)) - regle, 0)
    if doc.get("type_document") != "FAC":
        libelle = "—"
    elif regle <= 0:
        libelle = "Non payée"
    elif reste > 0:
        libelle = "Partiellement payée"
    else:
        libelle = "Payée"
    return {"total_regle": regle, "reste_a_payer": reste, "statut_paiement": libelle}
