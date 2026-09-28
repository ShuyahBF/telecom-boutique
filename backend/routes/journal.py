"""Historique des paiements d'une boutique, consultable par période."""
from __future__ import annotations

import csv
import io
from collections import defaultdict

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from auth import Contexte, ventes
from journal_paiements import MODES, STATUTS

router = APIRouter(prefix="/journal-paiements", tags=["Historique des paiements"])


def _filtre(du: str, au: str, statut: str, canal: str, mode: str) -> dict:
    filtre: dict = {}
    if du or au:
        filtre["date"] = {**({"$gte": du} if du else {}), **({"$lte": au + "T23:59:59"} if au else {})}
    if statut:
        filtre["statut"] = statut
    if canal:
        filtre["canal"] = canal
    if mode:
        filtre["mode"] = mode
    return filtre


@router.get("")
async def historique(du: str = "", au: str = "", statut: str = "", canal: str = "", mode: str = "",
                     ctx: Contexte = Depends(ventes)):
    entrees = await ctx.tdb.journal_paiements.find(_filtre(du, au, statut, canal, mode)).sort("date", -1).to_list(5000)
    # Totaux de la période : nombre et montant par statut, encaissé par mode
    par_statut = {k: {"nombre": 0, "montant": 0, "libelle": v} for k, v in STATUTS.items()}
    par_mode: dict = defaultdict(lambda: {"nombre": 0, "montant": 0})
    for e in entrees:
        par_statut[e["statut"]]["nombre"] += 1
        par_statut[e["statut"]]["montant"] += e["montant"]
        if e["statut"] == "SUCCES":
            par_mode[e["mode_libelle"]]["nombre"] += 1
            par_mode[e["mode_libelle"]]["montant"] += e["montant"]
    return {"entrees": entrees, "par_statut": par_statut, "encaisse_par_mode": dict(par_mode),
            "total_encaisse": par_statut["SUCCES"]["montant"], "modes": MODES, "statuts": STATUTS}


@router.get("/export.csv")
async def export_csv(du: str = "", au: str = "", statut: str = "", canal: str = "", mode: str = "",
                     ctx: Contexte = Depends(ventes)):
    """Export tableur (séparateur « ; », lisible directement par Excel en français)."""
    entrees = await ctx.tdb.journal_paiements.find(_filtre(du, au, statut, canal, mode)).sort("date", 1).to_list(None)
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, delimiter=";")
    ecrivain.writerow(["Date", "Canal", "Mode", "Objet", "Client", "Montant", "Devise", "Statut", "Motif", "Référence", "Saisi par"])
    for e in entrees:
        ecrivain.writerow([e["date"][:16].replace("T", " "), e["canal"], e["mode_libelle"], e["objet"], e["client_nom"],
                           e["montant"], e["devise"], STATUTS.get(e["statut"], e["statut"]), e["motif"], e["reference"],
                           e["saisi_par"]])
    # BOM UTF-8 : Excel reconnaît alors les accents
    return Response("﻿" + tampon.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="paiements_{ctx.boutique["code_marchand"]}.csv"'})
