"""Onglet « Usage » de l'espace plateforme (lot 25) : historique des connexions,
présence en ligne et blocage d'adresses IP ou de comptes.

Demande du propriétaire (super-administrateur de la plateforme, rôle
« super_admin » UNIQUEMENT ; les DG et le personnel des boutiques reçoivent 403) :

1. HISTORIQUE DES CONNEXIONS — collection `usage_connexions`
   Une ligne par connexion RÉUSSIE (page de connexion) et par tentative REFUSÉE
   pour cause de blocage (connexion, session en cours, demande d'ouverture de
   boutique) : date, adresse IP réelle (acces.ip_client : l'adresse ajoutée par
   le proxy de Render dans X-Forwarded-For), compte, boutique, méthode, appareil
   et identifiant de session (« sid », pour la pastille de présence).
   Purge automatique après 180 jours (index TTL sur `date_dt`, voir db.py).
   À ne pas confondre avec `connexions_journal`, le journal propre à CHAQUE
   boutique tenu par acces.py (règles IP / appareils du DG) : il reste inchangé.

2. PRÉSENCE (pastille en tête de ligne, mêmes règles que SAWALI)
   On réutilise la DERNIÈRE ACTIVITÉ déjà notée sur chaque session
   (sessions_actives.py, champ `activite_le` : au plus une écriture par minute,
   jamais pour une requête de fond « X-Adlyn-Fond ») :
     - verte  : session ouverte, activité dans les 5 dernières minutes ;
     - orange : session ouverte, sans activité depuis 5 à 10 minutes ;
     - rouge  : plus de 10 minutes sans activité, ou session fermée / expirée.

3. BLOCAGES — collection `usage_blocages` (un document par blocage)
     - type « ip » + portée « tous »   : l'adresse IP est refusée pour TOUS les comptes
                                         (et pour les demandes d'ouverture de boutique) ;
     - type « ip » + portée « compte » : l'IP est refusée pour CE compte seulement ;
     - type « compte »                 : le compte est refusé quelle que soit l'IP.
   Un blocage levé n'est pas effacé : il passe à `actif = False` (historique).
   Effet immédiat : sessions concernées fermées (motif « BLOCAGE »), connexion
   refusée (403 avec {"code": "acces_suspendu"}) ; le site efface alors la session
   et affiche la page « Accès momentanément suspendu ».
   Le super-administrateur n'est JAMAIS bloqué (ni à la création du blocage, ni
   au contrôle) : impossible de s'enfermer dehors.
   Chaque action (blocage, levée, réglage du contact) est notée dans
   `usage_blocages_journal` (qui, quand, quoi).
"""
from __future__ import annotations

import ipaddress
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request

from db import SANS_ID, db
from utils import new_id

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
CONSERVATION_JOURS = 180          # durée de conservation de l'historique des connexions
SEUIL_ACTIF_S = 5 * 60            # pastille verte : activité depuis moins de 5 min
SEUIL_ABSENT_S = 10 * 60          # pastille orange jusqu'à 10 min, rouge au-delà
DUREE_CACHE = 10.0                # blocages relus en base au plus toutes les 10 s

# Code et message renvoyés au site (le site affiche alors la page dédiée).
# Volontairement sans détail technique (ni adresse IP, ni motif).
CODE_SUSPENDU = "acces_suspendu"
MESSAGE_SUSPENDU = ("Accès momentanément suspendu. Contactez l'Administrateur pour réclamer "
                    "votre accès ou contester la décision.")

# Libellés lisibles des méthodes de connexion
METHODES = {
    "email": "E-mail + mot de passe",
    "telephone": "Téléphone + mot de passe",
    "session": "Session en cours",
    "creation_boutique": "Demande d'ouverture de boutique",
}

# Réglage « contact affiché sur la page de blocage » (collection parametres_plateforme)
ID_CONTACT = "contact_acces_suspendu"

# Liste des blocages actifs gardée en mémoire (lue à chaque requête authentifiée)
_cache: dict = {"lu_a": 0.0, "blocages": None}


def vider_cache() -> None:
    """Oublie la liste en mémoire : elle sera relue en base à la prochaine requête."""
    _cache.update(lu_a=0.0, blocages=None)


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _ip(request: Optional[Request]) -> str:
    """Adresse IP réelle du visiteur (même règle que le reste d'adLyn, voir acces.py)."""
    if request is None:
        return ""
    import acces
    return acces.ip_client(request)


