"""Support SAWALI dans l'espace de gestion des boutiques adLyn (SAWALI lot 90).

Demande du propriétaire (09/10/2026) : un petit pictogramme d'assistance dans
l'espace de gestion de chaque boutique ouvre une fenêtre de discussion avec le
support SAWALI. Côté SAWALI, les messages arrivent dans le chat de l'équipe,
espace « adLyn - Support », avec un numéro de requête (SUP-…).

En résumé (pour un développeur WinDev) :
  - le NAVIGATEUR ne parle jamais directement à SAWALI : il appelle CE serveur
    (gérant ou membre du personnel connecté), qui relaie vers SAWALI une requête
    SIGNÉE avec la clé d'émetteur déjà utilisée pour la Transmission WA
    (variables Render LILUVINE_WA_HMAC et LILUVINE_WA_EMETTEUR) :
    en-têtes X-Emetteur, X-Timestamp, X-Signature = HMAC-SHA256 de
    « <horodatage>.<corps brut> » (même fonction signer() que transmission_wa.py) ;
  - adresse de SAWALI : SAWALI_API_URL si elle existe, sinon déduite de
    LILUVINE_WA_URL (schéma + hôte), sinon https://api.sawalismartsystems.com ;
  - routes (personnel connecté d'une boutique) :
      GET  /api/support-sawali/etat      → pictogramme affiché ou non (clé présente)
      POST /api/support-sawali/messages  {texte}            → message envoyé au support
      POST /api/support-sawali/fil       {depuis, marquer_lu} → messages, réponses, état
  - aucun secret n'est renvoyé au navigateur ni journalisé.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import Contexte, tout_le_personnel
from config import get_settings
from transmission_wa import signer  # même signature HMAC que la Transmission WA

DELAI_SECONDES = 15                                  # délai maximal d'un appel à SAWALI
SAWALI_PAR_DEFAUT = "https://api.sawalismartsystems.com"
EMETTEUR_DEFAUT = "adlyn"                            # code de la plateforme dans SAWALI (pas secret)

# Transport HTTP de remplacement (tests) : None en production
_transport: Optional[httpx.AsyncBaseTransport] = None


# ---------------------------------------------------------------------------
# Configuration (variables d'environnement saisies sur Render, lues via config.py)
# ---------------------------------------------------------------------------
def cle() -> str:
    """Clé HMAC d'adLyn chez SAWALI (secrète : jamais affichée ni renvoyée)."""
    return (get_settings().liluvine_wa_hmac or "").strip()


def emetteur() -> str:
    """Code de la plateforme dans SAWALI (en-tête X-Emetteur)."""
    return (get_settings().liluvine_wa_emetteur or "").strip() or EMETTEUR_DEFAUT


def url_sawali() -> str:
    """Adresse de SAWALI : SAWALI_API_URL, sinon schéma + hôte de LILUVINE_WA_URL, sinon l'adresse par défaut."""
    direct = (os.environ.get("SAWALI_API_URL") or "").strip().rstrip("/")
    if direct:
        return direct
    lu = urlparse((get_settings().liluvine_wa_url or "").strip())
    if lu.scheme and lu.netloc:
        return f"{lu.scheme}://{lu.netloc}"
    return SAWALI_PAR_DEFAUT


def configure() -> bool:
    """Vrai si la clé est saisie (sinon le pictogramme reste caché)."""
    return bool(cle())


# ---------------------------------------------------------------------------
# Appel signé vers SAWALI
# ---------------------------------------------------------------------------
async def appeler_sawali(chemin: str, corps: Dict[str, Any]) -> Dict[str, Any]:
    """POST signé vers SAWALI ; renvoie le JSON ou lève une HTTPException lisible pour l'utilisateur."""
    if not configure():
        raise HTTPException(status_code=503, detail="Support SAWALI non configuré sur cette plateforme")
    # Corps sérialisé UNE SEULE FOIS : ce sont exactement ces octets qui sont signés et envoyés
    brut = json.dumps(corps, ensure_ascii=False).encode("utf-8")
    ts = str(int(time.time()))
    entetes = {"Content-Type": "application/json", "X-Emetteur": emetteur(), "X-Timestamp": ts,
               "X-Signature": signer(cle(), ts, brut)}
    try:
        async with httpx.AsyncClient(timeout=DELAI_SECONDES, transport=_transport) as client:
            r = await client.post(f"{url_sawali()}/api{chemin}", content=brut, headers=entetes)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Support SAWALI injoignable : réessayez dans un instant")
    # 403 chez SAWALI : la plateforme n'est pas (encore) autorisée à utiliser le support
    if r.status_code == 403:
        raise HTTPException(status_code=503, detail="Support SAWALI pas encore activé pour cette plateforme")
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail="Le support SAWALI a refusé la demande")
    try:
        return r.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Réponse illisible du support SAWALI")


# ---------------------------------------------------------------------------
# Identité envoyée à SAWALI (qui écrit, depuis quelle boutique)
# ---------------------------------------------------------------------------
def identite(ctx: Contexte) -> Dict[str, str]:
    """{id, nom, role, contexte = nom de la boutique, email, telephone} — aucun secret."""
    u, b = ctx.user, ctx.boutique or {}
    return {"id": str(u.get("id", "")), "nom": u.get("nom") or u.get("email") or "",
            "role": u.get("role") or "", "contexte": b.get("nom") or "",
            "email": u.get("email") or "", "telephone": u.get("telephone") or b.get("telephone") or ""}


# ---------------------------------------------------------------------------
# Routes (personnel connecté de la boutique : gérant / DG et équipe)
# ---------------------------------------------------------------------------
class MessageEntree(BaseModel):
    texte: str = Field(..., min_length=1, max_length=2000)


class FilEntree(BaseModel):
    depuis: Optional[str] = Field(None, max_length=40)
    marquer_lu: bool = True   # faux : simple vérification des non-lus (fenêtre fermée), rien n'est marqué lu


router = APIRouter(prefix="/support-sawali", tags=["Support SAWALI"])


@router.get("/etat")
async def etat(ctx: Contexte = Depends(tout_le_personnel)):
    """Pictogramme affiché seulement si la plateforme est reliée à SAWALI."""
    return {"actif": configure()}


@router.post("/messages")
async def envoyer(entree: MessageEntree, ctx: Contexte = Depends(tout_le_personnel)):
    """Message de l'utilisateur vers le support SAWALI."""
    texte = entree.texte.strip()
    if not texte:
        raise HTTPException(status_code=422, detail="Message vide")
    return await appeler_sawali("/support-plateforme/messages", {"utilisateur": identite(ctx), "texte": texte})


@router.post("/fil")
async def fil(entree: FilEntree, ctx: Contexte = Depends(tout_le_personnel)):
    """Messages de l'utilisateur et réponses du support (depuis une date), état de sa requête."""
    corps: Dict[str, Any] = {"utilisateur": identite(ctx), "marquer_lu": entree.marquer_lu}
    if entree.depuis:
        corps["depuis"] = entree.depuis
    return await appeler_sawali("/support-plateforme/fil", corps)
