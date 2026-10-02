"""Réglages de la déconnexion après inactivité (voir inactivite.py).

  - chacun        : GET /auth/inactivite (durée qui s'applique à lui), POST /auth/activite
                    (le site signale une activité : souris, clavier… au plus une fois par minute) ;
  - super-admin   : GET/PUT /plateforme/parametres/inactivite (valeur de la plateforme),
                    GET/PUT /plateforme/boutiques/{id}/inactivite (valeur propre à une boutique) ;
  - DG            : GET/PUT /boutique/inactivite (réduire la durée pour sa boutique).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import inactivite as service
from auth import Contexte, get_current_user, get_super_admin, permission
from db import SANS_ID, db

compte = APIRouter(prefix="/auth", tags=["Authentification"])
admin = APIRouter(prefix="/plateforme", tags=["Plateforme (super-admin)"])
boutique = APIRouter(prefix="/boutique", tags=["Ma boutique"])


class Duree(BaseModel):
    secondes: Optional[int] = None  # None = reprendre la valeur fixée au-dessus


# ---------------------------------------------------------------------------
# Tout utilisateur connecté
# ---------------------------------------------------------------------------
@compte.get("/inactivite")
async def ma_duree(user: dict = Depends(get_current_user)):
    secondes = await service.delai_utilisateur(user)
    return {"secondes": secondes, "avertissement_secondes": service.avertissement(secondes) if secondes else 0}


@compte.post("/activite")
async def signaler_activite(_: dict = Depends(get_current_user)):
    """Rien à faire ici : la requête elle-même est notée comme activité (auth.get_current_user)."""
    return {"ok": True}


# ---------------------------------------------------------------------------
# Super-administrateur
# ---------------------------------------------------------------------------
@admin.get("/parametres/inactivite")
async def lire_plateforme(_: dict = Depends(get_super_admin)):
    return {"secondes": await service.delai_plateforme(cache=False), "min": service.MIN_SECONDES,
            "max": service.MAX_SECONDES}


@admin.put("/parametres/inactivite")
async def regler_plateforme(payload: Duree, adm: dict = Depends(get_super_admin)):
    secondes = await service.regler_plateforme(payload.secondes, adm.get("email", ""))
    return {"secondes": secondes, "min": service.MIN_SECONDES, "max": service.MAX_SECONDES}


async def _boutique(boutique_id: str) -> dict:
    b = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    return b


@admin.get("/boutiques/{boutique_id}/inactivite")
async def lire_boutique(boutique_id: str, _: dict = Depends(get_super_admin)):
    return service.resume(await _boutique(boutique_id), await service.delai_plateforme(cache=False))


@admin.put("/boutiques/{boutique_id}/inactivite")
async def regler_boutique(boutique_id: str, payload: Duree, _: dict = Depends(get_super_admin)):
    """Durée propre à la boutique (None = valeur de la plateforme). Un réglage du DG
    plus long que le nouveau plafond n'a plus d'effet (le plus court l'emporte)."""
    b = await _boutique(boutique_id)
    secondes = service.valider(payload.secondes, nul_permis=True)
    await db.boutiques.update_one({"id": b["id"]}, {"$set": {"inactivite_secondes": secondes}})
    service.vider_cache()
    return service.resume({**b, "inactivite_secondes": secondes}, await service.delai_plateforme(cache=False))


# ---------------------------------------------------------------------------
# DG : ne peut que réduire la durée fixée par l'administrateur
# ---------------------------------------------------------------------------
@boutique.get("/inactivite")
async def lire_dg(ctx: Contexte = Depends(permission("parametres"))):
    return service.resume(ctx.boutique, await service.delai_plateforme(cache=False))


@boutique.put("/inactivite")
async def regler_dg(payload: Duree, ctx: Contexte = Depends(permission("parametres"))):
    plafond = service.plafond_boutique(ctx.boutique, await service.delai_plateforme(cache=False))
    secondes = service.valider(payload.secondes, nul_permis=True)
    if secondes == 0:
        secondes = None  # « désactivée » côté DG = reprendre la durée de l'administrateur
        if plafond:
            raise HTTPException(400, "Vous ne pouvez pas désactiver la déconnexion fixée par l'administrateur adLyn")
    if secondes is not None and plafond and secondes > plafond:
        raise HTTPException(400, f"Vous pouvez seulement réduire la durée : {plafond} secondes au maximum")
    await db.boutiques.update_one({"id": ctx.boutique["id"]}, {"$set": {"inactivite_secondes_dg": secondes}})
    service.vider_cache()
    return service.resume({**ctx.boutique, "inactivite_secondes_dg": secondes},
                          await service.delai_plateforme(cache=False))