def exception_suspendu() -> HTTPException:
    """Réponse 403 qui fait afficher la page « Accès momentanément suspendu »."""
    return HTTPException(403, {"code": CODE_SUSPENDU, "message": MESSAGE_SUSPENDU})


def est_super_admin(user: Optional[dict]) -> bool:
    return bool(user) and user.get("role") == "super_admin"


# ---------------------------------------------------------------------------
# Lecture des blocages actifs (avec cache)
# ---------------------------------------------------------------------------
async def blocages_actifs(cache: bool = True) -> list[dict]:
    if cache and _cache["blocages"] is not None and time.monotonic() - _cache["lu_a"] < DUREE_CACHE:
        return _cache["blocages"]
    liste = await db.usage_blocages.find({"actif": True}, SANS_ID).to_list(5000)
    _cache.update(lu_a=time.monotonic(), blocages=liste)
    return liste


def motif_blocage(blocages: list[dict], user_id: Optional[str], ip: Optional[str]) -> Optional[str]:
    """Pourquoi ce compte / cette IP est refusé : « compte », « ip » ou None (autorisé)."""
    for b in blocages:
        if b.get("type") == "compte" and user_id and b.get("user_id") == user_id:
            return "compte"
    for b in blocages:
        if b.get("type") != "ip" or not ip or b.get("ip") != ip:
            continue
        if b.get("portee") == "tous" or (user_id and b.get("user_id") == user_id):
            return "ip"
    return None


def etat_ip(blocages: list[dict], user_id: Optional[str], ip: Optional[str]) -> str:
    """État de l'IP pour l'affichage : « bloquee_tous », « bloquee_compte » ou « autorisee »."""
    for b in blocages:
        if b.get("type") == "ip" and ip and b.get("ip") == ip and b.get("portee") == "tous":
            return "bloquee_tous"
    for b in blocages:
        if b.get("type") == "ip" and ip and b.get("ip") == ip and user_id and b.get("user_id") == user_id:
            return "bloquee_compte"
    return "autorisee"


def compte_bloque(blocages: list[dict], user_id: Optional[str]) -> bool:
    return bool(user_id) and any(b.get("type") == "compte" and b.get("user_id") == user_id for b in blocages)


# ---------------------------------------------------------------------------
# Historique des connexions
# ---------------------------------------------------------------------------
async def journaliser_connexion(user: Optional[dict], request: Optional[Request], methode: str, etat: str, *,
                                sid: Optional[str] = None, motif: Optional[str] = None,
                                identifiant: str = "") -> None:
    """Ajoute une ligne à l'historique. Ne lève jamais d'exception : un échec
    d'écriture ne doit pas empêcher la connexion."""
    import sessions_actives

    maintenant = _maintenant()
    user = user or {}
    ua = request.headers.get("user-agent", "") if request is not None else ""
    try:
        await db.usage_connexions.insert_one({
            "id": new_id(), "date": maintenant.isoformat(), "date_dt": maintenant,
            "user_id": user.get("id"), "boutique_id": user.get("boutique_id"),
            "identifiant": (identifiant or user.get("email") or user.get("telephone") or "")[:200],
            "role": user.get("role", ""), "ip": _ip(request), "methode": methode, "etat": etat,
            "motif": motif, "sid": sid,
            "appareil": sessions_actives.decrire_appareil(ua), "user_agent": ua[:300],
        })
    except Exception as exc:  # noqa: BLE001 — l'historique ne doit jamais bloquer une connexion
        print(f"[usage] historique des connexions impossible : {exc!r}")


# ---------------------------------------------------------------------------
# Contrôles : à la connexion, à chaque requête authentifiée, à la création d'une boutique
# ---------------------------------------------------------------------------
async def controler_connexion(user: dict, request: Request, methode: str, identifiant: str = "") -> None:
    """À appeler AVANT d'ouvrir une session (routes/auth.py, connexion réussie).
    Compte ou IP bloqué : la tentative est notée « refusée » puis refusée (403)."""
    if est_super_admin(user):
        return  # le super-administrateur n'est jamais bloqué
    motif = motif_blocage(await blocages_actifs(cache=False), user.get("id"), _ip(request))
    if not motif:
        return
    await journaliser_connexion(user, request, methode, "refusee", motif=motif, identifiant=identifiant)
    raise exception_suspendu()


