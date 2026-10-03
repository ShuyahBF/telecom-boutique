"""Sessions simultanées limitées par compte (règle validée le 02/10/2026).

Réutilise l'infrastructure existante :
  - chaque jeton porte déjà un identifiant de session « sid » (auth.create_access_token)
    et la version de session du compte « v » ;
  - la collection « sessions_activite » (un document par sid, effacé automatiquement à
    l'expiration du jeton, voir db.ensure_indexes) sert aussi à la déconnexion après
    inactivité (inactivite.py). Ce module y ajoute ses propres champs : compte, version,
    ouverture, dernière activité (`activite_le`), adresse IP, appareil, fermeture et motif.

Règles :
  - au plus N sessions ouvertes par compte (N = 5 par défaut, réglé par le
    super-administrateur entre 1 et 20) ;
  - à la connexion qui dépasse N, la session dont la dernière activité est la plus
    ancienne est fermée ; l'appareil concerné reçoit « Session fermée : nombre maximal
    d'appareils atteint pour ce compte. » ;
  - chacun voit et ferme ses sessions dans « Mon compte » ; le super-administrateur voit
    le nombre de sessions de chaque compte d'une boutique et peut en fermer une ;
  - contrôle côté serveur à chaque requête (auth.get_current_user), avec un petit cache
    de quelques secondes ; chaque fermeture est journalisée (journal des identifiants).
Les sessions d'une ancienne version du compte (mot de passe changé, « Déconnecter mes
autres appareils »…) sont déjà invalides : elles ne comptent pas.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request, status

from db import db

LIMITE_DEFAUT, LIMITE_MIN, LIMITE_MAX = 5, 1, 20
ID_REGLAGE = "sessions_max"
DUREE_CACHE = 10  # secondes : état d'une session relu au plus toutes les 10 s
DUREE_CACHE_REGLAGE = 30
ECRITURE_ACTIVITE = 60  # dernière activité notée au plus une fois par minute
ENTETE_FOND = "x-adlyn-fond"  # rafraîchissements automatiques du site : pas une activité

MESSAGE_LIMITE = "Session fermée : nombre maximal d'appareils atteint pour ce compte."
MESSAGE_UTILISATEUR = "Session fermée depuis un autre appareil de ce compte. Reconnectez-vous."
MESSAGE_ADMIN = "Votre session a été fermée par un administrateur. Reconnectez-vous."
MESSAGES = {"LIMITE": MESSAGE_LIMITE, "UTILISATEUR": MESSAGE_UTILISATEUR, "ADMIN": MESSAGE_ADMIN,
            "DECONNEXION": "Session terminée : reconnectez-vous.",
            # Lot 25 : session fermée par un blocage du super-administrateur (onglet « Usage »).
            # Tant que le blocage dure, l'appareil reçoit le 403 « Accès momentanément
            # suspendu » ; une fois le blocage levé, il doit simplement se reconnecter.
            "BLOCAGE": "Session fermée : reconnectez-vous."}

_cache_reglage: dict = {"lu_a": 0.0, "valeur": LIMITE_DEFAUT}
_cache_sessions: dict[str, tuple[float, dict]] = {}


def _maintenant() -> float:
    return time.time()


def vider_cache() -> None:
    _cache_reglage.update(lu_a=0.0, valeur=LIMITE_DEFAUT)
    _cache_sessions.clear()


def id_public(sid: str) -> str:
    """Identifiant montré au navigateur (jamais le sid du jeton lui-même)."""
    return hashlib.sha256(f"adlyn-session|{sid}".encode()).hexdigest()[:20]


def decrire_appareil(user_agent: str) -> str:
    """« Chrome sur Android », « Safari sur iPhone »… à partir de l'en-tête User-Agent."""
    ua = user_agent or ""
    if not ua:
        return "Appareil inconnu"
    navigateur = next((nom for cle, nom in (("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung Internet"),
                                            ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
                       if cle in ua), "")
    systeme = next((nom for cle, nom in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
                                         ("Windows", "Windows"), ("Mac OS X", "macOS"), ("Linux", "Linux"))
                    if cle in ua), "")
    if navigateur and systeme:
        return f"{navigateur} sur {systeme}"
    return navigateur or systeme or ua[:60]


