"""Mot de passe oublié et changement de ses propres identifiants (e-mail / téléphone).

1) MOT DE PASSE OUBLIÉ (page de connexion, sans être connecté) :
   ID boutique + e-mail ou téléphone -> code à 6 chiffres envoyé par WhatsApp
   (SMS en repli, e-mail si le compte n'a qu'un e-mail) -> code + nouveau mot
   de passe. La réponse est LA MÊME que le compte existe ou non (on ne révèle
   rien), et toutes les sessions ouvertes du compte sont fermées ensuite.

2) MON COMPTE (tout utilisateur connecté d'une boutique) : changer, vérifier ou
   retirer son e-mail ou son téléphone. Mot de passe actuel + nouvelle valeur
   -> code envoyé À LA NOUVELLE VALEUR (WhatsApp/SMS pour un téléphone, e-mail
   pour une adresse) -> confirmation. On ne peut retirer un identifiant que si
   l'autre existe et a été vérifié : un compte n'est jamais sans identifiant.

Les règles de sécurité (10 minutes, 5 essais, 15 minutes de blocage, 1 envoi
par minute et 5 par heure) sont dans identifiants.py.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import identifiants as service
import maintenance_plateforme
from acces import ip_client
from auth import get_current_user, hash_password, user_public, verify_password
from db import SANS_ID, db

router = APIRouter(prefix="/auth", tags=["Identifiants et mot de passe oublié"])

# Réponse identique, que le compte existe ou non
MESSAGE_DEMANDE = ("Si ces informations correspondent à un compte, un code à 6 chiffres vient d'être envoyé "
                   "(par WhatsApp, sinon par SMS ou par e-mail). Il est valable 10 minutes.")
TROP_DE_DEMANDES = "Patientez avant de redemander un code (1 par minute et 5 par heure au maximum)."
TROP_D_ESSAIS = "Trop d'essais : réessayez dans 15 minutes."


def _code_boutique(texte: Optional[str]) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", texte or "").upper()


async def _compte_de_la_boutique(code_boutique: str, saisie: str) -> tuple[Optional[dict], Optional[dict], str]:
    """(compte, boutique, valeur normalisée) — compte None s'il n'existe pas, est
    désactivé, n'appartient pas à cette boutique, ou est le super-administrateur
    (son mot de passe se réinitialise par la configuration du serveur)."""
    type_, valeur = service.lire_identifiant(saisie)
    boutique = await db.boutiques.find_one({"code_marchand": code_boutique}, SANS_ID) if code_boutique else None
    user = await service.trouver_compte(type_, valeur)
    if not (user and boutique and user.get("boutique_id") == boutique["id"] and user.get("actif", True)
            and user.get("role") != "super_admin"):
        user = None
    return user, boutique, valeur or saisie.strip().lower()[:200]


# ---------------------------------------------------------------------------
# 1) Mot de passe oublié
# ---------------------------------------------------------------------------
class DemandeCode(BaseModel):
    code_boutique: str = Field(..., max_length=20)
    identifiant: str = Field(..., max_length=200)  # e-mail ou téléphone


@router.post("/mot-de-passe-oublie")
async def demander_code(payload: DemandeCode, request: Request, taches: BackgroundTasks):
    await maintenance_plateforme.refuser_si_maintenance()  # personnel bloqué pendant la maintenance
    code_b = _code_boutique(payload.code_boutique)
    user, boutique, valeur = await _compte_de_la_boutique(code_b, payload.identifiant)
    ip = ip_client(request)
    # Limites par identifiant tapé et par adresse IP : ne dépendent pas de l'existence du compte
    cles = [f"reinit|{code_b}|{valeur}", f"reinit-ip|{ip}"]
    if await service.limite_atteinte(cles):
        raise HTTPException(429, TROP_DE_DEMANDES)
    await service.noter_envoi(cles)
    if not user:
        await service.journaliser("CODE_DEMANDE_INCONNU", boutique_id=(boutique or {}).get("id"), request=request,
                                  identifiant=valeur)
        return {"ok": True, "message": MESSAGE_DEMANDE}
    # Limite par COMPTE (même s'il est désigné tantôt par son e-mail, tantôt par son téléphone) :
    # dépassée, on ne renvoie rien de plus, mais la réponse reste la même
    cle_compte = [f"reinit-compte|{user['id']}"]
    if await service.limite_atteinte(cle_compte):
        await service.journaliser("CODE_DEMANDE", cible=user, request=request, statut="LIMITE",
                                  details={"raison": "limite d'envoi du compte atteinte"})
        return {"ok": True, "message": MESSAGE_DEMANDE}
    await service.noter_envoi(cle_compte)
    code = await service.creer_code(user["id"], service.REINIT_MDP)

    async def _envoyer():
        # Après la réponse : le temps de réponse ne trahit pas l'existence du compte
        sujet, texte = service.texte_code(code, service.REINIT_MDP)
        envoi = await service.envoyer_message(telephone=user.get("telephone"), email=user.get("email"),
                                              sujet=sujet, texte=texte, code=code, boutique=boutique)
        if envoi["canal"]:
            # Retenu pour marquer ensuite ce contact comme « vérifié »
            await db.codes_verification.update_one({"user_id": user["id"], "objet": service.REINIT_MDP},
                                                   {"$set": {"canal": envoi["canal"]}})
        await service.journaliser("CODE_DEMANDE", cible=user, request=request, canal=envoi["canal"],
                                  statut=envoi["statut"], details={"erreur": envoi["erreur"]} if envoi["erreur"] else {})

    taches.add_task(_envoyer)
    return {"ok": True, "message": MESSAGE_DEMANDE}


class ConfirmationCode(DemandeCode):
    code: str = Field(..., max_length=12)
    nouveau: str = Field(..., min_length=8, max_length=200)


@router.post("/mot-de-passe-oublie/confirmer")
async def confirmer_code(payload: ConfirmationCode, request: Request):
    await maintenance_plateforme.refuser_si_maintenance()
    code_b = _code_boutique(payload.code_boutique)
    user, _, valeur = await _compte_de_la_boutique(code_b, payload.identifiant)
    cle = f"reinit-essais|{user['id']}" if user else f"reinit-essais|{code_b}|{valeur}"
    cle_ip = f"reinit-essais-ip|{ip_client(request)}"
    if await service.est_bloque(cle) or await service.est_bloque(cle_ip):
        raise HTTPException(429, TROP_D_ESSAIS)
    doc = await service.verifier_code(user["id"], service.REINIT_MDP, payload.code) if user else None
    if not doc:
        bloque = await service.noter_echec(cle)
        await service.noter_echec(cle_ip, service.MAX_ESSAIS_IP)
        if user:
            await service.journaliser("CODE_BLOQUE" if bloque else "CODE_ECHEC", cible=user, request=request)
            if bloque:
                await service.annuler_code(user["id"], service.REINIT_MDP)  # il faudra en redemander un
        raise HTTPException(429 if bloque else 400, TROP_D_ESSAIS if bloque else "Code incorrect ou expiré")
    maj = {"password_hash": hash_password(payload.nouveau), "doit_changer_mot_de_passe": False}
    # Le code est arrivé : ce contact est donc bien celui de la personne
    if doc.get("canal") in ("WHATSAPP", "SMS") and user.get("telephone"):
        maj["telephone_verifie"] = True
    elif doc.get("canal") == "EMAIL" and user.get("email"):
        maj["email_verifie"] = True
    # version_session + 1 : TOUTES les sessions ouvertes du compte sont fermées
    await db.users.update_one({"id": user["id"]}, {"$set": maj, "$inc": {"version_session": 1}})
    await service.effacer_echecs(cle)
    await db.echecs_connexion.delete_many({"cle": f"{code_b}|{valeur}"})
    await service.journaliser("MDP_REINITIALISE", cible=user, request=request, canal=doc.get("canal"))
    return {"ok": True, "message": "Mot de passe modifié. Connectez-vous avec votre nouveau mot de passe."}


# ---------------------------------------------------------------------------
# 2) Mon compte : changer / vérifier / retirer son e-mail ou son téléphone
# ---------------------------------------------------------------------------
TypeIdentifiant = Literal["email", "telephone"]
OBJET = {"email": service.CHANGEMENT_EMAIL, "telephone": service.CHANGEMENT_TELEPHONE}


async def _verifier_mot_de_passe(user: dict, mot_de_passe: str) -> None:
    """Mot de passe actuel exigé (avec la même protection : 5 erreurs -> 15 minutes de pause)."""
    if user.get("role") == "super_admin":
        raise HTTPException(403, "Compte administrateur : son e-mail est fixé par la configuration du serveur")
    cle = f"mdp-identifiant|{user['id']}"
    if await service.est_bloque(cle):
        raise HTTPException(429, TROP_D_ESSAIS)
    complet = await db.users.find_one({"id": user["id"]}, SANS_ID)
    if not verify_password(mot_de_passe, complet.get("password_hash", "")):
        bloque = await service.noter_echec(cle)
        raise HTTPException(429 if bloque else 400, TROP_D_ESSAIS if bloque else "Mot de passe actuel incorrect")
    await service.effacer_echecs(cle)


class DemandeChangement(BaseModel):
    type: TypeIdentifiant
    valeur: str = Field(..., max_length=200)
    mot_de_passe: str = Field(..., max_length=200)


@router.post("/identifiant/demande")
async def demander_changement(payload: DemandeChangement, request: Request, user: dict = Depends(get_current_user)):
    await _verifier_mot_de_passe(user, payload.mot_de_passe)
    valeur = service.valeur_normalisee(payload.type, payload.valeur)
    if valeur == user.get(payload.type) and user.get(f"{payload.type}_verifie"):
        raise HTTPException(400, f"C'est déjà votre {service.LIBELLES_TYPE[payload.type]}, et il est vérifié")
    await service.verifier_disponible(payload.type, valeur, sauf_user_id=user["id"])
    cles = [f"identifiant|{user['id']}", f"identifiant-ip|{ip_client(request)}"]
    if await service.limite_atteinte(cles):
        raise HTTPException(429, TROP_DE_DEMANDES)
    await service.noter_envoi(cles)
    objet = OBJET[payload.type]
    code = await service.creer_code(user["id"], objet, valeur)
    sujet, texte = service.texte_code(code, objet)
    boutique = await db.boutiques.find_one({"id": user.get("boutique_id")}, SANS_ID) if user.get("boutique_id") else None
    # Le code part vers la NOUVELLE valeur : c'est elle qu'on vérifie
    cible = {"telephone": valeur} if payload.type == "telephone" else {"email": valeur}
    envoi = await service.envoyer_message(**cible, sujet=sujet, texte=texte, code=code, boutique=boutique)
    await service.journaliser("IDENTIFIANT_CODE_DEMANDE", cible=user, par=user, request=request, identifiant=valeur,
                              canal=envoi["canal"], statut=envoi["statut"], details={"type": payload.type})
    if envoi["statut"] != "ENVOYE":
        await service.annuler_code(user["id"], objet)
        raise HTTPException(503, f"Le code n'a pas pu être envoyé ({envoi['erreur']}). "
                                 "Réessayez plus tard ou demandez au DG de modifier votre identifiant.")
    return {"ok": True, "canal": envoi["canal"], "destination": service.masquer(valeur),
            "message": f"Code envoyé par {service.CANAUX[envoi['canal']]} au {service.masquer(valeur)}. "
                       "Il est valable 10 minutes."}


class ConfirmationChangement(BaseModel):
    type: TypeIdentifiant
    code: str = Field(..., max_length=12)


@router.post("/identifiant/confirmer")
async def confirmer_changement(payload: ConfirmationChangement, request: Request,
                               user: dict = Depends(get_current_user)):
    if user.get("role") == "super_admin":
        raise HTTPException(403, "Compte administrateur : son e-mail est fixé par la configuration du serveur")
    objet = OBJET[payload.type]
    cle = f"identifiant-essais|{user['id']}"
    if await service.est_bloque(cle):
        raise HTTPException(429, TROP_D_ESSAIS)
    doc = await service.verifier_code(user["id"], objet, payload.code)
    if not doc:
        bloque = await service.noter_echec(cle)
        await service.journaliser("CODE_BLOQUE" if bloque else "CODE_ECHEC", cible=user, par=user, request=request,
                                  details={"type": payload.type})
        if bloque:
            await service.annuler_code(user["id"], objet)
        raise HTTPException(429 if bloque else 400, TROP_D_ESSAIS if bloque else "Code incorrect ou expiré")
    await service.effacer_echecs(cle)
    valeur, ancien = doc["valeur"], user.get(payload.type)
    await service.verifier_disponible(payload.type, valeur, sauf_user_id=user["id"])
    await service._appliquer(user["id"], {"$set": {payload.type: valeur, f"{payload.type}_verifie": True}})
    if ancien != valeur:
        boutique = await db.boutiques.find_one({"id": user.get("boutique_id")}, SANS_ID) if user.get("boutique_id") else None
        await service.notifier_changement(user, boutique, payload.type, ancien, valeur, "par vous-meme")
        await service.journaliser("IDENTIFIANT_MODIFIE", cible=user, par=user, request=request,
                                  details={"type": payload.type, "ancien": ancien or "", "nouveau": valeur})
    return user_public(await db.users.find_one({"id": user["id"]}, SANS_ID))


class Retrait(BaseModel):
    type: TypeIdentifiant
    mot_de_passe: str = Field(..., max_length=200)


@router.post("/identifiant/retirer")
async def retirer_identifiant(payload: Retrait, request: Request, user: dict = Depends(get_current_user)):
    await _verifier_mot_de_passe(user, payload.mot_de_passe)
    autre = "telephone" if payload.type == "email" else "email"
    if not user.get(payload.type):
        raise HTTPException(400, f"Votre compte n'a pas de {service.LIBELLES_TYPE[payload.type]}")
    if not (user.get(autre) and user.get(f"{autre}_verifie")):
        raise HTTPException(400, f"Ajoutez et vérifiez d'abord votre {service.LIBELLES_TYPE[autre]} : "
                                 "un compte doit toujours garder un identifiant vérifié")
    ancien = user[payload.type]
    await db.users.update_one({"id": user["id"]}, {"$unset": {payload.type: "", f"{payload.type}_verifie": ""}})
    boutique = await db.boutiques.find_one({"id": user.get("boutique_id")}, SANS_ID) if user.get("boutique_id") else None
    await service.notifier_changement(user, boutique, payload.type, ancien, None, "par vous-meme")
    await service.journaliser("IDENTIFIANT_RETIRE", cible=user, par=user, request=request,
                              details={"type": payload.type, "ancien": ancien})
    return user_public(await db.users.find_one({"id": user["id"]}, SANS_ID))