async def controler_creation(request: Request, identifiant: str = "") -> None:
    """Demande d'ouverture de boutique (page publique de parrainage) : refusée
    depuis une adresse IP bloquée pour tous les comptes."""
    ip = _ip(request)
    if motif_blocage(await blocages_actifs(cache=False), None, ip):
        await journaliser_connexion(None, request, "creation_boutique", "refusee", motif="ip", identifiant=identifiant)
        raise exception_suspendu()


async def controler_requete(user: dict, contenu: dict, request: Optional[Request]) -> None:
    """À chaque requête authentifiée (auth.get_current_user) : si le compte ou
    l'IP de la requête est bloqué, la session est fermée et la requête refusée."""
    if est_super_admin(user):
        return
    motif = motif_blocage(await blocages_actifs(), user.get("id"), _ip(request))
    if not motif:
        return
    import inactivite
    import sessions_actives

    sid = inactivite.id_session(contenu)
    res = await db.sessions_activite.update_one({"_id": sid, "fermee": {"$ne": True}}, {"$set": {
        "fermee": True, "motif": "BLOCAGE", "fermee_le": sessions_actives._maintenant()}})  # noqa: SLF001
    sessions_actives._cache_sessions.pop(sid, None)  # noqa: SLF001
    if res.modified_count:
        # Première requête refusée de cette session : une seule ligne dans l'historique
        await journaliser_connexion(user, request, "session", "refusee", sid=sid, motif=motif)
    raise exception_suspendu()


# ---------------------------------------------------------------------------
# Présence (pastille verte / orange / rouge)
# ---------------------------------------------------------------------------
def couleur_presence(session: Optional[dict], version_compte: Optional[int] = None,
                     maintenant_s: Optional[float] = None) -> dict:
    """Couleur de la pastille d'une session (document de `sessions_activite`)."""
    rouge = {"couleur": "rouge", "libelle": "Déconnecté", "derniere_activite": None}
    if not session or session.get("fermee"):
        return rouge
    import sessions_actives

    maintenant_s = sessions_actives._maintenant() if maintenant_s is None else maintenant_s  # noqa: SLF001
    if float(session.get("expire_ts") or 0) <= maintenant_s:
        return rouge  # jeton expiré
    if version_compte is not None and int(session.get("v", 0)) != int(version_compte):
        return rouge  # mot de passe changé, « déconnecter partout »… : session invalide
    derniere = session.get("activite_le") or session.get("ouverte_le")
    if not derniere:
        return rouge
    ecart = maintenant_s - float(derniere)
    iso = datetime.fromtimestamp(float(derniere), timezone.utc).isoformat()
    if ecart <= SEUIL_ACTIF_S:
        return {"couleur": "vert", "libelle": "Connecté et actif", "derniere_activite": iso}
    if ecart <= SEUIL_ABSENT_S:
        return {"couleur": "orange", "libelle": "Connecté, inactif depuis plus de 5 min", "derniere_activite": iso}
    return {"couleur": "rouge", "libelle": "Inactif depuis plus de 10 min", "derniere_activite": iso}


async def presence_sessions(sids: list[str]) -> dict[str, dict]:
    """Pastille de chaque session demandée (sid -> {couleur, libelle, derniere_activite})."""
    sids = [s for s in dict.fromkeys(sids) if s][:500]
    if not sids:
        return {}
    docs = {d["_id"]: d for d in await db.sessions_activite.find({"_id": {"$in": sids}}).to_list(len(sids))}
    uids = list({d.get("user_id") for d in docs.values() if d.get("user_id")})
    comptes = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": uids}}, {"_id": 0, "id": 1, "version_session": 1, "actif": 1}).to_list(len(uids) or 1)}
    resultat = {}
    for sid in sids:
        doc = docs.get(sid)
        compte = comptes.get((doc or {}).get("user_id")) or {}
        if doc and compte.get("actif") is False:
            doc = None  # compte désactivé : déconnecté
        resultat[sid] = couleur_presence(doc, compte.get("version_session", 0) if compte else None)
    return resultat


# ---------------------------------------------------------------------------
# Création et levée des blocages
# ---------------------------------------------------------------------------
def _qui(adm: dict) -> str:
    return adm.get("email") or adm.get("telephone") or adm.get("nom") or ""


async def journaliser_action(action: str, adm: dict, **details) -> None:
    """Journal des actions du super-administrateur (qui, quand, quoi)."""
    await db.usage_blocages_journal.insert_one({
        "id": new_id(), "date": _maintenant().isoformat(), "action": action,
        "par": _qui(adm), "par_id": adm.get("id"), "details": details})


