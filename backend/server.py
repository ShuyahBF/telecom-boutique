"""Point d'entrée FastAPI — TelecomBoutique (plateforme SaaS multi-boutiques).

Lancement local : uvicorn server:app --reload
Documentation interactive de l'API : http://localhost:8000/docs
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import catalogue_public as service_catalogue
from config import get_settings
from db import ensure_indexes
from routes import (auth, boutique, catalogue, catalogue_public, commandes, conversations, documents, maintenance, paiements,
                    plateforme, public, stock, tableau_de_bord, tiers)
from seed import creer_demo, ensure_super_admin

settings = get_settings()

app = FastAPI(title="TelecomBoutique API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
for module in (auth, plateforme, boutique, catalogue, tiers, stock, documents, commandes, maintenance,
               conversations, tableau_de_bord, public, paiements):
    api.include_router(module.router)
# Catalogue public commun : administration (super-admin) et consultation (boutiques)
api.include_router(catalogue_public.admin)
api.include_router(catalogue_public.consultation)


@api.get("/health")
async def health():
    return {"ok": True}


app.include_router(api)

if settings.storage_backend == "local":
    # Images servies par l'API elle-même : développement uniquement
    dossier = Path(settings.uploads_dir)
    dossier.mkdir(parents=True, exist_ok=True)
    app.mount("/api/files", StaticFiles(directory=str(dossier)), name="files")


@app.on_event("startup")
async def au_demarrage():
    await ensure_indexes()
    await ensure_super_admin()
    if settings.demo_au_demarrage:
        await creer_demo()
    # Rapprochement automatique des paiements PawaPay en attente (compte partagé :
    # le callback PawaPay ne pointe pas vers ce site)
    asyncio.create_task(paiements.boucle_rapprochement())
    # Publication du catalogue public chaque soir (23h par défaut)
    asyncio.create_task(service_catalogue.boucle_publication())
