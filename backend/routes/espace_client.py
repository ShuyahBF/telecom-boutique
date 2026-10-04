"""« Mon espace » : espace client PUBLIC de chaque boutique (lecture seule).

Parcours :
  1. Le client scanne le QR code de sa facture / proforma : la page « /q/<jeton> »
     du site appelle GET /api/espace-client/qr/<jeton>. Le jeton (chiffré et signé,
     voir jetons_qr.py) désigne la boutique ; la page affiche son logo, son nom,
     ses coordonnées et le bouton « Mon espace ». Sans QR code, « Mon espace » est
     aussi proposé sur la vitrine (GET /api/espace-client/b/<slug>).
  2. Le client saisit SON numéro de téléphone (son « mot de passe ») :
     POST /api/espace-client/demander-code. Le numéro doit correspondre à l'empreinte
     du jeton OU à un client de la boutique. Un code à usage unique de 6 chiffres
     (valable 10 minutes, 5 essais) lui est envoyé par WhatsApp (Transmission WA :
     WABA de la boutique, puis de la plateforme, puis Liluvine), sinon par SMS si la
     boutique a un service SMS actif, sinon un message clair est renvoyé.
     Anti-abus : nombre de codes limité par numéro (et délai entre deux codes) et
     nombre de demandes limité par adresse IP.
  3. POST /api/espace-client/verifier-code : si le code est bon, une SESSION courte
     est ouverte (30 minutes, prolongées à chaque action) : jeton chiffré renvoyé au
     site (gardé en mémoire) ET cookie HttpOnly. La session est CLOISONNÉE à ce client
     de cette boutique : toutes les lectures filtrent sur les deux.
  4. Lecture seule : factures et achats, devis / proformas, règlements et reste à
     payer, suivi SAV (dossiers de réparation et maintenance des équipements).
Chaque ouverture de session est journalisée (date, boutique, client, IP masquée).
Le code reçu n'est JAMAIS conservé en clair (seulement son empreinte HMAC).
"""
from __future__ import annotations

import ipaddress
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import acces
import jetons_qr
from config import get_settings
from db import SANS_ID, TenantDB, db
from utils import new_id, now_iso

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/espace-client", tags=["Espace client public"])

# Nom du cookie de session de l'espace client (différent de celui du personnel)
COOKIE_SESSION = "adlyn_espace_client"
# En-tête qui transporte le jeton gardé en mémoire par le site (si le navigateur bloque le cookie)
ENTETE_SESSION = "x-espace-client"
# Durée de vie maximale absolue d'un jeton de session, même s'il reste actif (12 heures)
DUREE_MAX_SESSION = 12 * 3600

# Coordonnées de la boutique montrées sur la page publique minimale (jamais de donnée interne)
CHAMPS_BOUTIQUE = ("nom", "slug", "code_marchand", "slogan", "logo_url", "adresse", "ville", "pays",
                   "telephone", "email", "couleur", "devise")
# Coordonnées imprimées sur une facture (déjà présentes sur le papier remis au client)
CHAMPS_BOUTIQUE_FACTURE = CHAMPS_BOUTIQUE + ("ifu", "rccm", "conditions_facture")

LIBELLES_MODE = {"ESP": "Espèces", "OM": "Orange Money", "MOOV": "Moov Money", "MM": "Mobile Money",
                 "CB": "Carte bancaire", "VIR": "Virement", "CHQ": "Chèque", "PISPI": "PI-SPI"}


# ---------------------------------------------------------------------------
# Petits outils : heure, IP masquée, boutique publique
# ---------------------------------------------------------------------------
def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def ip_masquee(ip: str) -> str:
    """Adresse IP masquée pour le journal : « 196.28.45.x » ou « 2001:db8:85a3:… »."""
    try:
        adresse = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return "inconnue"
    if adresse.version == 4:
        return ".".join(str(adresse).split(".")[:3]) + ".x"
    return ":".join(adresse.exploded.split(":")[:3]) + ":…"


def page_publique_active(b: dict) -> bool:
    """La vitrine publique de la boutique est-elle ouverte ? (même règle que routes/public.py)"""
    return bool(b.get("actif")) and b.get("validee") is not False


def boutique_minimale(b: dict) -> dict:
    """Ce qu'affiche la page de la boutique ouverte par le QR code."""
    return {**{k: b.get(k) for k in CHAMPS_BOUTIQUE}, "page_publique": page_publique_active(b)}