async def _fermer_sessions(filtre: dict) -> int:
    """Ferme les sessions ouvertes correspondant au filtre (jamais celles du super-administrateur)."""
    import sessions_actives

    admins = set(await db.users.distinct("id", {"role": "super_admin"}))
    docs = await db.sessions_activite.find(
        {**filtre, "fermee": {"$ne": True}, "expire_ts": {"$gt": sessions_actives._maintenant()}},  # noqa: SLF001
        {"_id": 1, "user_id": 1}).to_list(5000)
    n = 0
    for d in docs:
        if d.get("user_id") in admins:
            continue  # le super-administrateur n'est jamais déconnecté par un blocage
        await sessions_actives._fermer(d, "BLOCAGE")  # noqa: SLF001
        n += 1
    return n


def valider_ip(ip: Optional[str]) -> str:
    """Adresse IP exacte (IPv4 ou IPv6), sans « * » : sinon erreur 400."""
    ip = (ip or "").strip()
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError as exc:
        raise HTTPException(400, "Adresse IP invalide") from exc


async def bloquer(adm: dict, request: Request, *, type_: str, ip: Optional[str] = None,
                  user_id: Optional[str] = None, tous_comptes: bool = True,
                  libelle: Optional[str] = None, motif: Optional[str] = None) -> dict:
    """Crée un blocage (voir la docstring du module) et ferme les sessions concernées."""
    libelle = (libelle or "").strip()[:120] or None
    motif = (motif or "").strip()[:300] or None
    compte = None
    if user_id:
        compte = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "role": 1, "nom": 1, "email": 1,
                                                           "telephone": 1, "boutique_id": 1})
        if not compte:
            raise HTTPException(404, "Compte introuvable")
    # --- Règle absolue : le super-administrateur ne peut pas se bloquer lui-même ---
    if compte and (compte["id"] == adm.get("id") or est_super_admin(compte)):
        if type_ == "compte" or not tous_comptes:
            raise HTTPException(400, "Vous ne pouvez pas bloquer le compte du super-administrateur "
                                     "(le vôtre) : cela vous empêcherait d'accéder à la plateforme.")

    if type_ == "compte":
        if not compte:
            raise HTTPException(400, "Compte à bloquer non précisé")
        if await db.usage_blocages.find_one({"actif": True, "type": "compte", "user_id": compte["id"]}):
            raise HTTPException(409, "Ce compte est déjà bloqué")
        doc = {"type": "compte", "portee": "compte", "ip": None, "user_id": compte["id"]}
    elif type_ == "ip":
        ip = valider_ip(ip)
        if ip == _ip(request):
            raise HTTPException(400, "Vous ne pouvez pas bloquer l'adresse IP que vous utilisez en ce moment : "
                                     "cela vous bloquerait vous-même.")
        if not tous_comptes and not compte:
            raise HTTPException(400, "Compte non précisé pour un blocage limité à ce compte")
        portee = "tous" if tous_comptes else "compte"
        cible = {"actif": True, "type": "ip", "ip": ip, "portee": portee}
        if portee == "compte":
            cible["user_id"] = compte["id"]
        if await db.usage_blocages.find_one(cible):
            raise HTTPException(409, "Cette adresse IP est déjà bloquée")
        doc = {"type": "ip", "portee": portee, "ip": ip, "user_id": compte["id"] if portee == "compte" else None}
    else:
        raise HTTPException(400, "Type de blocage inconnu")

    # Pour la liste « Blocages en cours » : compte (et boutique) visé au moment du blocage
    vise = compte if doc["user_id"] else None
    boutique = await db.boutiques.find_one({"id": vise.get("boutique_id")}, {"_id": 0, "nom": 1}) \
        if vise and vise.get("boutique_id") else None
    doc.update({
        "id": new_id(), "actif": True, "libelle": libelle, "motif": motif,
        "cree_le": _maintenant().isoformat(), "cree_par": _qui(adm), "cree_par_id": adm.get("id"),
        "compte_nom": (vise or {}).get("nom"),
        "compte_identifiant": (vise or {}).get("email") or (vise or {}).get("telephone"),
        "boutique_nom": (boutique or {}).get("nom"),
    })
    await db.usage_blocages.insert_one(doc.copy())
    vider_cache()
    # Effet immédiat : les sessions en cours concernées sont fermées
    if doc["type"] == "compte":
        fermees = await _fermer_sessions({"user_id": doc["user_id"]})
    elif doc["portee"] == "tous":
        fermees = await _fermer_sessions({"ip": doc["ip"]})
    else:
        fermees = await _fermer_sessions({"ip": doc["ip"], "user_id": doc["user_id"]})
    if doc["type"] == "compte":
        action = "Compte bloqué"
    elif doc["portee"] == "tous":
        action = "Adresse IP bloquée pour tous les comptes"
    else:
        action = "Adresse IP bloquée pour ce compte"
    await journaliser_action(action, adm, blocage=doc["id"], ip=doc.get("ip"), compte=doc.get("compte_nom"),
                             compte_identifiant=doc.get("compte_identifiant"), boutique=doc.get("boutique_nom"),
                             libelle=libelle, motif=motif, sessions_fermees=fermees)
    return {**doc, "sessions_fermees": fermees}


