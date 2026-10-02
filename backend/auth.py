"""Authentification du personnel et résolution de la boutique (tenant).

Rôles :
  - super_admin : administrateur de la PLATEFORME (vous) ; crée les boutiques.
  - dg          : Directeur Général d'une boutique : tous les droits, dont
                  paramètres, équipe et dossier KYC.
  - commercial  : catalogue, clients, proformas/factures, commandes, conseils.
  - secretaire  : accueil des clients, dépôts SAV, commandes, messagerie.
  - comptable   : factures et règlements, historique des paiements, stock,
                  fournisseurs.
  - technicien  : réparations (SAV), pièces détachées, consultation du catalogue.
Les droits de chaque rôle sont regroupés dans la table PERMISSIONS ci-dessous
(une seule table à modifier pour les changer), renvoyée au navigateur à la
connexion pour afficher uniquement les menus autorisés.

RÈGLE MULTI-TENANT : la boutique d'un membre du personnel est lue dans SA
fiche en base (résolue côté serveur depuis le jeton), jamais depuis un
paramètre envoyé par le navigateur. Seul le super-administrateur peut
choisir la boutique sur laquelle il agit (en-tête X-Boutique-Id).
"""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

import inactivite
import maintenance_plateforme
import sessions_actives
from config import get_settings
from db import SANS_ID, TenantDB, db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

ROLES_BOUTIQUE = ("dg", "commercial", "secretaire", "comptable", "technicien")
TOUS = ROLES_BOUTIQUE

# Qui peut faire quoi (le super-administrateur a toujours tous les droits)
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "tableau_de_bord": TOUS,
    "catalogue.lecture": TOUS,
    "catalogue.edition": ("dg", "commercial"),
    "clients": TOUS,
    "facturation": ("dg", "commercial", "comptable"),
    "commandes": ("dg", "commercial", "secretaire"),
    "maintenance": ("dg", "technicien", "secretaire", "commercial"),
    "stock": ("dg", "comptable", "commercial"),
    "fournisseurs": ("dg", "comptable", "commercial"),
    "messagerie": ("dg", "commercial", "secretaire"),
    "paiements.historique": ("dg", "comptable"),
    "parametres": ("dg",),
    # Situation de la caisse Aizenta (reçue de Loois) : direction, comptabilité et
    # secrétariat (accueil / caisse). Les commerciaux et techniciens ne la voient pas.
    "caisse_aizenta": ("dg", "comptable", "secretaire"),
}


