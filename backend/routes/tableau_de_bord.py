"""Indicateurs clés de la boutique, en une requête pour la page d'accueil du back-office."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends

from auth import Contexte, tout_le_personnel
from routes.commandes import avec_libelles as cmd_libelles
from routes.maintenance import avec_libelles as sav_libelles
from services import est_stockable

router = APIRouter(tags=["Tableau de bord"])


@router.get("/tableau-de-bord")
async def tableau_de_bord(ctx: Contexte = Depends(tout_le_personnel)):
    aujourd_hui = date.today()
    debut_mois = aujourd_hui.replace(day=1).isoformat()
    factures_mois = await ctx.tdb.documents.find(
        {"type_document": "FAC", "statut": "VALIDE", "date": {"$gte": debut_mois}},
        {"_id": 0, "total_ht": 1, "total_ttc": 1, "reglements": 1}).to_list(10000)
    # Chiffre d'affaires par jour sur 30 jours (pour le graphique)
    debut_30 = (aujourd_hui - timedelta(days=29)).isoformat()
    ventes_30 = await ctx.tdb.documents.find(
        {"type_document": "FAC", "statut": "VALIDE", "date": {"$gte": debut_30}},
        {"_id": 0, "date": 1, "total_ht": 1}).to_list(10000)
    par_jour = {(aujourd_hui - timedelta(days=i)).isoformat(): 0 for i in range(29, -1, -1)}
    for f in ventes_30:
        par_jour[f["date"]] = par_jour.get(f["date"], 0) + f["total_ht"]

    produits = await ctx.tdb.produits.find({"actif": True}, {"_id": 0, "id": 1, "nom": 1, "stock": 1, "stock_alerte": 1,
                                                             "type_produit": 1, "reference": 1}).to_list(5000)
    alertes = sorted([p for p in produits if est_stockable(p) and p.get("stock", 0) <= p.get("stock_alerte", 0)],
                     key=lambda p: p.get("stock", 0))
    dossiers = await ctx.tdb.dossiers.find({"statut": {"$ne": "RESTITUE"}}).sort("date_prevue", 1).to_list(500)
    en_retard = [d for d in dossiers if d.get("date_prevue") and d["date_prevue"] < aujourd_hui.isoformat()
                 and d["statut"] not in ("PRET", "IRREPARABLE")]
    commandes = await ctx.tdb.commandes.find({"statut": {"$in": ["RECUE", "CONFIRMEE", "PREPARATION"]}}).sort("date", -1).to_list(50)
    return {
        "ca_mois_ht": sum(f["total_ht"] for f in factures_mois),
        "encaisse_mois": sum(int(r.get("montant", 0)) for f in factures_mois for r in f.get("reglements", [])),
        "nb_factures_mois": len(factures_mois),
        "brouillons": await ctx.tdb.documents.count_documents({"type_document": "FAC", "statut": "BROUILLON"}),
        "ventes_30_jours": [{"date": d, "total_ht": v} for d, v in par_jour.items()],
        "commandes_a_traiter": [cmd_libelles(c) for c in commandes[:10]],
        "nb_commandes_a_traiter": len(commandes),
        "dossiers_en_cours": [sav_libelles(d) for d in dossiers[:10]],
        "nb_dossiers_en_cours": len(dossiers),
        "nb_dossiers_en_retard": len(en_retard),
        "produits_alerte": alertes[:15],
        "nb_produits_alerte": len(alertes),
        "conversations_attente": await ctx.tdb.conversations.count_documents({"statut": "ATTENTE"}),
        # Nouveaux modèles reçus du catalogue public, pas encore consultés
        "nb_nouveautes_catalogue": await ctx.tdb.produits.count_documents({"nouveau": True}),
        "nb_produits_sans_prix": await ctx.tdb.produits.count_documents({"actif": True, "prix_vente": {"$lte": 0}, "type_produit": {"$ne": "SER"}}),
    }
