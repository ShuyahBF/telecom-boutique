"""Caisse Aizenta : réception des données de Loois (webhook), écran de la boutique
et administration (super-admin). Le contrat JSON est décrit dans docs/caisse-aizenta.md
et validé par caisse_aizenta.EnvoiCaisse.

    POST /api/webhooks/caisse-aizenta
    Authorization : Bearer <jeton de la boutique>   (généré par le super-admin)
    X-Code-Boutique : K7M2QD                         (facultatif si « code_boutique » est dans le corps)
    Content-Type : application/json

Sécurité du webhook :
  1. jeton PROPRE À CHAQUE BOUTIQUE, stocké haché (SHA-256), comparé à temps constant ;
     un jeton ne donne accès qu'à SA boutique (code boutique vérifié) ;
  2. taille du corps limitée (TAILLE_MAX_CORPS) ;
  3. limitation de fréquence par adresse IP (APPELS_MAX_MINUTE) et blocage
     temporaire d'une adresse après trop d'appels refusés dans l'heure ;
  4. journal de chaque réception (date, boutique, nombre de lignes, résultat,
     erreurs), consultable par le super-admin.
"""
from __future__ import annotations

import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

import caisse_aizenta as caisse
from acces import ip_client
from auth import Contexte, get_super_admin, permission
from config import get_settings
from db import SANS_ID, db

webhook = APIRouter(prefix="/webhooks", tags=["Webhooks"])
boutique = APIRouter(prefix="/caisse-aizenta", tags=["Caisse Aizenta (boutique)"])
admin = APIRouter(prefix="/plateforme/caisse-aizenta", tags=["Caisse Aizenta (super-admin)"])

TAILLE_MAX_CORPS = 8 * 1024 * 1024  # 8 Mo (≈ 20 000 opérations) ; au-delà, découper la période
APPELS_MAX_MINUTE = 30  # appels acceptés par adresse IP et par minute


def url_webhook() -> str:
    """Adresse à saisir dans Loois."""
    return f"{get_settings().public_base_url.rstrip('/')}/api/webhooks/caisse-aizenta"


# ---------------------------------------------------------------------------
# Réception (Loois -> adLyn)
# ---------------------------------------------------------------------------
async def _refuser(ip: str, code: int, message: str, erreurs: Optional[list[str]] = None, **extra) -> JSONResponse:
    """Refus journalisé (et compté pour le blocage de l'adresse IP)."""
    await caisse.journaliser_reception(ip=ip, resultat="REFUSEE", code_http=code, detail=message[:300],
                                       erreurs=erreurs or [], **extra)
    contenu = {"resultat": "refusee", "detail": message}
    if erreurs:
        contenu["erreurs"] = erreurs
    return JSONResponse(contenu, status_code=code)