def telephone_masque(telephone: str) -> str:
    """« +22670112233 » -> « +226 •• •• 22 33 » (affiché après l'envoi du code)."""
    chiffres = telephone.lstrip("+")
    if len(chiffres) < 6:
        return "••••"
    return f"+{chiffres[:3]} •• •• {chiffres[-4:-2]} {chiffres[-2:]}"


# ---------------------------------------------------------------------------
# 1. Page de la boutique : par QR code ou par adresse (slug)
# ---------------------------------------------------------------------------
@router.get("/qr/{jeton}")
async def ouvrir_qr(jeton: str):
    """Jeton du QR code -> boutique (logo, nom, contact) et document concerné.
    Aucune donnée du client n'est renvoyée : il faut d'abord se connecter."""
    contenu = jetons_qr.lire_jeton_document(jeton)
    if not contenu:
        raise HTTPException(404, "QR code non reconnu")
    b = await db.boutiques.find_one({"id": contenu["b"]}, SANS_ID)
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    return {"boutique": boutique_minimale(b), "document": {"numero": contenu.get("n") or "", "date": contenu.get("d") or ""}}


@router.get("/b/{slug}")
async def ouvrir_boutique(slug: str):
    """« Mon espace » ouvert depuis la vitrine (boutique visible du public seulement)."""
    from routes.public import _boutique

    return {"boutique": boutique_minimale(await _boutique(slug)), "document": None}


# ---------------------------------------------------------------------------
# 2. Demande du code à usage unique
# ---------------------------------------------------------------------------
class DemandeCode(BaseModel):
    jeton: Optional[str] = Field(None, max_length=2000)  # jeton du QR code (facultatif)
    slug: Optional[str] = Field(None, max_length=120)  # adresse de la vitrine (sans QR code)
    telephone: str = Field(..., min_length=8, max_length=30)


async def _resoudre_boutique(jeton: Optional[str], slug: Optional[str]) -> tuple[dict, Optional[dict]]:
    """Boutique concernée (et contenu du jeton s'il y en a un)."""
    if jeton:
        contenu = jetons_qr.lire_jeton_document(jeton)
        if not contenu:
            raise HTTPException(404, "QR code non reconnu")
        b = await db.boutiques.find_one({"id": contenu["b"]}, SANS_ID)
        if not b:
            raise HTTPException(404, "Boutique introuvable")
        return b, contenu
    if slug:
        from routes.public import _boutique

        return await _boutique(slug), None
    raise HTTPException(400, "Boutique non précisée")


async def _client_par_telephone(tdb: TenantDB, canonique: str) -> Optional[dict]:
    """Client de la boutique qui a ce numéro (toutes les écritures possibles du même numéro)."""
    variantes = {canonique, "+" + canonique.lstrip("+"), canonique.lstrip("+"), "00" + canonique.lstrip("+")}
    if canonique.startswith("+226") and len(canonique) == 12:
        variantes.add(canonique[4:])  # numéro local burkinabè à 8 chiffres
    clients = await tdb.clients.find({"telephone": {"$in": sorted(variantes)}}).sort("created_at", 1).to_list(20)
    return next((c for c in clients if jetons_qr.telephone_canonique(c.get("telephone")) == canonique), None)


async def _compter(cle: str, depuis: datetime) -> int:
    return await db.espace_client_limites.count_documents({"cle": cle, "date": {"$gte": depuis.isoformat()}})


async def _noter(cle: str, duree: timedelta) -> None:
    maintenant = _maintenant()
    await db.espace_client_limites.insert_one({"cle": cle, "date": maintenant.isoformat(),
                                               "expire_le": maintenant + duree})


