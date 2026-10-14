"""Lot 52 — CONTACTS D'adLyn LUS PAR SAWALI (groupe « Plateforme adLyn » : messages WhatsApp de masse, carrousels).

Pour un développeur WinDev : UNE route de lecture seule, GET /api/sawali/contacts?limite=500&page=1, appelée par SAWALI
chaque nuit. Pas d'utilisateur connecté : la requête est SIGNÉE avec la clé partagée SAWALI_CONTACTS_HMAC (variable
d'environnement saisie par le propriétaire sur Render, même valeur que CONTACTS_HMAC_ADLYN côté SAWALI) :
    X-Timestamp = horodatage Unix (secondes), valable 5 minutes ;
    X-Signature = HMAC-SHA256(clé, "<horodatage>.GET <chemin>?<requête>") en hexadécimal.
Clé absente → 503 (route désactivée) ; signature absente, périmée ou fausse → 401.

Contenu : le PERSONNEL des boutiques (DG et collaborateurs actifs qui ont un téléphone) avec le nom de leur boutique.
Jamais les clients des boutiques (données des commerçants), ni commande, stock, montant ou mot de passe. Aucun consentement
transmis pour le moment : SAWALI ne diffuse un carrousel qu'aux personnes qui ont donné leur accord elles-mêmes.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from typing import Any, Dict, List, Optional

VALIDITE_SECONDES = 300
LIMITE_DEFAUT = 500
LIMITE_MAX = 1000
VARIABLE_CLE = "SAWALI_CONTACTS_HMAC"


def cle_partagee() -> str:
    return (os.environ.get(VARIABLE_CLE) or "").strip()


def signer(cle: str, horodatage: str, chemin: str, requete: str) -> str:
    """HMAC-SHA256 hexadécimal de « <horodatage>.GET <chemin>?<requête> » (même calcul que SAWALI)."""
    cible = f"{chemin}?{requete}" if requete else chemin
    return hmac.new(cle.encode("utf-8"), f"{horodatage}.GET {cible}".encode("utf-8"), hashlib.sha256).hexdigest()


def signature_valide(cle: str, horodatage: str, signature: str, chemin: str, requete: str, maintenant: Optional[float] = None) -> bool:
    """Vrai si l'horodatage est récent (± 5 minutes) et la signature exacte (comparaison à temps constant)."""
    try:
        ecart = abs((maintenant if maintenant is not None else time.time()) - int(horodatage))
    except (TypeError, ValueError):
        return False
    return ecart <= VALIDITE_SECONDES and hmac.compare_digest(signer(cle, horodatage, chemin, requete), signature or "")


async def tous_les_contacts(db) -> List[Dict[str, Any]]:
    """Personnel actif des boutiques avec téléphone, un contact par numéro, triés de façon stable."""
    boutiques = {b["id"]: b.get("nom") or "" async for b in db.boutiques.find({}, {"_id": 0, "id": 1, "nom": 1})}
    contacts, vus = [], set()
    async for u in db.users.find({"actif": {"$ne": False}, "role": {"$ne": "super_admin"}, "telephone": {"$nin": [None, ""]}},
                                 {"_id": 0, "id": 1, "nom": 1, "telephone": 1, "role": 1, "boutique_id": 1}):
        tel = re.sub(r"\D", "", u.get("telephone") or "")
        if len(tel) < 8 or tel in vus:
            continue
        vus.add(tel)
        boutique = boutiques.get(u.get("boutique_id"), "")
        contacts.append({"id": u["id"], "nom": u.get("nom") or "", "telephone": tel,
                         "role": u.get("role") or "", "societe": f"adLyn · {boutique}" if boutique else "adLyn"})
    return sorted(contacts, key=lambda c: c["id"])


async def page_de_contacts(db, page: int, limite: int) -> Dict[str, Any]:
    limite = max(1, min(int(limite or LIMITE_DEFAUT), LIMITE_MAX))
    tous = await tous_les_contacts(db)
    pages = max(1, -(-len(tous) // limite))
    page = max(1, min(int(page or 1), pages))
    return {"plateforme": "adLyn", "page": page, "pages": pages, "total": len(tous),
            "contacts": tous[(page - 1) * limite: page * limite]}