@webhook.post("/caisse-aizenta")
async def recevoir_caisse(request: Request):
    ip = ip_client(request)
    maintenant = datetime.now(timezone.utc)

    # 1) Limitation de fréquence : trop d'appels dans la minute, ou trop de refus dans l'heure
    if await db.caisse_receptions.count_documents(
            {"ip": ip, "date": {"$gte": (maintenant - timedelta(minutes=1)).isoformat()}}) >= APPELS_MAX_MINUTE:
        return JSONResponse({"resultat": "refusee", "detail": "Trop d'envois, réessayez dans une minute"}, status_code=429)
    if await db.caisse_receptions.count_documents(
            {"ip": ip, "resultat": "REFUSEE", "date": {"$gte": (maintenant - timedelta(hours=1)).isoformat()}}) \
            >= get_settings().webhook_max_echecs_ip:
        return JSONResponse({"resultat": "refusee", "detail": "Trop d'envois refusés, réessayez plus tard"}, status_code=429)

    # 2) Taille du corps (annoncée puis réelle)
    annoncee = request.headers.get("content-length", "")
    if annoncee.isdigit() and int(annoncee) > TAILLE_MAX_CORPS:
        return await _refuser(ip, 413, f"Envoi trop volumineux (maximum {TAILLE_MAX_CORPS // 1024 // 1024} Mo) : découpez la période")
    corps = await request.body()
    if len(corps) > TAILLE_MAX_CORPS:
        return await _refuser(ip, 413, f"Envoi trop volumineux (maximum {TAILLE_MAX_CORPS // 1024 // 1024} Mo) : découpez la période")

    # 3) Jeton présent ?
    entete = request.headers.get("authorization", "")
    jeton = entete[7:].strip() if entete.lower().startswith("bearer ") else ""
    if not jeton:
        return await _refuser(ip, 401, "Jeton absent : en-tête « Authorization: Bearer <jeton> » obligatoire")

    # 4) JSON lisible ?
    try:
        donnees = json.loads(corps)
    except (ValueError, UnicodeDecodeError):
        return await _refuser(ip, 400, "Corps illisible : JSON (UTF-8) attendu")
    if not isinstance(donnees, dict):
        return await _refuser(ip, 400, "Corps invalide : un objet JSON est attendu")

    # 5) Boutique visée : en-tête X-Code-Boutique et/ou champ « code_boutique » (identiques si les deux)
    code_entete = request.headers.get("x-code-boutique", "").strip().upper()
    code_corps = str(donnees.get("code_boutique") or "").strip().upper()
    if code_entete and code_corps and code_entete != code_corps:
        return await _refuser(ip, 400, "Le code boutique de l'en-tête et celui du corps sont différents")
    code = code_entete or code_corps
    if not code:
        return await _refuser(ip, 400, "Code boutique absent (champ « code_boutique » ou en-tête X-Code-Boutique)")
    b = await db.boutiques.find_one({"code_marchand": code}, {"_id": 0, "id": 1, "nom": 1, "code_marchand": 1})
    enregistre = await db.caisse_jetons.find_one({"boutique_id": b["id"]}, SANS_ID) if b else None
    # Même réponse si la boutique n'existe pas ou si le jeton est faux (rien n'est révélé)
    if not enregistre or not hmac.compare_digest(enregistre["hash"], caisse.hacher_jeton(jeton)):
        return await _refuser(ip, 401, "Jeton invalide pour cette boutique", code_boutique=code[:12],
                              boutique_id=(b or {}).get("id"))
    if not code_corps:
        donnees["code_boutique"] = code

    # 6) Contenu conforme au contrat v1 ?
    try:
        envoi = caisse.EnvoiCaisse.model_validate(donnees)
    except ValidationError as exc:
        erreurs = caisse.erreurs_lisibles(exc)
        return await _refuser(ip, 422, "Contenu non conforme au contrat v1", erreurs, code_boutique=code,
                              boutique_id=b["id"], nb_operations=len(donnees.get("operations") or [])
                              if isinstance(donnees.get("operations"), list) else 0)

    # 7) Enregistrement idempotent
    reception_id = caisse.new_id()
    compteurs = await caisse.enregistrer_envoi(b["id"], envoi, reception_id)
    periode = {"du": envoi.periode.du.isoformat(), "au": envoi.periode.au.isoformat()}
    await db.caisse_receptions.insert_one({
        "id": reception_id, "date": caisse.now_iso(), "ip": ip, "resultat": "ACCEPTEE", "code_http": 200,
        "boutique_id": b["id"], "code_boutique": code, "source": envoi.source, "base": envoi.base,
        "version": envoi.version, "genere_le": envoi.genere_le, "periode": periode,
        "remplacer_periode": envoi.remplacer_periode, "erreurs": [], **compteurs})
    return {"resultat": "acceptee", "reception_id": reception_id, "periode": periode, **compteurs}


# ---------------------------------------------------------------------------
# Écran « Caisse Aizenta » de la boutique
# ---------------------------------------------------------------------------
lecture_caisse = permission("caisse_aizenta")


def _periode(du: Optional[str], au: Optional[str]) -> tuple[str, str]:
    try:
        return caisse.borner_periode(du, au)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@boutique.get("/situation")
