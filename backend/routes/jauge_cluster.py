"""Lot 54 — GET /api/plateforme/atlas/jauge : occupation du cluster de production (super-admin uniquement).
Règles de calcul : jauge_cluster.py. Jamais d'adresse ni d'identifiant de connexion dans la réponse."""
from __future__ import annotations

from fastapi import APIRouter, Depends

import jauge_cluster
from auth import get_super_admin
from config import get_settings
from db import _client  # client Motor partagé (permet de lister toutes les bases du cluster)

router = APIRouter(prefix="/plateforme/atlas", tags=["Jauge du cluster (super-admin)"])


@router.get("/jauge")
async def jauge(forcer: bool = False, _: dict = Depends(get_super_admin)):
    """Taille occupée (Mo) et nombre de collections du cluster, avec couleur et pourcentage ;
    « forcer » ignore la mesure gardée en mémoire (10 min)."""
    return await jauge_cluster.mesurer(_client, get_settings().mongo_db_name, forcer)
