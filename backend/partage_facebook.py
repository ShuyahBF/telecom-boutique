"""Page Facebook d'adLyn animée par Liluvine (SAWALI) — articles des vitrines proposés à la publication.

Demande du propriétaire (12/10/2026) : « Publication Facebook pour ZandGo, adLyn et bfmobility comme nous l'avons
fait pour beAuthentik. » Choix : « Produits + annonces de lancement ».

Pour un développeur WinDev : ce fichier est la « procédure globale » du partage Facebook. SAWALI interroge adLyn par
le canal signé existant (route /api/webhooks/liluvine-retour, clé LILUVINE_WA_HMAC), fait relire les textes par
l'IA, puis publie sur la Page Facebook d'adLyn connectée dans SAWALI.
  {"type": "facebook_candidats", "nombre": 3}                     → {"candidats": [...]}
  {"type": "facebook_publie", "element_id": "…", "post_id": "…"}  → {"ok": true}

Règles :
  - CONSENTEMENT : seule une boutique dont le gérant a coché, dans Paramètres → Réseaux sociaux, « Autoriser adLyn à
    publier mes articles sur sa page Facebook » (champ `publication_facebook_adlyn`, DÉSACTIVÉ par défaut) est
    concernée ; il peut décocher à tout moment ;
  - la boutique est visible du public (active et validée par l'équipe adLyn), hors boutiques de démonstration ;
  - l'article est en vente sur la vitrine (actif, visible, avec un prix), avec une photo et une adresse de vitrine ;
  - on ne transmet que des données de vitrine : nom et courte description de l'article, prix, photo (adresse
    absolue), nom de la boutique et lien de partage du produit (lot 45, compté « facebook » dans les statistiques
    de partage) — jamais le gérant, le téléphone, l'e-mail, le prix d'achat ni les notes internes ;
  - un même article n'est pas reproposé avant DELAI_REPUBLICATION_JOURS jours ; au plus PAR_BOUTIQUE articles d'une
    même boutique par demande, pour que toutes les boutiques consentantes aient leur tour.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import Request

from db import db
from routes.partage import _absolue, _resume, lien_partage_produit, prix_formate
from routes.public import EN_VENTE, VISIBLE

TYPE_CANDIDATS = "facebook_candidats"
TYPE_PUBLIE = "facebook_publie"
TYPES = (TYPE_CANDIDATS, TYPE_PUBLIE)
CHAMP_CONSENTEMENT = "publication_facebook_adlyn"
DELAI_REPUBLICATION_JOURS = 30     # un même article n'est pas republié avant 30 jours
NOMBRE_MAX = 15                    # au plus 15 candidats par demande
PAR_BOUTIQUE = 2                   # au plus 2 articles d'une même boutique par demande


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


async def boutiques_consentantes() -> Dict[str, Dict[str, Any]]:
    """Boutiques visibles du public qui ont autorisé la publication de leurs articles (id → fiche réduite)."""
    filtre = {**dict(VISIBLE), CHAMP_CONSENTEMENT: True, "test": {"$ne": True}, "slug": {"$nin": [None, ""]}}
    return {b["id"]: b async for b in db.boutiques.find(filtre, {"_id": 0, "id": 1, "nom": 1, "slug": 1, "devise": 1})}


async def candidats(nombre: int, request: Request) -> List[Dict[str, Any]]:
    """Articles en vente des boutiques consentantes, avec photo, pas publiés depuis 30 jours.
    Les jamais publiés d'abord, puis les plus récents ; au plus PAR_BOUTIQUE par boutique."""
    nombre = max(1, min(int(nombre or 3), NOMBRE_MAX))
    boutiques = await boutiques_consentantes()
    if not boutiques:
        return []
    limite = (_maintenant() - timedelta(days=DELAI_REPUBLICATION_JOURS)).isoformat()
    filtre = {
        **EN_VENTE, "boutique_id": {"$in": list(boutiques)},
        "image_url": {"$nin": [None, ""]}, "slug": {"$nin": [None, ""]}, "nom": {"$nin": [None, ""]},
        "$or": [{"facebook_publie_le": {"$exists": False}}, {"facebook_publie_le": None},
                {"facebook_publie_le": {"$lt": limite}}],
    }
    champs = {"_id": 0, "id": 1, "boutique_id": 1, "nom": 1, "slug": 1, "description": 1, "image_url": 1,
              "prix_vente": 1, "facebook_publie_le": 1, "created_at": 1}
    docs = await db.produits.find(filtre, champs).sort([("facebook_publie_le", 1), ("created_at", -1)]).to_list(nombre * 10)
    sortie: List[Dict[str, Any]] = []
    par_boutique: Dict[str, int] = {}
    for p in docs:
        b = boutiques[p["boutique_id"]]
        if par_boutique.get(b["id"], 0) >= PAR_BOUTIQUE:
            continue
        photo = _absolue(p.get("image_url"), request)
        if not photo.startswith(("https://", "http://")):
            continue
        devise = b.get("devise") or "FCFA"
        montant = int(round(float(p.get("prix_vente") or 0)))
        sortie.append({
            "element_id": p["id"], "type": "produit", "nom": (p.get("nom") or "")[:150],
            "description": _resume(p.get("description"), 300), "boutique": b.get("nom") or "",
            "prix_fcfa": montant if devise.upper() in ("FCFA", "XOF", "F CFA", "CFA") else None,
            "prix_txt": prix_formate(montant, devise), "photo_url": photo,
            # Lien de partage du lot 45 : aperçu (photo, prix) puis vitrine ; ouverture comptée « facebook »
            "lien": f"{lien_partage_produit(request, b['slug'], p['slug'])}?via=facebook",
        })
        par_boutique[b["id"]] = par_boutique.get(b["id"], 0) + 1
        if len(sortie) >= nombre:
            break
    return sortie


async def marquer_publie(element_id: Any, post_id: Any) -> bool:
    """Note la publication (date et identifiant du post Facebook) sur la fiche de l'article."""
    r = await db.produits.update_one({"id": str(element_id or "")}, {"$set": {
        "facebook_publie_le": _maintenant().isoformat(), "facebook_post_id": (str(post_id) if post_id else None)}})
    return r.matched_count == 1


async def traiter(donnees: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Réponse aux demandes signées de SAWALI (types facebook_candidats / facebook_publie)."""
    if donnees.get("type") == TYPE_CANDIDATS:
        return {"candidats": await candidats(donnees.get("nombre") or 3, request)}
    return {"ok": await marquer_publie(donnees.get("element_id"), donnees.get("post_id"))}