async def envoyer_code(b: dict, telephone: str, code: str) -> tuple[Optional[str], str]:
    """Envoie le code -> (canal « WhatsApp » / « SMS », "") ou (None, message d'erreur).
    WhatsApp par la Transmission WA (WABA boutique -> WABA plateforme -> Liluvine),
    avec le modèle « Authentication » s'il est configuré ; sinon SMS de la boutique."""
    import sms_boutiques
    import transmission_wa

    s = get_settings()
    texte = (f"{b.get('nom') or 'adLyn'} : votre code d'accès à votre espace client est {code}. "
             f"Il est valable {s.espace_client_code_minutes} minutes. Ne le communiquez à personne.")
    modele = (s.whatsapp_code_template or "").strip()
    if modele:
        # Modèle « Authentication » de Meta : le code + bouton « Copier le code »
        composants = [{"type": "body", "parameters": [{"type": "text", "text": code}]},
                      {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": code}]}]
        resultat = await transmission_wa.envoyer_whatsapp(telephone, texte, boutique=b, modele=modele, composants=composants)
    else:
        resultat = await transmission_wa.envoyer_whatsapp(telephone, texte, boutique=b, modele="")
    if resultat.get("ok"):
        return "WhatsApp", ""
    # Repli : SMS de la boutique (service OVH activé par adLyn), s'il est actif
    if sms_boutiques.peut_envoyer(b) and not b.get("test"):
        ligne = await sms_boutiques.envoyer(b, telephone, texte, origine="ESPACE_CLIENT_CODE")
        if ligne.get("statut") == "ENVOYE":
            return "SMS", ""
    return None, ("Le code n'a pas pu vous être envoyé (WhatsApp indisponible et aucun SMS possible pour "
                  "cette boutique). Contactez la boutique pour accéder à vos documents.")


@router.post("/demander-code")
async def demander_code(payload: DemandeCode, request: Request):
    s = get_settings()
    ip = acces.ip_client(request)
    maintenant = _maintenant()
    # Anti-abus par adresse IP : toute demande compte, même avec un mauvais numéro
    cle_ip = f"ip:{jetons_qr.hacher('limite-ip', ip)}"
    if await _compter(cle_ip, maintenant - timedelta(hours=1)) >= s.espace_client_demandes_par_ip:
        raise HTTPException(429, "Trop de demandes depuis cette connexion : réessayez dans une heure.")
    await _noter(cle_ip, timedelta(hours=1))

    b, contenu = await _resoudre_boutique(payload.jeton, payload.slug)
    canonique = jetons_qr.telephone_canonique(payload.telephone)
    if len(canonique.lstrip("+")) < 8:
        raise HTTPException(400, "Numéro de téléphone invalide")
    tdb = TenantDB(b["id"])

    # Le numéro doit correspondre à l'empreinte du QR code, sinon à un client de la boutique
    client = None
    if contenu and contenu.get("c") and jetons_qr.empreintes_egales(
            contenu.get("e", ""), jetons_qr.empreinte_telephone(b["id"], canonique)):
        client = await tdb.clients.find_one({"id": contenu["c"]})
    if not client:
        client = await _client_par_telephone(tdb, canonique)
    if not client:
        raise HTTPException(403, "Ce numéro ne correspond à aucun client de cette boutique.")

    # Anti-abus par numéro : délai entre deux codes, et nombre de codes par quart d'heure
    cle_tel = f"tel:{jetons_qr.hacher('limite-tel', b['id'] + '|' + canonique)}"
    if await _compter(cle_tel, maintenant - timedelta(seconds=s.espace_client_delai_renvoi_secondes)):
        raise HTTPException(429, "Un code vient d'être envoyé : patientez une minute avant d'en redemander un.")
    if await _compter(cle_tel, maintenant - timedelta(minutes=15)) >= s.espace_client_codes_par_numero:
        raise HTTPException(429, "Trop de codes demandés pour ce numéro : réessayez dans un quart d'heure.")

    # Code à 6 chiffres, tiré au hasard (générateur cryptographique)
    code = f"{secrets.randbelow(10 ** 6):06d}"
    destinataire = jetons_qr.telephone_canonique(client.get("telephone")) or canonique
    destinataire = destinataire if destinataire.startswith("+") else "+" + destinataire
    canal, erreur = await envoyer_code(b, destinataire, code)
    await _noter(cle_tel, timedelta(minutes=15))
    if not canal:
        raise HTTPException(503, erreur)

    demande_id = new_id()
    await db.espace_client_codes.insert_one({
        "id": demande_id, "boutique_id": b["id"], "client_id": client["id"],
        # Seule l'EMPREINTE du code est gardée (jamais le code lui-même)
        "code_hash": jetons_qr.hacher("code-espace-client", f"{demande_id}|{code}"),
        "date": maintenant.isoformat(),
        "expire_a": (maintenant + timedelta(minutes=s.espace_client_code_minutes)).isoformat(),
        "expire_le": maintenant + timedelta(hours=1),  # effacement automatique (index TTL)
        "essais": 0, "statut": "EN_ATTENTE", "canal": canal, "ip": ip_masquee(ip),
    })
    return {"demande_id": demande_id, "canal": canal, "destinataire": telephone_masque(destinataire),
            "expire_dans": s.espace_client_code_minutes * 60}


# ---------------------------------------------------------------------------
# 3. Vérification du code et ouverture de la session
# ---------------------------------------------------------------------------
class VerificationCode(BaseModel):
    demande_id: str = Field(..., max_length=60)
    code: str = Field(..., min_length=4, max_length=10)


def _cookie_securise() -> bool:
    from auth import _cookie_securise as securise

    return securise()


def _poser_cookie(response: Response, jeton: str) -> None:
    securise = _cookie_securise()
    response.set_cookie(COOKIE_SESSION, jeton, max_age=DUREE_MAX_SESSION, httponly=True, secure=securise,
                        samesite="none" if securise else "lax", path="/")


def _effacer_cookie(response: Response) -> None:
    securise = _cookie_securise()
    response.delete_cookie(COOKIE_SESSION, path="/", secure=securise, httponly=True,
                           samesite="none" if securise else "lax")


@router.post("/verifier-code")
async def verifier_code(payload: VerificationCode, request: Request, response: Response):
    s = get_settings()
    d = await db.espace_client_codes.find_one({"id": payload.demande_id}, SANS_ID)
    if not d or d.get("statut") != "EN_ATTENTE":
        raise HTTPException(400, "Ce code n'est plus valable : demandez un nouveau code.")
    if now_iso() > d["expire_a"]:
        await db.espace_client_codes.update_one({"id": d["id"]}, {"$set": {"statut": "EXPIRE"}})
        raise HTTPException(400, "Code expiré : demandez un nouveau code.")
    if d.get("essais", 0) >= s.espace_client_code_essais:
        raise HTTPException(429, "Trop d'essais : demandez un nouveau code.")

    attendu = jetons_qr.hacher("code-espace-client", f"{d['id']}|{payload.code.strip()}")
    if not jetons_qr.empreintes_egales(attendu, d["code_hash"]):
        # Mauvais code : un essai de moins ; au 5e, le code est définitivement bloqué
        from pymongo import ReturnDocument

        apres = await db.espace_client_codes.find_one_and_update(
            {"id": d["id"]}, {"$inc": {"essais": 1}}, return_document=ReturnDocument.AFTER)
        restants = s.espace_client_code_essais - int((apres or d).get("essais", 0))
        if restants <= 0:
            await db.espace_client_codes.update_one({"id": d["id"]}, {"$set": {"statut": "BLOQUE"}})
            raise HTTPException(429, "Trop d'essais : demandez un nouveau code.")
        raise HTTPException(400, f"Code incorrect ({restants} essai(s) restant(s)).")

    # Bon code : il est consommé de façon atomique (un même code n'ouvre qu'une session)
    if not await db.espace_client_codes.find_one_and_update(
            {"id": d["id"], "statut": "EN_ATTENTE"}, {"$set": {"statut": "UTILISE", "utilise_le": now_iso()}}):
        raise HTTPException(400, "Ce code n'est plus valable : demandez un nouveau code.")

    b = await db.boutiques.find_one({"id": d["boutique_id"]}, SANS_ID)
    client = await TenantDB(d["boutique_id"]).clients.find_one({"id": d["client_id"]})
    if not b or not client:
        raise HTTPException(404, "Compte client introuvable")

    # Session : identifiant aléatoire (seule son empreinte est gardée en base)
    sid = secrets.token_urlsafe(32)
    maintenant = _maintenant()
    await db.espace_client_sessions.insert_one({
        "sid_hash": jetons_qr.hacher("session-espace-client", sid), "boutique_id": b["id"], "client_id": client["id"],
        "creee_le": maintenant.isoformat(), "derniere_activite": maintenant.isoformat(),
        "expire_le": maintenant + timedelta(minutes=s.espace_client_session_minutes), "fermee": False,
    })
    # Journal des connexions à l'espace client (IP masquée)
    ip = acces.ip_client(request)
    await db.espace_client_connexions.insert_one({
        "id": new_id(), "date": maintenant.isoformat(), "boutique_id": b["id"], "client_id": client["id"],
        "client_nom": client.get("nom", ""), "ip": ip_masquee(ip), "canal": d.get("canal", ""),
    })
    jeton = jetons_qr.creer_jeton_session(sid, b["id"], client["id"])
    _poser_cookie(response, jeton)
    return {"jeton": jeton, "expire_dans": s.espace_client_session_minutes * 60,
            "client": {"nom": client.get("nom", "")}, "boutique": boutique_minimale(b)}


# ---------------------------------------------------------------------------
# Session : contrôle à chaque appel (30 minutes glissantes, cloisonnement)
# ---------------------------------------------------------------------------
class SessionClient:
    """Session vérifiée : boutique et client FIXÉS par le serveur (jamais par le navigateur)."""

    def __init__(self, sid_hash: str, boutique_id: str, client_id: str):
        self.sid_hash = sid_hash
        self.boutique_id = boutique_id
        self.client_id = client_id
        self.tdb = TenantDB(boutique_id)  # toutes les lectures limitées à CETTE boutique


async def session_client(request: Request) -> SessionClient:
    s = get_settings()
    jeton = request.headers.get(ENTETE_SESSION) or ""
    if not jeton:
        jeton = request.cookies.get(COOKIE_SESSION, "")
        # Protection CSRF : une écriture authentifiée par cookie doit porter l'en-tête du site
        if jeton and request.method not in ("GET", "HEAD", "OPTIONS") and not request.headers.get("x-adlyn"):
            raise HTTPException(403, "Requête refusée (en-tête de sécurité manquant)")
    contenu = jetons_qr.lire_jeton_session(jeton, DUREE_MAX_SESSION) if jeton else None
    if not contenu:
        raise HTTPException(401, "Session expirée : reconnectez-vous à votre espace.")
    sid_hash = jetons_qr.hacher("session-espace-client", contenu["s"])
    session = await db.espace_client_sessions.find_one({"sid_hash": sid_hash}, SANS_ID)
    if (not session or session.get("fermee") or session.get("boutique_id") != contenu.get("b")
            or session.get("client_id") != contenu.get("c")):
        raise HTTPException(401, "Session expirée : reconnectez-vous à votre espace.")
    maintenant = _maintenant()
    limite = (maintenant - timedelta(minutes=s.espace_client_session_minutes)).isoformat()
    if session["derniere_activite"] < limite:
        await db.espace_client_sessions.update_one({"sid_hash": sid_hash}, {"$set": {"fermee": True}})
        raise HTTPException(401, "Session expirée après 30 minutes d'inactivité : reconnectez-vous.")
    # Session glissante : chaque appel repousse l'expiration
    await db.espace_client_sessions.update_one({"sid_hash": sid_hash}, {"$set": {
        "derniere_activite": maintenant.isoformat(),
        "expire_le": maintenant + timedelta(minutes=s.espace_client_session_minutes)}})
    return SessionClient(sid_hash, session["boutique_id"], session["client_id"])


@router.post("/deconnexion")
async def deconnexion(response: Response, session: SessionClient = Depends(session_client)):
    await db.espace_client_sessions.update_one({"sid_hash": session.sid_hash}, {"$set": {"fermee": True}})
    _effacer_cookie(response)
    return {"ok": True}


# ---------------------------------------------------------------------------
# 4. Contenu de l'espace (lecture seule, cloisonné au client de la session)
# ---------------------------------------------------------------------------
# Documents visibles du client : factures validées (ou annulées, pour information)
# et proformas émises (en cours ou acceptées). Les brouillons de facture restent internes.
def _filtre_documents(client_id: str) -> dict:
    return {"client_id": client_id, "$or": [
        {"type_document": "FAC", "statut": {"$in": ["VALIDE", "ANNULE"]}},
        {"type_document": "PRO", "statut": {"$in": ["BROUILLON", "VALIDE"]}},
    ]}


def _document_resume(d: dict) -> dict:
    from services import statut_paiement

    paiement = statut_paiement(d) if d.get("statut") != "ANNULE" else {"total_regle": 0, "reste_a_payer": 0,
                                                                         "statut_paiement": "—"}
    return {**{k: d.get(k) for k in ("id", "type_document", "numero", "date", "date_echeance", "objet", "statut",
                                     "total_ttc")},
            **paiement, "convertie": bool(d.get("facture_generee_id"))}


@router.get("/moi")
async def moi(session: SessionClient = Depends(session_client)):
    """Client connecté, boutique et résumé (total facturé, réglé, reste à payer)."""
    b = await db.boutiques.find_one({"id": session.boutique_id}, SANS_ID) or {}
    client = await session.tdb.clients.find_one({"id": session.client_id}) or {}
    docs = await session.tdb.documents.find(_filtre_documents(session.client_id)).to_list(2000)
    factures = [_document_resume(d) for d in docs if d["type_document"] == "FAC" and d["statut"] == "VALIDE"]
    return {"client": {"nom": client.get("nom", "")}, "boutique": boutique_minimale(b),
            "resume": {"nb_factures": len(factures),
                       "nb_proformas": sum(1 for d in docs if d["type_document"] == "PRO"),
                       "total_facture": sum(int(f.get("total_ttc") or 0) for f in factures),
                       "total_regle": sum(f["total_regle"] for f in factures),
                       "reste_a_payer": sum(f["reste_a_payer"] for f in factures)}}


@router.get("/documents")
async def mes_documents(session: SessionClient = Depends(session_client)):
    docs = await session.tdb.documents.find(_filtre_documents(session.client_id), {"_id": 0, "lignes": 0}) \
        .sort([("date", -1), ("created_at", -1)]).to_list(1000)
    return [_document_resume(d) for d in docs]


@router.get("/documents/{document_id}")
async def mon_document(document_id: str, session: SessionClient = Depends(session_client)):
    """Document complet (lignes, totaux) pour l'affichage et l'impression / PDF."""
    from routes.documents import enrichir

    d = await session.tdb.documents.find_one({"id": document_id, **_filtre_documents(session.client_id)})
    if not d:
        raise HTTPException(404, "Document introuvable")
    b = await db.boutiques.find_one({"id": session.boutique_id}, SANS_ID) or {}
    doc = enrichir(d, b)
    # Rien d'interne : auteur de la saisie, notes de règlement
    doc.pop("cree_par", None)
    doc["reglements"] = [{"date": r.get("date"), "montant": r.get("montant"),
                          "mode": LIBELLES_MODE.get(r.get("mode"), r.get("mode"))} for r in d.get("reglements", [])]
    doc["modifiable"] = False
    import pispi_connecteur
    return {"document": doc, "boutique": {k: b.get(k) for k in CHAMPS_BOUTIQUE_FACTURE},
            # Bloc « Payer par PI-SPI » de la boutique (QR de sa banque), s'il est actif
            "pispi": pispi_connecteur.bloc_impression(b)}


@router.get("/reglements")
async def mes_reglements(session: SessionClient = Depends(session_client)):
    """Règlements enregistrés sur les factures validées du client."""
    docs = await session.tdb.documents.find({"client_id": session.client_id, "type_document": "FAC",
                                             "statut": "VALIDE"}).to_list(2000)
    lignes = [{"date": r.get("date"), "montant": r.get("montant"), "mode": LIBELLES_MODE.get(r.get("mode"), r.get("mode")),
               "document_id": d["id"], "numero": d.get("numero")}
              for d in docs for r in d.get("reglements", [])]
    return sorted(lignes, key=lambda r: r.get("date") or "", reverse=True)


@router.get("/sav")
async def mon_sav(session: SessionClient = Depends(session_client)):
    """Suivi SAV : dossiers de réparation (téléphones) et fiches de maintenance des équipements."""
    from routes.maintenance import avec_libelles
    from routes.maintenance_equipements import LIBELLES_STATUT

    dossiers = await session.tdb.dossiers.find({"client_id": session.client_id}).sort("date_depot", -1).to_list(500)
    fiches = await session.tdb.maintenance_fiches.find({"client_id": session.client_id}).sort("date_reception", -1).to_list(500)
    return {
        "dossiers": [{k: x.get(k) for k in ("id", "numero", "marque", "modele", "statut", "statut_libelle", "etape",
                                            "date_depot", "date_prevue", "date_restitution", "diagnostic",
                                            "devis_montant", "sous_garantie")}
                     for x in (avec_libelles(d) for d in dossiers)],
        "maintenance": [{"id": f.get("id"), "numero": f.get("numero"), "type_materiel": f.get("type_materiel"),
                         "marque_modele": f.get("marque_modele"), "statut": f.get("statut"),
                         "statut_libelle": LIBELLES_STATUT.get(f.get("statut"), f.get("statut")),
                         "date_reception": f.get("date_reception"), "date_sortie": f.get("date_sortie"),
                         "diagnostic": f.get("diagnostic")} for f in fiches],
    }
