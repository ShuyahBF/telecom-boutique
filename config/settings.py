"""
Paramètres Django de la plateforme TelecomPro.

Toutes les valeurs sensibles (clé secrète, mode debug, base de données)
se règlent par VARIABLES D'ENVIRONNEMENT, jamais en dur dans le code.
En local, sans aucune variable, le projet démarre en mode développement
avec une base SQLite (fichier db.sqlite3) : aucune installation de
serveur de base de données n'est nécessaire.
"""

import os
from pathlib import Path

# Dossier racine du projet (celui qui contient manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(nom: str, defaut: bool = False) -> bool:
    """Lit une variable d'environnement booléenne ("1", "true", "oui"...)."""
    valeur = os.environ.get(nom)
    if valeur is None:
        return defaut
    return valeur.strip().lower() in {"1", "true", "yes", "oui", "on"}


# --- Sécurité -----------------------------------------------------------
# Clé secrète : OBLIGATOIRE en production (variable DJANGO_SECRET_KEY).
# La valeur par défaut ne sert qu'au développement local.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "dev-uniquement-ne-pas-utiliser-en-production"
)

# Mode debug : activé par défaut en local, à désactiver en production
# (DJANGO_DEBUG=0).
DEBUG = _env_bool("DJANGO_DEBUG", True)

# Noms de domaine autorisés, séparés par des virgules (ex: "monsite.com,www.monsite.com")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# --- Applications -------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Applications métier de la plateforme (une application = un module)
    "core",         # paramètres entreprise, compteurs de numérotation, tableau de bord
    "tiers",        # clients et fournisseurs
    "catalogue",    # téléphones, accessoires, catégories, marques
    "stock",        # mouvements d'entrées / sorties de stock
    "ventes",       # factures, proformas, commandes en ligne
    "maintenance",  # dossiers de réparation des appareils déposés
    "messagerie",   # centre de messagerie + paramétrage e-mail par l'admin
    "portail",      # site public (vitrine, panier, suivi, conseils)
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Dossier global de gabarits HTML (templates/ à la racine du projet)
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Rend "entreprise" et "panier_nb" disponibles dans toutes les pages
                "core.context_processors.entreprise",
                "portail.context_processors.panier",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de données ----------------------------------------------------
# Par défaut : SQLite (un simple fichier, idéal pour démarrer).
# Pour la production, définir DATABASE_ENGINE / DATABASE_NAME / ... pour
# PostgreSQL ou MySQL (voir README.md, section "Base de données").
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DATABASE_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("DATABASE_NAME", str(BASE_DIR / "db.sqlite3")),
        "USER": os.environ.get("DATABASE_USER", ""),
        "PASSWORD": os.environ.get("DATABASE_PASSWORD", ""),
        "HOST": os.environ.get("DATABASE_HOST", ""),
        "PORT": os.environ.get("DATABASE_PORT", ""),
    }
}

# --- Mots de passe ------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "admin:login"

# --- Langue / fuseau horaire -------------------------------------------
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Africa/Ouagadougou")
USE_I18N = True
USE_TZ = True
# Séparateur de milliers (ex: 125 000) pour les montants affichés
USE_THOUSAND_SEPARATOR = True

# --- Fichiers statiques (CSS) et médias (photos produits, logo) --------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"  # rempli par "collectstatic" en production

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- E-mail -------------------------------------------------------------
# Valeur de repli uniquement : les vrais réglages SMTP sont saisis par
# l'administrateur dans l'écran "Messagerie > Paramètres de messagerie"
# (stockés en base, voir messagerie/services.py). Tant qu'ils ne sont pas
# renseignés, les e-mails sont simplement affichés dans la console.
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)

# --- Durcissement en production (DEBUG désactivé) -----------------------
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