async def lever(adm: dict, blocage_id: str) -> dict:
    """Lève un blocage (« Autoriser ») : il reste dans l'historique, inactif."""
    doc = await db.usage_blocages.find_one({"id": blocage_id, "actif": True}, SANS_ID)
    if not doc:
        raise HTTPException(404, "Blocage introuvable ou déjà levé")
    await db.usage_blocages.update_one({"id": blocage_id}, {"$set": {
        "actif": False, "leve_le": _maintenant().isoformat(), "leve_par": _qui(adm)}})
    vider_cache()
    await journaliser_action("Blocage levé (accès autorisé)", adm, blocage=blocage_id, type=doc.get("type"),
                             portee=doc.get("portee"), ip=doc.get("ip"), compte=doc.get("compte_nom"),
                             compte_identifiant=doc.get("compte_identifiant"), libelle=doc.get("libelle"))
    return {"ok": True}


async def autoriser(adm: dict, *, type_: str, ip: Optional[str] = None, user_id: Optional[str] = None) -> int:
    """Lève tous les blocages actifs qui touchent cette IP (pour ce compte ou
    pour tous) ou ce compte. Renvoie le nombre de blocages levés."""
    if type_ == "compte":
        if not user_id:
            raise HTTPException(400, "Compte non précisé")
        filtre = {"actif": True, "type": "compte", "user_id": user_id}
    else:
        ip = valider_ip(ip)
        filtre = {"actif": True, "type": "ip", "ip": ip,
                  "$or": [{"portee": "tous"}, {"user_id": user_id}] if user_id else [{"portee": "tous"}]}
    ids = [d["id"] for d in await db.usage_blocages.find(filtre, {"_id": 0, "id": 1}).to_list(100)]
    for bid in ids:
        await lever(adm, bid)
    return len(ids)


# ---------------------------------------------------------------------------
# Contact affiché sur la page « Accès momentanément suspendu »
# ---------------------------------------------------------------------------
async def lire_contact() -> dict:
    doc = await db.parametres_plateforme.find_one({"_id": ID_CONTACT}) or {}
    return {"email": doc.get("email") or "", "whatsapp": doc.get("whatsapp") or ""}


async def regler_contact(adm: dict, email: Optional[str], whatsapp: Optional[str]) -> dict:
    email = (email or "").strip()[:200]
    whatsapp = (whatsapp or "").strip()[:40]
    if email and ("@" not in email or " " in email or "." not in email.split("@")[-1]):
        raise HTTPException(400, "Adresse e-mail de contact invalide")
    if whatsapp and (not all(c.isdigit() or c in "+ " for c in whatsapp)
                     or sum(c.isdigit() for c in whatsapp) < 8):
        raise HTTPException(400, "Numéro WhatsApp invalide (indicatif et numéro : chiffres, espaces et « + »)")
    await db.parametres_plateforme.update_one({"_id": ID_CONTACT}, {"$set": {
        "email": email, "whatsapp": whatsapp, "modifie_le": _maintenant().isoformat(),
        "modifie_par": _qui(adm)}}, upsert=True)
    await journaliser_action("Contact de la page de blocage modifié", adm, email=email, whatsapp=whatsapp)
    return await lire_contact()


def borne_jour(jour: Optional[str], fin: bool = False) -> Optional[str]:
    """« AAAA-MM-JJ » → borne ISO (UTC = heure de Ouagadougou). `fin` : lendemain 0 h."""
    if not jour:
        return None
    try:
        d = datetime.strptime(jour, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(400, "Date invalide (format attendu AAAA-MM-JJ)") from exc
    return (d + timedelta(days=1) if fin else d).isoformat()
