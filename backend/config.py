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
    jwt_expires_minutes: int = 60 * 24 * 30  # 30 jours (session gardée par le navigateur)
    # Cookie de session : HttpOnly (illisible par le JavaScript du site), jamais le
    # mot de passe. "auto" : Secure + SameSite=None si le site est en https
    # (site et API sur deux domaines Render différents), sinon SameSite=Lax (dev).
    session_cookie_nom: str = "adlyn_session"
    session_cookie_securise: str = "auto"  # auto | true | false

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
    pawapay_customer_message: str = "adLyn"

    # --- Parrainage entre boutiques ---
    # Bonus (FCFA) gagné par le parrain pour chaque boutique filleule ouverte
    # (validée par l'administrateur) ; déductible de son abonnement.
    parrainage_bonus_fcfa: int = 500
    # Garde-fous de la page publique d'ouverture : demandes par adresse IP (par heure)
    # et par parrain (par jour)
    parrainage_max_demandes_ip_heure: int = 5
    parrainage_max_demandes_parrain_jour: int = 10

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

    # --- Sauvegardes chiffrées des boutiques (chaque nuit, vers Google Drive) ---
    # Clé AES-256 en base64 (32 octets) : SANS ELLE AUCUNE RESTAURATION N'EST
    # POSSIBLE. La conserver aussi en lieu sûr hors de Render (coffre-fort).
    sauvegarde_cle: Optional[str] = None
    sauvegarde_heure: int = 0  # 00h, heure locale (fuseau_horaire)
    sauvegarde_retention_jours: int = 30  # sauvegardes plus anciennes supprimées du Drive
    # Google Drive du propriétaire de la plateforme : identifiants OAuth
    # (voir outils/obtenir_jeton_gdrive.py pour obtenir le jeton de rafraîchissement)
    gdrive_client_id: Optional[str] = None
    gdrive_client_secret: Optional[str] = None
    gdrive_refresh_token: Optional[str] = None
    gdrive_nom_dossier: str = "adLyn - Sauvegardes"

    # --- Rapport nocturne (sauvegardes + catalogue) envoyé au super-admin ---
    rapport_email: Optional[str] = None
    # Serveur d'envoi de la PLATEFORME (distinct de celui de chaque boutique)
    plateforme_smtp_hote: Optional[str] = None
    plateforme_smtp_port: int = 587
    plateforme_smtp_utilisateur: Optional[str] = None
    plateforme_smtp_mot_de_passe: Optional[str] = None
    plateforme_smtp_ssl: bool = False
    plateforme_expediteur: Optional[str] = None

    # --- SMS (identifiants envoyés au DG d'une boutique créée par le webhook) ---
    # Orange SMS API (Burkina Faso et Afrique de l'Ouest), OVH en repli : mêmes
    # comptes et mêmes variables que beauthentik.net
    orange_sms_client_id: Optional[str] = None
    orange_sms_client_secret: Optional[str] = None
    orange_sms_sender_msisdn: Optional[str] = None  # numéro émetteur enregistré chez Orange, ex. +22600000000
    orange_sms_sender_name: Optional[str] = None  # nom d'émetteur (si activé par Orange)
    ovh_sms_endpoint: str = "ovh-eu"  # ovh-eu | ovh-ca
    ovh_sms_application_key: Optional[str] = None
    ovh_sms_application_secret: Optional[str] = None
    ovh_sms_consumer_key: Optional[str] = None
    ovh_sms_service_name: Optional[str] = None  # ex. sms-ab12345-1
    ovh_sms_sender: Optional[str] = None  # expéditeur déclaré chez OVH, ex. adLyn

    # --- WhatsApp Cloud API (Meta) : même compte que beauthentik.net ---
    whatsapp_access_token: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    # Modèle (template) « Utility » approuvé par Meta pour les rappels d'abonnement,
    # 3 variables : {{1}} nom de la boutique, {{2}} échéance, {{3}} montant
    whatsapp_rappel_template: Optional[str] = None
    whatsapp_template_langue: str = "fr"
    # Carrousel de produits (modèle « Marketing » à cartes, approuvé par Meta).
    # Nom de BASE : le modèle réellement utilisé est « <base>_<n> » où n = nombre
    # de cartes (2 à 10), car Meta impose un nombre de cartes fixe par modèle.
    # Ex. base « adlyn_carrousel » -> modèles adlyn_carrousel_3, adlyn_carrousel_5...
    # Structure attendue de chaque modèle :
    #   corps du message : {{1}} nom de la boutique, {{2}} message d'introduction
    #   chaque carte : en-tête IMAGE, corps {{1}} nom du produit, {{2}} prix,
    #   bouton URL « Voir le produit » = https://adlynservice.com/b/{{1}}
    whatsapp_carrousel_template: Optional[str] = None

    # --- Abonnements des boutiques ---
    abonnement_essai_jours: int = 14  # démo complète offerte à chaque nouvelle boutique
    abonnement_rappel_jours_avant: int = 3  # premier rappel N jours avant l'échéance, puis chaque jour
    abonnement_rappel_retard_max_jours: int = 60  # plus de rappel au-delà de ce retard
    abonnement_rappel_heure: int = 9  # heure locale d'envoi des rappels

    # --- Service SMS des boutiques (OVH, facturé à part) ---
    sms_prix_defaut: int = 25  # FCFA par SMS, modifiable boutique par boutique
    sms_facture_delai_jours: int = 10  # délai de paiement d'une facture SMS

    # --- Webhook de création automatique des boutiques (signé HMAC-SHA256) ---
    # Secret partagé avec le système appelant ; sans lui le webhook est fermé (503).
    webhook_boutiques_secret: Optional[str] = None
    webhook_fenetre_secondes: int = 300  # horodatage accepté à ± 5 minutes
    webhook_quota_jour: int = 20  # boutiques créées au maximum par jour via le webhook
    webhook_max_echecs_ip: int = 10  # appels refusés tolérés par adresse IP et par heure

    # Développement : crée la boutique de démonstration au démarrage
    # (pratique avec MONGO_URL=mongomock://, dont les données sont perdues à l'arrêt)
    demo_au_demarrage: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