def _ip(request: Optional[Request]) -> str:
    if request is None:
        return ""
    import acces
    return acces.ip_client(request)


# ---------------------------------------------------------------------------
# Réglage de la plateforme
# ---------------------------------------------------------------------------
async def limite(cache: bool = True) -> int:
    if cache and _maintenant() - _cache_reglage["lu_a"] < DUREE_CACHE_REGLAGE:
        return _cache_reglage["valeur"]
    doc = await db.parametres_plateforme.find_one({"_id": ID_REGLAGE}) or {}
    valeur = int(doc.get("valeur") or LIMITE_DEFAUT)
    _cache_reglage.update(lu_a=_maintenant(), valeur=valeur)
    return valeur


async def regler_limite(valeur: int, par: str) -> int:
    if valeur is None or not LIMITE_MIN <= int(valeur) <= LIMITE_MAX:
        raise HTTPException(400, f"Nombre de sessions invalide : entre {LIMITE_MIN} et {LIMITE_MAX}")
    await db.parametres_plateforme.update_one({"_id": ID_REGLAGE}, {"$set": {
        "valeur": int(valeur), "modifie_le": datetime.now(timezone.utc).isoformat(), "modifie_par": par}}, upsert=True)
    _cache_reglage.update(lu_a=0.0)
    return int(valeur)


# ---------------------------------------------------------------------------
# Enregistrement des sessions
# ---------------------------------------------------------------------------
def _champs_session(user: dict, contenu: dict, request: Optional[Request]) -> dict:
    import inactivite

    sid = inactivite.id_session(contenu)
    maintenant = _maintenant()
    exp = float(contenu.get("exp") or maintenant + 86_400 * 31)
    return {"user_id": user.get("id"), "boutique_id": user.get("boutique_id"), "v": int(contenu.get("v", 0)),
            "id_public": id_public(sid), "ouverte_le": float(contenu.get("ouv") or maintenant),
            "activite_le": maintenant, "ip": _ip(request),
            "appareil": decrire_appareil(request.headers.get("user-agent", "") if request else ""),
            "expire_ts": exp, "expire_le": datetime.fromtimestamp(exp, timezone.utc)}


def _filtre_ouvertes(user: dict) -> dict:
    return {"user_id": user["id"], "fermee": {"$ne": True}, "v": int(user.get("version_session", 0)),
            "expire_ts": {"$gt": _maintenant()}}


async def ouvrir(user: dict, jeton: str, request: Optional[Request], methode: str = "email") -> int:
    """Nouvelle connexion : enregistre la session puis ferme les plus anciennes au-delà
    de la limite. Renvoie le nombre de sessions fermées.
    `methode` (lot 25) : « email » ou « telephone » (identifiant tapé à la connexion),
    noté dans l'historique des connexions de l'onglet « Usage »."""
    import blocages_acces
    import inactivite
    from auth import decode_access_token

    contenu = decode_access_token(jeton) or {}
    sid = inactivite.id_session(contenu)
    await db.sessions_activite.update_one({"_id": sid}, {"$set": _champs_session(user, contenu, request)}, upsert=True)
    # Lot 25 : une ligne « réussie » dans l'historique des connexions (IP réelle, appareil, session)
    await blocages_acces.journaliser_connexion(user, request, methode, "reussie", sid=sid)
    ouvertes = await db.sessions_activite.find(_filtre_ouvertes(user)).to_list(500)
    en_trop = len(ouvertes) - await limite()
    if en_trop <= 0:
        return 0
    autres = sorted((s for s in ouvertes if s["_id"] != sid),
                    key=lambda s: float(s.get("activite_le") or s.get("ouverte_le") or 0))
    for s in autres[:en_trop]:
        await _fermer(s, "LIMITE")
    import identifiants
    await identifiants.journaliser("SESSIONS_LIMITE_FERMEES", cible=user, par=user, request=request,
                                   details={"nb_sessions": en_trop, "limite": await limite()})
    return en_trop


