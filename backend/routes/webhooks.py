"""Webhook de création AUTOMATIQUE des boutiques, sécurisé par signature HMAC.

Un système externe (formulaire d'inscription, CRM, partenaire...) envoie :

    POST /api/webhooks/boutiques
    X-Adlyn-Horodatage : 1790000000                  (secondes Unix, heure de l'envoi)
    X-Adlyn-Signature  : sha256=<hex>                (HMAC-SHA256, voir ci-dessous)
    Content-Type       : application/json
    {"evenement_id": "insc-2026-000123", "nom": "Boutique Étoile", "pays": "Burkina Faso",
     "ville": "Ouagadougou", "telephone": "+22625000000", "dg_nom": "Awa Ouédraogo",
     "dg_email": "awa@exemple.bf", "dg_telephone": "+22670000000", ...}

    signature = HMAC_SHA256(WEBHOOK_BOUTIQUES_SECRET, "<horodatage>." + <corps brut>)

La boutique est créée si elle n'existe pas, sinon la demande est IGNORÉE.

Protections contre les créations « pour s'amuser » :
  1. signature HMAC : sans le secret partagé, aucune demande n'est acceptée ;
  2. horodatage à ± 5 minutes + identifiant d'événement à usage unique :
     une demande interceptée ne peut pas être rejouée ;
  3. contrôles de vraisemblance (nom réaliste, e-mail non jetable, téléphone valide) ;
  4. quota de créations par 24 h + blocage d'une adresse IP après trop d'échecs ;
  5. la boutique reste INVISIBLE du public tant que le super-administrateur
     ne l'a pas validée (le DG peut déjà se connecter et préparer sa boutique) ;
  6. journal de chaque appel (accepté, ignoré ou refusé), consultable par le super-admin.
Le mot de passe provisoire du DG n'apparaît JAMAIS dans la réponse : il est
envoyé au DG lui-même, par e-mail et SMS.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, ValidationError
from pymongo.errors import DuplicateKeyError

import envois_plateforme as envois
from acces import ip_client
from auth import get_super_admin
from config import get_settings
from db import SANS_ID, db
from routes.plateforme import enregistrer_boutique, envoyer_identifiants, mot_de_passe_temporaire
from utils import new_id, normaliser_telephone, now_iso, slugifier

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
admin = APIRouter(prefix="/plateforme/webhooks", tags=["Webhooks (super-admin)"])

TAILLE_MAX_CORPS = 20_000  # octets : une demande de création est un petit JSON

# Noms manifestement fantaisistes (comparés au nom « simplifié », sans accents ni espaces)
NOMS_INTERDITS = {"test", "tests", "essai", "demo", "fake", "faux", "azerty", "qwerty", "toto", "tata",
                  "titi", "blabla", "xxx", "aaa", "abc", "lol", "boutique", "shop", "admin", "adlyn"}
# Services d'adresses e-mail jetables
DOMAINES_JETABLES = {"mailinator.com", "yopmail.com", "yopmail.fr", "guerrillamail.com", "10minutemail.com",
                     "tempmail.com", "temp-mail.org", "trashmail.com", "sharklasers.com", "getnada.com",
                     "dispostable.com", "maildrop.cc", "throwawaymail.com", "fakeinbox.com"}


class DemandeBoutique(BaseModel):
    """Contenu attendu. Champs inconnus refusés (extra="forbid") pour détecter les erreurs d'intégration."""
    model_config = {"extra": "forbid"}

    evenement_id: str = Field(..., min_length=8, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    nom: str = Field(..., min_length=3, max_length=120)
    pays: str = Field("Burkina Faso", min_length=2, max_length=60)
    ville: str = Field(..., min_length=2, max_length=80)
    adresse: str = Field("", max_length=500)
    telephone: str = Field("", max_length=30)
    email: Optional[EmailStr] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    dg_nom: str = Field(..., min_length=3, max_length=120)
    dg_email: EmailStr
    dg_telephone: str = Field(..., min_length=8, max_length=30)
    ifu: str = Field("", max_length=50)
    cnss: str = Field("", max_length=50)
    rccm: str = Field("", max_length=60)
    # Identifiant de la boutique dans le système appelant (facultatif)
    reference_externe: Optional[str] = Field(None, max_length=100)


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------
def signature_attendue(secret: str, horodatage: str, corps: bytes) -> str:
    """Signature « sha256=<hex> » d'une demande (utilisable aussi par l'appelant)."""
    mac = hmac.new(secret.encode(), horodatage.encode() + b"." + corps, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def _ip(request: Request) -> str:
    return ip_client(request)


async def _journaliser(ip: str, resultat: str, detail: str = "", **extra) -> None:
    await db.webhook_journal.insert_one({"id": new_id(), "date": now_iso(), "type": "boutique",
                                         "ip": ip, "resultat": resultat, "detail": detail[:500], **extra})


async def _refuser(ip: str, code: int, message: str, **extra) -> JSONResponse:
    """Refus journalisé et compté pour le blocage de l'adresse IP."""
    await _journaliser(ip, "REFUSEE", message, code_http=code, **extra)
    return JSONResponse({"resultat": "refusee", "detail": message}, status_code=code)


def _invraisemblance(d: DemandeBoutique) -> Optional[str]:
    """Contrôles anti-plaisantins ; renvoie la raison du refus, ou None."""
    lettres = re.sub(r"[^a-zA-Z]", "", slugifier(d.nom))
    if len(lettres) < 3:
        return "Nom de boutique non valable (au moins 3 lettres)"
    if slugifier(d.nom).replace("-", "") in NOMS_INTERDITS or re.search(r"(.)\1{3,}", d.nom.lower()):
        return "Nom de boutique non valable"
    if re.search(r"https?://|www\.|<|>", d.nom + d.dg_nom):
        return "Les liens et balises ne sont pas acceptés"
    if len(re.sub(r"[^a-zA-Z]", "", slugifier(d.dg_nom))) < 3:
        return "Nom du DG non valable"
    if d.dg_email.split("@")[-1].lower() in DOMAINES_JETABLES:
        return "Adresse e-mail jetable refusée"
    if not envois.msisdn(d.dg_telephone):
        return "Téléphone du DG non valable"
    return None


async def _boutique_existante(d: DemandeBoutique) -> Optional[dict]:
    """Même nom (à la casse et aux accents près), même référence externe, ou DG déjà inscrit."""
    base = slugifier(d.nom)
    candidates = db.boutiques.find({"slug": {"$regex": f"^{re.escape(base)}(-[0-9]+)?$"}},
                                   {"_id": 0, "id": 1, "nom": 1})
    async for b in candidates:
        if slugifier(b["nom"]) == base:
            return b
    if d.reference_externe:
        b = await db.boutiques.find_one({"reference_externe": d.reference_externe}, {"_id": 0, "id": 1, "nom": 1})
        if b:
            return b
    if await db.users.find_one({"email": d.dg_email.lower()}, {"_id": 0, "id": 1}):
        return {"id": None, "nom": "(compte DG déjà existant)"}
    return None


# ---------------------------------------------------------------------------
# Réception
# ---------------------------------------------------------------------------
@router.post("/boutiques")
async def recevoir_boutique(request: Request):
    s = get_settings()
    ip = _ip(request)
    if not s.webhook_boutiques_secret:
        raise HTTPException(503, "Webhook non configuré sur le serveur")

    # 1) Adresse IP bloquée après trop d'échecs dans l'heure
    depuis = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    if await db.webhook_journal.count_documents({"ip": ip, "resultat": "REFUSEE", "date": {"$gte": depuis}}) \
            >= s.webhook_max_echecs_ip:
        return JSONResponse({"resultat": "refusee", "detail": "Trop de demandes refusées, réessayez plus tard"},
                            status_code=429)

    # 2) Corps brut (la signature porte sur les octets exacts reçus)
    corps = await request.body()
    if len(corps) > TAILLE_MAX_CORPS:
        return await _refuser(ip, 413, "Demande trop volumineuse")

    # 3) Horodatage récent + signature HMAC (comparaison à temps constant)
    horodatage = request.headers.get("x-adlyn-horodatage", "")
    signature = request.headers.get("x-adlyn-signature", "")
    if not horodatage.isdigit() or abs(time.time() - int(horodatage)) > s.webhook_fenetre_secondes:
        return await _refuser(ip, 401, "Horodatage absent ou hors délai")
    if not hmac.compare_digest(signature, signature_attendue(s.webhook_boutiques_secret, horodatage, corps)):
        return await _refuser(ip, 401, "Signature invalide")

    # 4) Contenu
    try:
        demande = DemandeBoutique(**json.loads(corps))
    except (ValueError, ValidationError, TypeError) as exc:
        return await _refuser(ip, 422, f"Contenu invalide : {str(exc)[:300]}")

    # 5) Anti-rejeu : chaque evenement_id n'est accepté qu'une fois
    try:
        await db.webhook_nonces.insert_one({"_id": demande.evenement_id, "date": now_iso(),
                                            "expire_le": datetime.now(timezone.utc) + timedelta(days=7)})
    except DuplicateKeyError:
        return await _refuser(ip, 409, "Événement déjà reçu (rejeu)", evenement_id=demande.evenement_id)

    # 6) Vraisemblance
    raison = _invraisemblance(demande)
    if raison:
        return await _refuser(ip, 422, raison, evenement_id=demande.evenement_id, nom=demande.nom)

    # 7) Boutique déjà existante : demande ignorée (sans rien révéler de la boutique)
    existante = await _boutique_existante(demande)
    if existante:
        await _journaliser(ip, "IGNOREE", f"Existe déjà : {existante['nom']}", evenement_id=demande.evenement_id,
                           nom=demande.nom, boutique_id=existante["id"])
        return {"resultat": "ignoree", "detail": "Cette boutique existe déjà"}

    # 8) Quota de créations sur 24 h glissantes
    hier = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    if await db.boutiques.count_documents({"origine": "webhook", "created_at": {"$gte": hier}}) >= s.webhook_quota_jour:
        await _journaliser(ip, "QUOTA", "Quota journalier atteint", evenement_id=demande.evenement_id, nom=demande.nom)
        return JSONResponse({"resultat": "refusee", "detail": "Quota de créations atteint, réessayez demain"},
                            status_code=429)

    # 9) Création : boutique EN ATTENTE DE VALIDATION + DG avec mot de passe provisoire
    mot_de_passe = mot_de_passe_temporaire()
    donnees = demande.model_dump(exclude={"evenement_id", "dg_email", "reference_externe"})
    donnees["dg_telephone"] = normaliser_telephone(demande.dg_telephone)
    boutique, dg, nb_produits = await enregistrer_boutique(
        donnees, dg_email=demande.dg_email, dg_mot_de_passe=mot_de_passe, validee=False,
        origine="webhook", doit_changer_mot_de_passe=True)
    if demande.reference_externe:
        await db.boutiques.update_one({"id": boutique["id"]}, {"$set": {"reference_externe": demande.reference_externe}})
    envoi = await envoyer_identifiants(boutique, dg, mot_de_passe, demande.dg_telephone)
    await _journaliser(ip, "CREEE", f"{boutique['code_marchand']} — {boutique['nom']}",
                       evenement_id=demande.evenement_id, nom=demande.nom, boutique_id=boutique["id"])
    # Prévenir l'administrateur de la plateforme : une boutique attend sa validation
    if s.rapport_email:
        await envois.envoyer_email(
            f"[adLyn] Nouvelle boutique à valider : {boutique['nom']}",
            "\n".join([f"Boutique : {boutique['nom']} ({boutique['ville']}, {boutique['pays']})",
                       f"ID boutique : {boutique['code_marchand']}",
                       f"DG : {dg['nom']} — {dg['email']} — {donnees['dg_telephone']}",
                       f"Identifiants envoyés : WhatsApp {envoi.get('whatsapp')}, SMS {envoi['sms']}, e-mail {envoi['email']}", "",
                       f"À valider dans l'administration : {s.public_site_url}/plateforme"]),
            s.rapport_email)
    return JSONResponse(status_code=201, content={
        "resultat": "creee", "code_boutique": boutique["code_marchand"], "statut": "EN_ATTENTE_VALIDATION",
        "produits_copies": nb_produits, "identifiants_envoyes": {"email": envoi["email"], "sms": envoi["sms"], "whatsapp": envoi.get("whatsapp")}})


# ---------------------------------------------------------------------------
# Journal (super-admin)
# ---------------------------------------------------------------------------
@admin.get("/journal")
async def journal(resultat: str = "", _: dict = Depends(get_super_admin)):
    filtre = {"resultat": resultat} if resultat else {}
    lignes = await db.webhook_journal.find(filtre, SANS_ID).sort("date", -1).to_list(200)
    return {"configure": bool(get_settings().webhook_boutiques_secret), "quota_jour": get_settings().webhook_quota_jour,
            "lignes": lignes}
