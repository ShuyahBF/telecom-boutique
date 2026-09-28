"""Configuration centralisée, lue depuis les variables d'environnement (.env).

Même organisation que beauthentik.net (ShuyahBF/site-meetafrican) : toutes
les collections MongoDB du projet sont préfixées (`tlb_` par défaut, voir
db.py) pour cohabiter sans risque dans un cluster Atlas partagé.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- MongoDB Atlas ---
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db_name: str = "telecom_boutique"
    mongo_collection_prefix: str = "tlb_"

    # --- Authentification du personnel (jeton JWT) ---
    jwt_secret: str = "change-me-in-.env"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24 * 7  # 7 jours

    # --- CORS : adresse(s) du site public, séparées par des virgules.
    # La PREMIÈRE sert d'URL publique (liens de suivi envoyés par e-mail,
    # retour après paiement, QR codes des boutiques).
    frontend_origin: str = "http://localhost:5173"

    @property
    def frontend_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]

    @property
    def public_site_url(self) -> str:
        origins = self.frontend_origins
        return origins[0].rstrip("/") if origins else "http://localhost:5173"

    # --- PawaPay (Mobile Money) — même compte et même mécanique que beauthentik ---
    pawapay_environment: str = "sandbox"  # sandbox | production
    pawapay_api_token_sandbox: Optional[str] = None
    pawapay_api_token_production: Optional[str] = None
    pawapay_callback_secret: Optional[str] = None
    pawapay_default_country: str = "BFA"
    # Libellé du SMS / de l'historique Mobile Money (4 à 22 caractères)
    pawapay_customer_message: str = "TelecomBoutique"

    # --- Stockage des fichiers (photos produits, logos des boutiques) ---
    # "local" : disque du serveur, dev/test uniquement (perdu à chaque
    # redéploiement Render). "r2" : Cloudflare R2, obligatoire en production.
    storage_backend: str = "local"  # local | r2
    max_upload_bytes: int = 5 * 1024 * 1024  # 5 Mo par image
    uploads_dir: str = "./uploads"
    public_base_url: str = "http://localhost:8000"
    r2_account_id: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret_access_key: Optional[str] = None
    r2_bucket_public: str = "telecom-boutique-medias"  # bucket PUBLIC (images)
    r2_public_base_url: Optional[str] = None  # domaine public du bucket (ou URL r2.dev)
    # Bucket PRIVÉ : pièces d'identité et documents KYC des boutiques. Jamais
    # d'adresse publique : lien temporaire (quelques minutes) généré à la demande.
    r2_bucket_prive: str = "telecom-boutique-kyc"
    r2_lien_prive_duree_secondes: int = 300

    # --- Premier compte super-administrateur de la plateforme ---
    # Créé (ou promu) au démarrage s'il est renseigné.
    super_admin_email: Optional[str] = None
    super_admin_password: Optional[str] = None
    # "true" le temps d'UN redéploiement pour réinitialiser le mot de passe oublié
    super_admin_reset_password: bool = False

    # --- Catalogue public commun ---
    # Heure de publication quotidienne des modifications (fuseau ci-dessous)
    catalogue_heure_publication: int = 23
    fuseau_horaire: str = "Africa/Ouagadougou"
    # Assistant de recherche des fiches techniques (API Claude + recherche web)
    anthropic_api_key: Optional[str] = None
    catalogue_ia_modele: str = "claude-opus-5"

    # Développement : crée la boutique de démonstration au démarrage
    # (pratique avec MONGO_URL=mongomock://, dont les données sont perdues à l'arrêt)
    demo_au_demarrage: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
