"""Point d'entrée FastAPI — adLyn (plateforme SaaS multi-boutiques).

Lancement local : uvicorn server:app --reload
Documentation interactive de l'API : http://localhost:8000/docs
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import abonnements as service_abonnements
import catalogue_public as service_catalogue
import taches_nocturnes
from config import get_settings
from db import ensure_indexes
from routes import (abonnements, auth, boutique, catalogue, catalogue_public, commandes, conversations, documents, journal,
                    maintenance, paiements, plateforme, public, referentiel, reversements, sauvegardes, sms, stock,
                    tableau_de_bord, tiers, webhooks)
from seed import creer_demo, ensure_super_admin

settings = get_settings()

app = FastAPI(title="adLyn API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Nom des fichiers téléchargés (sauvegardes, exports) lisible par le site
    expose_headers=["Content-Disposition"],
)

api = APIRouter(prefix="/api")
for module in (auth, plateforme, boutique, catalogue, tiers, stock, documents, commandes, maintenance,
               conversations, tableau_de_bord, public, paiements, journal, sauvegardes):
    api.include_router(module.router)
# Abonnements : page du DG et administration (super-admin)
api.include_router(abonnements.boutique)
api.include_router(abonnements.admin)
# Reversements aux boutiques de l'argent encaissé par PawaPay
api.include_router(reversements.boutique)
api.include_router(reversements.admin)
# Service SMS des boutiques (envois, journal, facturation)
api.include_router(sms.boutique)
api.include_router(sms.admin)
# Webhook de création des boutiques (signé HMAC) et son journal
api.include_router(webhooks.router)
api.include_router(webhooks.admin)
# Référentiel mondial des appareils (déclaré AVANT le catalogue public)
api.include_router(referentiel.admin)
api.include_router(referentiel.consultation)
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
    # Formules d'abonnement par défaut + essai de 14 jours des boutiques plus anciennes
    await service_abonnements.initialiser()
    # Rapprochement automatique des paiements PawaPay en attente (compte partagé :
    # le callback PawaPay ne pointe pas vers ce site)
    asyncio.create_task(paiements.boucle_rapprochement())
    # Publication du catalogue public chaque soir (23h par défaut)
    asyncio.create_task(service_catalogue.boucle_publication())
    # Sauvegardes chiffrées vers Google Drive + rapport par e-mail, chaque nuit à 00h
    asyncio.create_task(taches_nocturnes.boucle_nocturne())
    # Rappels d'abonnement (WhatsApp / SMS / e-mail) chaque jour à 9h
    asyncio.create_task(service_abonnements.boucle_rappels())
