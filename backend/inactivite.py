"""Déconnexion après inactivité (durée réglable en SECONDES, 0 = désactivée).

Réglages :
  - plateforme (super-administrateur) : valeur par défaut de toutes les boutiques,
    qui s'applique aussi au super-administrateur lui-même (comme sur SAWALI) ;
  - boutique, par le super-administrateur (`inactivite_secondes`) : remplace la
    valeur de la plateforme pour cette boutique (None = valeur de la plateforme) ;
  - boutique, par le DG (`inactivite_secondes_dg`) : ne peut que RÉDUIRE la durée
    fixée par l'administrateur (le « plafond »), jamais l'allonger.

Contrôle côté serveur (appelé par auth.get_current_user à chaque requête) :
la dernière activité de chaque session est notée en base (collection
« sessions_activite », au plus une écriture par minute et par session). Un jeton
dont la dernière activité dépasse le délai (+ 1 minute de marge, due à cette
écriture espacée) est refusé : « Session expirée après inactivité ». Le site,
lui, déconnecte à la seconde près et prévient avant (minuteur du navigateur).

Les rafraîchissements automatiques du site (compteurs du menu…) portent l'en-tête
« X-Adlyn-Fond » : ils sont contrôlés mais ne comptent PAS comme une activité,
sinon un onglet oublié resterait connecté indéfiniment.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request, status

from db import SANS_ID, db

MIN_SECONDES, MAX_SECONDES = 60, 86_400  # de 1 minute à 24 heures (0 = désactivée)
MARGE_SECONDES = 60  # écriture de l'activité au plus une fois par minute
DUREE_CACHE = 30  # secondes : réglages relus au plus toutes les 30 s
ENTETE_FOND = "x-adlyn-fond"
MESSAGE_INACTIVITE = "Session expirée après inactivité. Reconnectez-vous."
ID_REGLAGE = "inactivite"

# Petits caches en mémoire (réglages et dernière activité connue de chaque session)
_cache_plateforme: dict = {"lu_a": 0.0, "valeur": 0}
_cache_boutiques: dict[str, tuple[float, dict]] = {}
_dernieres: dict[str, float] = {}


def _maintenant() -> float:
    """Heure courante (remplacée dans les tests pour simuler l'inactivité)."""
    return time.time()


def vider_cache() -> None:
    _cache_plateforme.update(lu_a=0.0, valeur=0)
    _cache_boutiques.clear()
    _dernieres.clear()


def valider(secondes: Optional[int], *, nul_permis: bool = False) -> Optional[int]:
    """0 (désactivée) ou entre 60 et 86 400 secondes ; None seulement si `nul_permis`."""
    if secondes is None and nul_permis:
        return None
    if secondes is None or not (secondes == 0 or MIN_SECONDES <= int(secondes) <= MAX_SECONDES):
        raise HTTPException(400, f"Durée d'inactivité invalide : 0 (désactivée) ou entre {MIN_SECONDES} "
                                 f"et {MAX_SECONDES} secondes")
    return int(secondes)


# ---------------------------------------------------------------------------
# Réglages
# ---------------------------------------------------------------------------
async def delai_plateforme(cache: bool = True) -> int:
    if cache and _maintenant() - _cache_plateforme["lu_a"] < DUREE_CACHE:
        return _cache_plateforme["valeur"]
    doc = await db.parametres_plateforme.find_one({"_id": ID_REGLAGE}) or {}
    valeur = int(doc.get("secondes") or 0)
    _cache_plateforme.update(lu_a=_maintenant(), valeur=valeur)
    return valeur


async def regler_plateforme(secondes: int, par: str) -> int:
    secondes = valider(secondes)
    await db.parametres_plateforme.update_one({"_id": ID_REGLAGE}, {"$set": {
        "secondes": secondes, "modifie_le": datetime.now(timezone.utc).isoformat(), "modifie_par": par}}, upsert=True)
    vider_cache()
    return secondes


def plafond_boutique(boutique: dict, plateforme: int) -> int:
    """Durée fixée par l'administrateur pour la boutique (sinon celle de la plateforme)."""
    propre = boutique.get("inactivite_secondes")
    return plateforme if propre is None else int(propre)


def delai_boutique(boutique: dict, plateforme: int) -> int:
    """Durée effective : le réglage du DG s'il est plus court que le plafond."""
    plafond = plafond_boutique(boutique, plateforme)
    dg = boutique.get("inactivite_secondes_dg")
    if dg and (plafond == 0 or int(dg) < plafond):
        return int(dg)
    return plafond


def resume(boutique: dict, plateforme: int) -> dict:
    return {"plateforme": plateforme, "boutique": boutique.get("inactivite_secondes"),
            "dg": boutique.get("inactivite_secondes_dg"), "plafond": plafond_boutique(boutique, plateforme),
            "effective": delai_boutique(boutique, plateforme), "min": MIN_SECONDES, "max": MAX_SECONDES}


async def _boutique(boutique_id: str) -> dict:
    lu = _cache_boutiques.get(boutique_id)
    if lu and _maintenant() - lu[0] < DUREE_CACHE:
        return lu[1]
    doc = await db.boutiques.find_one({"id": boutique_id}, {"_id": 0, "inactivite_secondes": 1,
                                                            "inactivite_secondes_dg": 1}) or {}
    _cache_boutiques[boutique_id] = (_maintenant(), doc)
    return doc


async def delai_utilisateur(user: dict) -> int:
    plateforme = await delai_plateforme()
    if user.get("role") == "super_admin" or not user.get("boutique_id"):
        return plateforme
    return delai_boutique(await _boutique(user["boutique_id"]), plateforme)


def avertissement(secondes: int) -> int:
    """Avertissement 60 s avant la déconnexion, ou 20 % de la durée si elle est courte."""
    return 60 if secondes >= 300 else max(5, round(secondes * 0.2))


# ---------------------------------------------------------------------------
# Contrôle de chaque requête authentifiée
# ---------------------------------------------------------------------------
def id_session(contenu: dict) -> str:
    """Identifiant de la session : « sid » du jeton (anciens jetons : compte + heure d'ouverture)."""
    return str(contenu.get("sid") or f"{contenu.get('sub')}:{contenu.get('ouv', 0)}")


async def controler(user: dict, contenu: dict, request: Optional[Request]) -> None:
    delai = await delai_utilisateur(user)
    if not delai:
        return
    sid = id_session(contenu)
    maintenant = _maintenant()
    activite = request is None or not request.headers.get(ENTETE_FOND)
    connue = _dernieres.get(sid)
    if connue is None or maintenant - connue > MARGE_SECONDES:
        # Plus d'une minute depuis la dernière activité connue ici : on relit la base
        doc = await db.sessions_activite.find_one({"_id": sid}) or {}
        if doc.get("fermee"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, MESSAGE_INACTIVITE)
        connue = doc.get("derniere")
    if connue is not None and maintenant - connue > delai + MARGE_SECONDES:
        # Trop longtemps sans activité : la session est fermée pour de bon
        await db.sessions_activite.update_one({"_id": sid}, {"$set": {"fermee": True}}, upsert=True)
        _dernieres.pop(sid, None)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, MESSAGE_INACTIVITE)
    if connue is None or (activite and maintenant - connue >= MARGE_SECONDES):
        # Première requête de la session, ou activité réelle : au plus une écriture par minute
        expire = datetime.fromtimestamp(float(contenu.get("exp") or maintenant + 86_400 * 31), timezone.utc)
        await db.sessions_activite.update_one({"_id": sid}, {"$set": {
            "derniere": maintenant, "user_id": user.get("id"), "expire_le": expire}}, upsert=True)
        connue = maintenant
    _dernieres[sid] = connue
