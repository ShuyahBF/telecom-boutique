"""Routes de la « Transmission WA ».

Super-administrateur (router) :
  - GET  /api/admin/transmission-wa/etat    : canaux configurés (jamais de secret) ;
  - POST /api/admin/transmission-wa/test    : message de test (ordre boutique -> plateforme -> Liluvine) ;
  - GET  /api/admin/transmission-wa/retours : les 100 derniers retours de SAWALI.

Public, signé par SAWALI (public) :
  - POST /api/webhooks/liluvine-retour : statuts, réponses des clients, désinscriptions
    (protocole v3, section 2). Signature HMAC avec LILUVINE_WA_HMAC, horodatage ± 5 min,
    idempotent (un même retour reçu deux fois ne fait qu'une ligne).

Boutique (boutique) — gérant (permission « paramètres ») ou super-admin consultant la boutique :
  - GET    /api/boutique/whatsapp-waba        : réglage du WABA propre (jeton masqué « ******** ») ;
  - PUT    /api/boutique/whatsapp-waba        : enregistrement (jeton chiffré ; vide = conservé) ;
  - DELETE /api/boutique/whatsapp-waba        : suppression du réglage ;
  - POST   /api/boutique/whatsapp-waba/tester : vérifie le compte chez Meta (+ message de test facultatif)."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import envois_plateforme as envois
import transmission_wa as service
from auth import Contexte, get_super_admin, permission
from db import SANS_ID, db
from utils import now_iso

router = APIRouter(prefix="/admin/transmission-wa", tags=["Transmission WA (super-admin)"],
                   dependencies=[Depends(get_super_admin)])
public = APIRouter(prefix="/webhooks", tags=["Transmission WA (retours de SAWALI)"])
boutique = APIRouter(prefix="/boutique/whatsapp-waba", tags=["Transmission WA (WABA de la boutique)"])

MESSAGE_TEST = "Test de transmission WhatsApp depuis adLyn"
JETON_MASQUE = "********"  # affiché à la place du jeton : il n'est JAMAIS renvoyé en clair
TAILLE_MAX_RETOUR = 64_000  # octets : un retour de SAWALI est un petit JSON
parametres = permission("parametres")


class TestIn(BaseModel):
    numero: str = Field(..., min_length=8, max_length=30)  # numéro international, ex. +22670000000
    boutique_id: Optional[str] = Field(None, max_length=64)  # facultatif : teste le canal de cette boutique


# ---- État des canaux (booléens seulement : aucune clé n'est renvoyée) ----
@router.get("/etat")
async def etat():
    return service.etat()


# ---- Envoi d'un message de test ----
@router.post("/test")
async def tester(data: TestIn):
    fiche = None
    if data.boutique_id:
        fiche = await db.boutiques.find_one({"id": data.boutique_id}, SANS_ID)
        if not fiche:
            raise HTTPException(404, "Boutique introuvable")
    resultat = await service.envoyer_whatsapp(data.numero, MESSAGE_TEST, boutique=fiche, modele="")
    # Résultat sans secret : canal utilisé, identifiant du message, erreur éventuelle
    return {k: resultat.get(k) for k in ("ok", "canal", "message_id", "erreur")}


# ---- Les 100 derniers retours de SAWALI (statuts, réponses, désinscriptions) ----
@router.get("/retours")
async def retours(type: str = ""):
    filtre = {"type": type} if type else {}
    lignes = await db.liluvine_retours.find(filtre, SANS_ID).sort("recu_le", -1).to_list(100)
    # Nom de la boutique concernée (si l'envoi d'origine est connu)
    ids = {l["boutique_id"] for l in lignes if l.get("boutique_id")}
    noms = {b["id"]: b["nom"] for b in await db.boutiques.find({"id": {"$in": list(ids)}}, {"_id": 0, "id": 1, "nom": 1})
            .to_list(len(ids) or 1)} if ids else {}
    for l in lignes:
        l["boutique_nom"] = noms.get(l.get("boutique_id"))
    return {"retours": lignes, "chemin_retour": "/api/webhooks/liluvine-retour", **service.etat()}


# ---------------------------------------------------------------------------
# Webhook public : retours signés de SAWALI
# ---------------------------------------------------------------------------
@public.post("/liluvine-retour")
async def recevoir_retour(request: Request, taches: BackgroundTasks):
    # Transmission non configurée : aucune clé pour vérifier la signature
    if not service.liluvine_configure():
        raise HTTPException(503, "Transmission WA Universelle non configurée")
    corps_brut = await request.body()
    if len(corps_brut) > TAILLE_MAX_RETOUR:
        raise HTTPException(413, "Corps trop volumineux")
    # Signature HMAC du corps EXACT reçu + horodatage à ± 5 minutes
    if not service.verifier_signature(request.headers.get("X-Timestamp", ""), corps_brut,
                                      request.headers.get("X-Signature", "")):
        raise HTTPException(401, "Signature invalide ou horodatage hors délai")
    # Contenu : un JSON avec un type connu
    try:
        doc = json.loads(corps_brut)
    except ValueError:
        raise HTTPException(422, "JSON invalide") from None
    if not isinstance(doc, dict) or doc.get("type") not in service.TYPES_RETOUR:
        raise HTTPException(422, "Type de retour inconnu (statut, reponse ou desinscription)")
    nouveau, ligne = await service.enregistrer_retour(doc)
    # Réponse d'un client : signalée aux administrateurs APRÈS la réponse HTTP (réponse rapide)
    if nouveau and ligne["type"] == "reponse":
        taches.add_task(service.signaler_reponse, ligne)
    return {"ok": True, "doublon": not nouveau}


# ---------------------------------------------------------------------------
# WABA propre à la boutique (Paramètres > WhatsApp)
# ---------------------------------------------------------------------------
class WabaIn(BaseModel):
    phone_number_id: str = Field(..., pattern=r"^\d{5,30}$")  # identifiant du numéro chez Meta (chiffres)
    # Jeton d'accès Meta : vide ou « ******** » = jeton enregistré conservé
    access_token: Optional[str] = Field(None, max_length=1000)
    actif: bool = True


class TestWabaIn(BaseModel):
    numero: Optional[str] = Field(None, max_length=30)  # facultatif : envoie aussi un message de test


def waba_public(fiche: dict) -> dict:
    """Réglage WABA renvoyé au navigateur : le jeton est remplacé par « ******** »."""
    conf = fiche.get("whatsapp_waba") or {}
    return {"phone_number_id": conf.get("phone_number_id") or "",
            "access_token": JETON_MASQUE if conf.get("access_token") else "",
            "a_jeton": bool(conf.get("access_token")), "actif": conf.get("actif", True) is not False,
            "configure": bool(service.waba_boutique(fiche)), "modifie_le": conf.get("modifie_le"),
            "modifie_par": conf.get("modifie_par"), "canal_prevu": service.canal_prevu(fiche), **service.etat()}


async def _fiche(ctx: Contexte) -> dict:
    """Fiche boutique relue en base (la version en mémoire peut être ancienne)."""
    return await db.boutiques.find_one({"id": ctx.boutique["id"]}, SANS_ID) or ctx.boutique


@boutique.get("")
async def lire_waba(ctx: Contexte = Depends(parametres)):
    return waba_public(await _fiche(ctx))


@boutique.put("")
async def enregistrer_waba(data: WabaIn, ctx: Contexte = Depends(parametres)):
    actuel = (await _fiche(ctx)).get("whatsapp_waba") or {}
    saisie = (data.access_token or "").strip()
    # Jeton : nouveau jeton chiffré, sinon celui déjà enregistré (vide ou masque = conservé)
    if saisie and saisie != JETON_MASQUE:
        jeton_chiffre = envois.chiffrer(saisie)
    elif actuel.get("access_token"):
        jeton_chiffre = actuel["access_token"]
    else:
        raise HTTPException(400, "Saisissez le jeton d'accès (access token) du compte WhatsApp Business")
    conf = {"phone_number_id": data.phone_number_id, "access_token": jeton_chiffre, "actif": data.actif,
            "modifie_le": now_iso(), "modifie_par": ctx.user.get("email", "")}
    await db.boutiques.update_one({"id": ctx.boutique["id"]}, {"$set": {"whatsapp_waba": conf}})
    return waba_public(await _fiche(ctx))


@boutique.delete("")
async def supprimer_waba(ctx: Contexte = Depends(parametres)):
    await db.boutiques.update_one({"id": ctx.boutique["id"]}, {"$unset": {"whatsapp_waba": ""}})
    return waba_public(await _fiche(ctx))


@boutique.post("/tester")
async def tester_waba(data: TestWabaIn, ctx: Contexte = Depends(parametres)):
    """Bouton « Tester » : vérifie le compte chez Meta SANS repli vers un autre canal,
    puis, si un numéro est indiqué, lui envoie un message de test par CE compte."""
    fiche = await _fiche(ctx)
    conf = fiche.get("whatsapp_waba") or {}
    phone_number_id = str(conf.get("phone_number_id") or "")
    jeton = envois.dechiffrer(conf.get("access_token") or "") if conf.get("access_token") else ""
    if not phone_number_id or not jeton:
        raise HTTPException(400, "Enregistrez d'abord l'identifiant du numéro et le jeton d'accès")
    # 1) Lecture du numéro chez Meta : prouve que l'identifiant et le jeton sont bons
    verification = await envois.verifier_waba((phone_number_id, jeton))
    resultat = {"verification": verification, "envoi": None}
    # 2) Message de test facultatif (texte libre : ne passe que dans la fenêtre de 24 h)
    if verification["ok"] and (data.numero or "").strip():
        statut, erreur, mid = await envois.envoyer_whatsapp_waba(
            data.numero, [], MESSAGE_TEST, modele="", identifiants=(phone_number_id, jeton))
        resultat["envoi"] = {"ok": statut == "ENVOYE", "statut": statut, "message_id": mid,
                             "erreur": (erreur or "").replace(jeton, "***") or None}
    resultat["ok"] = verification["ok"] and (resultat["envoi"] is None or resultat["envoi"]["ok"])
    return resultat