async def _fermer(doc: dict, motif: str) -> None:
    await db.sessions_activite.update_one({"_id": doc["_id"]}, {"$set": {
        "fermee": True, "motif": motif, "fermee_le": _maintenant()}})
    _cache_sessions.pop(doc["_id"], None)


async def fermer_jeton(jeton: Optional[str]) -> None:
    """Déconnexion : la session libère sa place (le cookie est effacé par ailleurs)."""
    import inactivite
    from auth import decode_access_token

    contenu = decode_access_token(jeton) if jeton else None
    if contenu and contenu.get("sub"):
        await _fermer({"_id": inactivite.id_session(contenu)}, "DECONNEXION")


async def fermer(user_id: str, session_id_public: str, motif: str) -> Optional[dict]:
    """Ferme UNE session d'un compte (par son identifiant public) ; None si introuvable."""
    doc = await db.sessions_activite.find_one({"user_id": user_id, "id_public": session_id_public,
                                               "fermee": {"$ne": True}})
    if doc:
        await _fermer(doc, motif)
    return doc


# ---------------------------------------------------------------------------
# Contrôle de chaque requête authentifiée (auth.get_current_user)
# ---------------------------------------------------------------------------
async def controler(user: dict, contenu: dict, request: Optional[Request]) -> None:
    import inactivite

    sid = inactivite.id_session(contenu)
    maintenant = _maintenant()
    lu = _cache_sessions.get(sid)
    if lu and maintenant - lu[0] < DUREE_CACHE:
        doc = lu[1]
    else:
        doc = await db.sessions_activite.find_one({"_id": sid}) or {}
        if doc.get("fermee") and doc.get("motif") in MESSAGES:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, MESSAGES[doc["motif"]])
        if not doc.get("id_public"):
            # Session ouverte autrement que par la page de connexion (nouveau jeton après un
            # changement de mot de passe…) ou avant cette fonction : enregistrée maintenant
            champs = _champs_session(user, contenu, request)
            await db.sessions_activite.update_one({"_id": sid}, {"$set": champs}, upsert=True)
            doc = {**doc, **champs}
        doc = {"activite_le": doc.get("activite_le") or 0.0}
    activite = request is None or not request.headers.get(ENTETE_FOND)
    if activite and maintenant - float(doc["activite_le"]) >= ECRITURE_ACTIVITE:
        await db.sessions_activite.update_one({"_id": sid}, {"$set": {"activite_le": maintenant}})
        doc = {"activite_le": maintenant}
    _cache_sessions[sid] = (lu[0] if lu and maintenant - lu[0] < DUREE_CACHE else maintenant, doc)


# ---------------------------------------------------------------------------
# Listes
# ---------------------------------------------------------------------------
def _publique(doc: dict, sid_courant: str = "") -> dict:
    def iso(ts):
        return datetime.fromtimestamp(float(ts), timezone.utc).isoformat() if ts else None

    return {"id": doc.get("id_public"), "appareil": doc.get("appareil") or "Appareil inconnu", "ip": doc.get("ip", ""),
            "ouverte_le": iso(doc.get("ouverte_le")), "derniere_activite": iso(doc.get("activite_le") or doc.get("ouverte_le")),
            "courante": doc.get("_id") == sid_courant}


async def lister(user: dict, sid_courant: str = "") -> list[dict]:
    docs = await db.sessions_activite.find(_filtre_ouvertes(user)).to_list(500)
    docs.sort(key=lambda d: -float(d.get("activite_le") or d.get("ouverte_le") or 0))
    return [_publique(d, sid_courant) for d in docs if d.get("id_public")]