async def situation(du: Optional[str] = None, au: Optional[str] = None, ctx: Contexte = Depends(lecture_caisse)):
    d, a = _periode(du, au)
    resultat = await caisse.situation(ctx.boutique["id"], d, a)
    resultat["webhook_url"] = url_webhook()
    resultat["code_boutique"] = ctx.boutique.get("code_marchand", "")
    return resultat


@boutique.get("/operations")
async def operations(du: Optional[str] = None, au: Optional[str] = None, type: str = "", mode: str = "",
                     caissier: str = "", q: str = "", page: int = Query(1, ge=1),
                     par_page: int = Query(50, ge=1, le=200), ctx: Contexte = Depends(lecture_caisse)):
    d, a = _periode(du, au)
    ops, _ = await caisse.operations_periode(ctx.boutique["id"], d, a)
    filtrees = caisse.filtrer(ops, type, mode, caissier, q)
    debut = (page - 1) * par_page
    return {"total": len(filtrees), "page": page, "par_page": par_page,
            "total_montant": caisse._arrondi(sum(o["montant"] for o in filtrees)),
            "lignes": filtrees[debut:debut + par_page]}


@boutique.get("/operations.csv")
async def exporter(du: Optional[str] = None, au: Optional[str] = None, type: str = "", mode: str = "",
                   caissier: str = "", q: str = "", ctx: Contexte = Depends(lecture_caisse)):
    d, a = _periode(du, au)
    ops, _ = await caisse.operations_periode(ctx.boutique["id"], d, a)
    contenu = caisse.exporter_csv(caisse.filtrer(ops, type, mode, caissier, q))
    nom = f"caisse_aizenta_{ctx.boutique.get('code_marchand', '')}_{d}_{a}.csv"
    return Response(contenu, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})


# ---------------------------------------------------------------------------
# Administration (super-admin) : jeton de la boutique et journal des réceptions
# ---------------------------------------------------------------------------
async def _boutique_ou_404(boutique_id: str) -> dict:
    b = await db.boutiques.find_one({"id": boutique_id}, {"_id": 0, "id": 1, "nom": 1, "code_marchand": 1})
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    return b


@admin.get("/boutiques/{boutique_id}")
async def etat_boutique(boutique_id: str, _: dict = Depends(get_super_admin)):
    b = await _boutique_ou_404(boutique_id)
    receptions = await db.caisse_receptions.find({"boutique_id": boutique_id}, SANS_ID).sort("date", -1).to_list(50)
    return {"code_boutique": b["code_marchand"], "webhook_url": url_webhook(),
            "jeton": await caisse.infos_jeton(boutique_id),
            "nb_operations": await db.caisse_operations.count_documents({"boutique_id": boutique_id}),
            "receptions": receptions}


@admin.post("/boutiques/{boutique_id}/jeton")
async def generer_jeton(boutique_id: str, utilisateur: dict = Depends(get_super_admin)):
    """Génère (ou régénère) le jeton : il n'est affiché QU'UNE FOIS, l'ancien ne marche plus."""
    b = await _boutique_ou_404(boutique_id)
    jeton = await caisse.generer_jeton(boutique_id, utilisateur.get("email", ""))
    return {"jeton": jeton, "code_boutique": b["code_marchand"], "webhook_url": url_webhook(),
            **(await caisse.infos_jeton(boutique_id) or {})}


@admin.delete("/boutiques/{boutique_id}/jeton")
async def revoquer_jeton(boutique_id: str, _: dict = Depends(get_super_admin)):
    """Coupe la réception (les données déjà reçues sont conservées)."""
    await _boutique_ou_404(boutique_id)
    await db.caisse_jetons.delete_many({"boutique_id": boutique_id})
    return {"ok": True}


@admin.get("/receptions")
async def journal(boutique_id: str = "", resultat: str = "", _: dict = Depends(get_super_admin)):
    filtre = {}
    if boutique_id:
        filtre["boutique_id"] = boutique_id
    if resultat:
        filtre["resultat"] = resultat
    return await db.caisse_receptions.find(filtre, SANS_ID).sort("date", -1).to_list(200)
