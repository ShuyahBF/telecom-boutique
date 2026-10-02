"""Fermeture des sessions d'un compte, SANS changer son mot de passe ni le désactiver
(téléphone perdu, poste partagé…).

Principe : la version de session du compte (`version_session`) est augmentée de 1 ;
tous les jetons déjà distribués deviennent invalides (voir auth.get_current_user).
Quand c'est un responsable (DG ou administrateur) qui ferme les sessions, l'heure
de la fermeture est notée (`sessions_fermees_par_admin_le`) : l'utilisateur
déconnecté voit alors « Votre session a été fermée par un administrateur ».

Trois points d'entrée :
  - DG       : POST /boutique/equipe/{user_id}/fermer-sessions (membre de SA boutique) ;
  - chacun   : POST /auth/sessions/fermer-autres (ses autres appareils ; celui-ci reste connecté) ;
  - super-admin : POST /plateforme/boutiques/{id}/comptes/{user_id}/fermer-sessions
                  et POST /plateforme/boutiques/{id}/fermer-sessions (toute la boutique).
Chaque action est notée dans le journal des identifiants (qui, cible, quand, IP).
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pymongo import ReturnDocument

import identifiants
from auth import (Contexte, create_access_token, get_current_user, get_super_admin, permission,
                  poser_cookie_session, user_public)
from db import SANS_ID, db

boutique = APIRouter(prefix="/boutique", tags=["Ma boutique"])
compte = APIRouter(prefix="/auth", tags=["Authentification"])
admin = APIRouter(prefix="/plateforme", tags=["Plateforme (super-admin)"])

parametres = permission("parametres")  # gestion de l'équipe : réservée au DG


def _fermeture_par_admin() -> dict:
    """Opération Mongo : nouvelle version de session + heure de fermeture par un responsable."""
    return {"$inc": {"version_session": 1}, "$set": {"sessions_fermees_par_admin_le": time.time()}}


# ---------------------------------------------------------------------------
# DG : fermer les sessions d'un membre de SA boutique
# ---------------------------------------------------------------------------
@boutique.post("/equipe/{user_id}/fermer-sessions")
async def fermer_sessions_membre(user_id: str, request: Request, ctx: Contexte = Depends(parametres)):
    if user_id == ctx.user["id"]:
        raise HTTPException(400, "Pour vos propres sessions, utilisez « Déconnecter mes autres appareils » dans Mon compte")
    # Filtre boutique_id : un DG ne peut viser QUE les comptes de sa boutique
    membre = await db.users.find_one({"id": user_id, "boutique_id": ctx.boutique["id"]}, SANS_ID)
    if not membre:
        raise HTTPException(404, "Membre introuvable")
    await db.users.update_one({"id": user_id, "boutique_id": ctx.boutique["id"]}, _fermeture_par_admin())
    await identifiants.journaliser("SESSIONS_FERMEES", cible=membre, par=ctx.user, request=request)
    return {"ok": True, "message": f"Les sessions de {membre.get('nom', 'ce membre')} sont fermées sur tous ses appareils."}


# ---------------------------------------------------------------------------
# Tout utilisateur : déconnecter ses AUTRES appareils (celui-ci reste connecté)
# ---------------------------------------------------------------------------
@compte.post("/sessions/fermer-autres")
async def fermer_autres_sessions(request: Request, response: Response, user: dict = Depends(get_current_user)):
    maj = await db.users.find_one_and_update({"id": user["id"]}, {"$inc": {"version_session": 1}},
                                             projection=SANS_ID, return_document=ReturnDocument.AFTER)
    # Nouveau jeton à la nouvelle version : cet appareil garde une session valide
    jeton = create_access_token(user["id"], int(maj.get("version_session", 0)))
    poser_cookie_session(response, jeton)
    await identifiants.journaliser("SESSIONS_AUTRES_FERMEES", cible=user, par=user, request=request)
    return {"ok": True, "access_token": jeton,
            "message": "Vos autres appareils sont déconnectés. Cet appareil reste connecté."}


# ---------------------------------------------------------------------------
# Super-administrateur : comptes d'une boutique, un compte, ou toute la boutique
# ---------------------------------------------------------------------------
async def _boutique(boutique_id: str) -> dict:
    b = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    return b


@admin.get("/boutiques/{boutique_id}/comptes")
async def comptes_boutique(boutique_id: str, _: dict = Depends(get_super_admin)):
    """Comptes du personnel de la boutique (pour fermer leurs sessions)."""
    await _boutique(boutique_id)
    comptes = await db.users.find({"boutique_id": boutique_id}, SANS_ID).sort("nom", 1).to_list(500)
    return [user_public(c) for c in comptes]


@admin.post("/boutiques/{boutique_id}/comptes/{user_id}/fermer-sessions")
async def fermer_sessions_compte(boutique_id: str, user_id: str, request: Request,
                                 administrateur: dict = Depends(get_super_admin)):
    if user_id == administrateur["id"]:
        raise HTTPException(400, "Vous ne pouvez pas fermer vos propres sessions ici")
    b = await _boutique(boutique_id)
    membre = await db.users.find_one({"id": user_id, "boutique_id": b["id"]}, SANS_ID)
    if not membre or membre.get("role") == "super_admin":
        raise HTTPException(404, "Compte introuvable dans cette boutique")
    await db.users.update_one({"id": user_id, "boutique_id": b["id"]}, _fermeture_par_admin())
    await identifiants.journaliser("SESSIONS_FERMEES", cible=membre, par=administrateur, request=request)
    return {"ok": True, "message": f"Les sessions de {membre.get('nom', 'ce compte')} sont fermées sur tous ses appareils."}


@admin.post("/boutiques/{boutique_id}/fermer-sessions")
async def fermer_sessions_boutique(boutique_id: str, request: Request, administrateur: dict = Depends(get_super_admin)):
    b = await _boutique(boutique_id)
    # Jamais le super-administrateur lui-même (il n'appartient à aucune boutique, mais on l'exclut quand même)
    filtre = {"boutique_id": b["id"], "role": {"$ne": "super_admin"}, "id": {"$ne": administrateur["id"]}}
    res = await db.users.update_many(filtre, _fermeture_par_admin())
    await identifiants.journaliser("SESSIONS_BOUTIQUE_FERMEES", boutique_id=b["id"], par=administrateur, request=request,
                                   details={"nb_comptes": res.modified_count, "boutique": b.get("nom", "")})
    return {"ok": True, "nb_comptes": res.modified_count,
            "message": f"Sessions fermées pour {res.modified_count} compte(s) de « {b.get('nom', '')} »."}