def permissions_de(role: str) -> list[str]:
    """Liste des permissions d'un rôle (toutes pour le super-administrateur)."""
    return [p for p, roles in PERMISSIONS.items() if role == "super_admin" or role in roles]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: str, version: int = 0) -> str:
    """Jeton de session signé. `v` = version de session de l'utilisateur :
    l'augmenter (changement de mot de passe, déconnexion partout) invalide
    tous les jetons déjà distribués."""
    s = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_expires_minutes)
    # « ouv » = heure d'ouverture de la session (invalidation après une maintenance) ;
    # « sid » = identifiant de la session (suivi de l'inactivité, voir inactivite.py)
    return jwt.encode({"sub": user_id, "v": version, "exp": expires_at, "ouv": time.time(),
                       "sid": secrets.token_urlsafe(12)},
                      s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------------------------
# Cookie de session (HttpOnly) : le navigateur le renvoie tout seul, le site
# se reconnecte donc dès son ouverture. Le MOT DE PASSE N'EST JAMAIS STOCKÉ :
# le cookie ne contient que le jeton signé, illisible par le JavaScript.
# ---------------------------------------------------------------------------
# En-tête exigé sur les requêtes d'écriture authentifiées par cookie : un site
# tiers ne peut pas l'ajouter sans l'accord CORS du serveur (protection CSRF).
ENTETE_CSRF = "x-adlyn"
# Message affiché quand le DG ou l'administrateur a fermé les sessions du compte
MESSAGE_SESSION_FERMEE = "Votre session a été fermée par un administrateur. Reconnectez-vous."


def _cookie_securise() -> bool:
    s = get_settings()
    choix = (s.session_cookie_securise or "auto").lower()
    if choix in ("true", "false"):
        return choix == "true"
    return s.public_site_url.startswith("https://")


def poser_cookie_session(response: Response, jeton: str) -> None:
    s = get_settings()
    securise = _cookie_securise()
    response.set_cookie(
        s.session_cookie_nom, jeton, max_age=s.jwt_expires_minutes * 60, httponly=True, secure=securise,
        # Site et API sur deux domaines différents en production : SameSite=None (+ Secure obligatoire)
        samesite="none" if securise else "lax", path="/")


def effacer_cookie_session(response: Response) -> None:
    s = get_settings()
    securise = _cookie_securise()
    response.delete_cookie(s.session_cookie_nom, path="/", secure=securise, httponly=True,
                           samesite="none" if securise else "lax")


def user_public(user: dict) -> dict:
    """Fiche utilisateur renvoyée au navigateur (jamais le hachage du mot de passe),
    avec la liste de ses permissions."""
    public = {k: v for k, v in user.items() if k not in ("password_hash", "_id", "version_session",
                                                     "sessions_fermees_par_admin_le")}
    public["permissions"] = permissions_de(user.get("role", ""))
    return public


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """Utilisateur connecté : jeton « Bearer » (outils, tests) ou cookie de session (site)."""
    if credentials is not None:
        jeton = credentials.credentials
    else:
        jeton = request.cookies.get(get_settings().session_cookie_nom)
        if not jeton:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non authentifié")
        # Protection CSRF : toute écriture via cookie doit porter l'en-tête du site
        if request.method not in ("GET", "HEAD", "OPTIONS") and not request.headers.get(ENTETE_CSRF):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Requête refusée (en-tête de sécurité manquant)")
    contenu = decode_access_token(jeton)
    if not contenu or not contenu.get("sub"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalide ou expirée")
    user = await db.users.find_one({"id": contenu["sub"]}, SANS_ID)
    if not user or not user.get("actif", True):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable ou désactivé")
    if int(contenu.get("v", 0)) != int(user.get("version_session", 0)):
        # Session ouverte AVANT une fermeture par le DG ou l'administrateur (routes/sessions.py)
        if float(contenu.get("ouv", 0)) < float(user.get("sessions_fermees_par_admin_le") or 0):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, MESSAGE_SESSION_FERMEE)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée : reconnectez-vous")
    # Maintenance de la plateforme : 503 pendant la maintenance, 401 pour les sessions d'avant
    await maintenance_plateforme.controler_session(user, contenu)
    # Session fermée (nombre maximal d'appareils, fermée depuis Mon compte ou par l'administrateur)
    await sessions_actives.controler(user, contenu, request)
    # Déconnexion après inactivité (durée réglée par l'administrateur et le DG)
    await inactivite.controler(user, contenu, request)
    return user


async def utilisateur_optionnel(request: Request) -> Optional[dict]:
    """Utilisateur connecté s'il y en a un (jeton Bearer ou cookie de session),
    None sinon — pour les pages PUBLIQUES qui s'adaptent au visiteur (lecture seule :
    aucune vérification CSRF nécessaire)."""
    entete = request.headers.get("authorization", "")
    jeton = entete[7:] if entete.lower().startswith("bearer ") else request.cookies.get(get_settings().session_cookie_nom)
    contenu = decode_access_token(jeton) if jeton else None
    if not contenu or not contenu.get("sub"):
        return None
    user = await db.users.find_one({"id": contenu["sub"]}, SANS_ID)
    if not user or not user.get("actif", True) or int(contenu.get("v", 0)) != int(user.get("version_session", 0)):
        return None
    if not await maintenance_plateforme.session_admise(user, contenu):
        return None  # maintenance : simple visiteur
    return user


async def get_super_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'administrateur de la plateforme")
    return user


class Contexte:
    """Ce dont une route métier a besoin : l'utilisateur, SA boutique et
    l'accès cloisonné aux données de cette boutique (tdb)."""

    def __init__(self, user: dict, boutique: dict):
        self.user = user
        self.boutique = boutique
        self.tdb = TenantDB(boutique["id"])

    @property
    def role(self) -> str:
        return self.user.get("role", "")

    def peut(self, permission: str) -> bool:
        return self.role == "super_admin" or self.role in PERMISSIONS.get(permission, ())

    @property
    def auteur(self) -> dict:
        """Signature enregistrée sur les opérations (mouvements, documents...)."""
        return {"user_id": self.user["id"], "user_nom": self.user.get("nom", "")}


async def _resoudre_contexte(user: dict, x_boutique_id: Optional[str], meme_suspendue: bool,
                             request: Optional[Request] = None) -> Contexte:
    if user.get("role") == "super_admin":
        # Le super-administrateur choisit explicitement la boutique à consulter
        if not x_boutique_id:
            raise HTTPException(400, "Choisissez une boutique (en-tête X-Boutique-Id)")
        boutique_id = x_boutique_id
    else:
        boutique_id = user.get("boutique_id")
    if user.get("doit_changer_mot_de_passe"):
        # Mot de passe provisoire (reçu par e-mail/SMS) : à changer avant tout travail
        raise HTTPException(403, "Changez votre mot de passe provisoire avant de continuer")
    boutique = await db.boutiques.find_one({"id": boutique_id}, SANS_ID) if boutique_id else None
    if not boutique:
        raise HTTPException(403, "Aucune boutique associée à ce compte")
    # Suspendue (J+110) ou archivée (J+113) par le cycle de vie : aucun accès, même à la
    # page Abonnement, sauf pour le super-administrateur (cycle_vie.py)
    import cycle_vie
    cycle_vie.controler(boutique, user)
    if not boutique.get("actif", True) and user.get("role") != "super_admin" and not meme_suspendue:
        if (boutique.get("suspension") or {}).get("motif") == "IMPAYE":
            raise HTTPException(403, "Accès suspendu : abonnement adLyn non renouvelé. Le DG peut le régler depuis la page Abonnement.")
        raise HTTPException(403, "Cette boutique est suspendue. Contactez l'administrateur de la plateforme.")
    if not meme_suspendue:
        # Abonnement expiré et période de grâce terminée : coupure automatique (abonnement_grace.py)
        import abonnement_grace
        abonnement_grace.controler(boutique, user)
    if request is not None and user.get("role") != "super_admin":
        # Règles d'accès de la boutique (IP / appareils), vérifiées à CHAQUE requête :
        # une interdiction ajoutée par le DG coupe aussi les sessions déjà ouvertes
        import acces
        autorise, raison = acces.controler(boutique, request)
        if not autorise:
            raise HTTPException(403, f"Accès refusé : {raison.lower()}")
    if request is not None:
        # Options de la barre latérale activées par l'administrateur pour cette boutique :
        # une route d'une option désactivée répond 403 (voir options_sidebar.py).
        # S'applique aussi au super-admin qui consulte la boutique (il voit ce qu'elle voit).
        import options_sidebar
        route = request.scope.get("route")
        chemin = getattr(route, "path", None) or request.url.path
        options_sidebar.verifier_requete(boutique, request.method, chemin)
    return Contexte(user, boutique)


async def get_contexte(
    request: Request,
    user: dict = Depends(get_current_user),
    x_boutique_id: Optional[str] = Header(default=None),
) -> Contexte:
    return await _resoudre_contexte(user, x_boutique_id, meme_suspendue=False, request=request)


async def contexte_abonnement(
    request: Request,
    user: dict = Depends(get_current_user),
    x_boutique_id: Optional[str] = Header(default=None),
) -> Contexte:
    """Page « Abonnement » : réservée au DG, et accessible MÊME si la boutique est
    suspendue (c'est là qu'il règle son abonnement pour retrouver l'accès)."""
    ctx = await _resoudre_contexte(user, x_boutique_id, meme_suspendue=True, request=request)
    if ctx.role not in ("dg", "super_admin"):
        raise HTTPException(403, "Réservé au DG de la boutique")
    return ctx


def permission(nom: str):
    """Dépendance : limite une route aux rôles qui ont cette permission."""
    if nom not in PERMISSIONS:
        raise ValueError(f"Permission inconnue : {nom}")

    async def _verif(ctx: Contexte = Depends(get_contexte)) -> Contexte:
        if not ctx.peut(nom):
            raise HTTPException(403, "Action non autorisée pour votre rôle")
        return ctx

    return _verif


# Raccourci : tout membre du personnel de la boutique
tout_le_personnel = permission("tableau_de_bord")
