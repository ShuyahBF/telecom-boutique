"""Identifiants de connexion du personnel : e-mail OU numéro de téléphone.

Ce module regroupe tout ce qui sert à RETROUVER, VÉRIFIER et CHANGER les
identifiants d'un compte du personnel d'une boutique :

  - lecture de ce que la personne a tapé (« jean@x.bf » ou « 70 12 34 56 ») ;
  - codes de vérification à 6 chiffres (mot de passe oublié, changement
    d'e-mail ou de téléphone) : jamais gardés en clair (seule une empreinte
    HMAC est en base), valables 10 minutes, 5 essais puis blocage 15 minutes ;
  - limites d'envoi : 1 code par minute et 5 par heure, par compte et par
    adresse IP ;
  - envoi des messages par les comptes de la PLATEFORME : WhatsApp d'abord
    (la plupart des jeunes n'ont pas d'e-mail), SMS en repli, e-mail en dernier ;
  - journal des actions (collection « journal_identifiants »), sans aucun
    secret : ni code, ni mot de passe.

Un compte a toujours AU MOINS un identifiant (e-mail ou téléphone) ; chacun
est unique sur toute la plateforme (index « unique » en base, voir db.py).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request

from config import get_settings
from db import SANS_ID, db
from utils import new_id, now_iso, telephone_e164

logger = logging.getLogger("adlyn.identifiants")

# --- Règles de sécurité des codes (valeurs demandées, à ne changer qu'ici) ---
CODE_VALIDITE = timedelta(minutes=10)  # durée de vie d'un code
MAX_ESSAIS = 5  # mauvais codes tolérés...
DUREE_BLOCAGE = timedelta(minutes=15)  # ... avant ce blocage
MAX_ESSAIS_IP = 20  # mauvais codes tolérés pour une même adresse IP (tous comptes confondus)
DELAI_ENTRE_ENVOIS = timedelta(minutes=1)  # 1 envoi par minute...
MAX_ENVOIS_HEURE = 5  # ... et 5 par heure (par compte et par adresse IP)

# Objets d'un code (un seul code actif par compte et par objet)
REINIT_MDP, CHANGEMENT_EMAIL, CHANGEMENT_TELEPHONE = "REINIT_MDP", "EMAIL", "TELEPHONE"

LIBELLES_TYPE = {"email": "adresse e-mail", "telephone": "numéro de téléphone"}

# Libellés des actions du journal (affichés au DG et à l'administrateur)
ACTIONS = {
    "CODE_DEMANDE": "Code de réinitialisation demandé",
    "CODE_DEMANDE_INCONNU": "Code demandé pour un compte inconnu",
    "CODE_ECHEC": "Code incorrect ou expiré",
    "CODE_BLOQUE": "Trop d'essais : blocage de 15 minutes",
    "MDP_REINITIALISE": "Mot de passe réinitialisé par code",
    "IDENTIFIANT_CODE_DEMANDE": "Code de vérification d'un nouvel identifiant demandé",
    "IDENTIFIANT_MODIFIE": "Identifiant de connexion modifié",
    "IDENTIFIANT_RETIRE": "Identifiant de connexion retiré",
    "MDP_PROVISOIRE_ENVOYE": "Nouveau mot de passe provisoire envoyé",
    "MDP_MODIFIE_PAR_DG": "Mot de passe provisoire saisi par le DG",
    "COMPTE_CREE": "Compte créé",
    # Fermeture des sessions sans changer le mot de passe (routes/sessions.py)
    "SESSIONS_FERMEES": "Sessions fermées sur tous les appareils",
    "SESSIONS_AUTRES_FERMEES": "Autres appareils déconnectés",
    "SESSIONS_BOUTIQUE_FERMEES": "Toutes les sessions de la boutique fermées",
}

_MOTIF_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Lecture d'un identifiant tapé par l'utilisateur
# ---------------------------------------------------------------------------
def lire_identifiant(texte: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """« Jean@X.bf » -> ("email", "jean@x.bf") ; « 70 12 34 56 » -> ("telephone", "+22670123456").
    (None, None) si ce n'est ni un e-mail ni un numéro plausible."""
    t = (texte or "").strip()
    if "@" in t:
        t = t.lower()
        return ("email", t) if _MOTIF_EMAIL.match(t) and len(t) <= 200 else (None, None)
    tel = telephone_e164(t)
    return ("telephone", tel) if tel else (None, None)


def valeur_normalisee(type_: str, texte: str) -> str:
    """Valeur d'un type imposé (e-mail OU téléphone), ou erreur 400 lisible."""
    lu_type, valeur = lire_identifiant(texte)
    if lu_type != type_ or not valeur:
        raise HTTPException(400, "Adresse e-mail invalide" if type_ == "email"
                            else "Numéro de téléphone invalide (ex. 70 12 34 56 ou +226 70 12 34 56)")
    return valeur


def masquer(valeur: Optional[str]) -> str:
    """« jean@gmail.com » -> « j***@gmail.com » ; « +22670123456 » -> « +2267*****56 »."""
    v = valeur or ""
    if "@" in v:
        nom, domaine = v.split("@", 1)
        return f"{nom[:1]}***@{domaine}"
    if len(v) > 6:
        return v[:5] + "*" * (len(v) - 7) + v[-2:]
    return "***" if v else ""


def identifiant_principal(user: dict) -> str:
    """Identifiant affiché dans les messages : l'e-mail s'il existe, sinon le téléphone."""
    return user.get("email") or user.get("telephone") or ""


async def trouver_compte(type_: Optional[str], valeur: Optional[str]) -> Optional[dict]:
    if not type_ or not valeur:
        return None
    return await db.users.find_one({type_: valeur}, SANS_ID)


async def verifier_disponible(type_: str, valeur: str, sauf_user_id: Optional[str] = None) -> None:
    """Erreur 409 si cet e-mail / ce téléphone sert déjà à un AUTRE compte."""
    autre = await db.users.find_one({type_: valeur}, {"_id": 0, "id": 1})
    if autre and autre["id"] != sauf_user_id:
        raise HTTPException(409, "Un compte existe déjà avec cet e-mail" if type_ == "email"
                            else "Un compte existe déjà avec ce numéro de téléphone")


# ---------------------------------------------------------------------------
# Codes de vérification
# ---------------------------------------------------------------------------
def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _empreinte(user_id: str, objet: str, code: str) -> str:
    """Empreinte HMAC-SHA256 du code (clé = JWT_SECRET) : la base ne contient jamais le code."""
    cle = ("adlyn-codes|" + get_settings().jwt_secret).encode()
    return hmac.new(cle, f"{user_id}|{objet}|{code}".encode(), hashlib.sha256).hexdigest()


async def creer_code(user_id: str, objet: str, valeur: str = "") -> str:
    """Nouveau code à 6 chiffres (remplace le précédent du même objet). Le code
    en clair n'est renvoyé que pour être ENVOYÉ, jamais enregistré ni journalisé."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    expire = _maintenant() + CODE_VALIDITE
    await db.codes_verification.delete_many({"user_id": user_id, "objet": objet})
    await db.codes_verification.insert_one({
        "id": new_id(), "user_id": user_id, "objet": objet, "empreinte": _empreinte(user_id, objet, code),
        "valeur": valeur, "cree_le": now_iso(), "expire_iso": expire.isoformat(),
        "expire_le": expire})  # date réelle : MongoDB efface le document à cette heure (index TTL)
    return code


async def verifier_code(user_id: str, objet: str, code: str) -> Optional[dict]:
    """Document du code s'il est bon et pas expiré (il est alors consommé), sinon None."""
    doc = await db.codes_verification.find_one({"user_id": user_id, "objet": objet}, SANS_ID)
    code = re.sub(r"\D", "", code or "")
    if not doc or doc.get("expire_iso", "") <= _maintenant().isoformat():
        return None
    if not hmac.compare_digest(doc["empreinte"], _empreinte(user_id, objet, code)):
        return None
    await db.codes_verification.delete_many({"user_id": user_id, "objet": objet})
    return doc


async def annuler_code(user_id: str, objet: str) -> None:
    await db.codes_verification.delete_many({"user_id": user_id, "objet": objet})


# ---------------------------------------------------------------------------
# Limites d'envoi (1 par minute, 5 par heure) et blocage après 5 mauvais codes
# ---------------------------------------------------------------------------
async def limite_atteinte(cles: list[str]) -> bool:
    """Vrai si l'une des clés (compte, adresse IP...) a déjà reçu un code il y a
    moins d'une minute, ou 5 dans l'heure."""
    maintenant = _maintenant()
    for cle in cles:
        if await db.limites_codes.count_documents(
                {"cle": cle, "date": {"$gte": (maintenant - DELAI_ENTRE_ENVOIS).isoformat()}}):
            return True
        if await db.limites_codes.count_documents(
                {"cle": cle, "date": {"$gte": (maintenant - timedelta(hours=1)).isoformat()}}) >= MAX_ENVOIS_HEURE:
            return True
    return False


async def noter_envoi(cles: list[str]) -> None:
    for cle in cles:
        await db.limites_codes.insert_one({"cle": cle, "date": now_iso(),
                                           "expire_le": _maintenant() + timedelta(hours=1)})


async def est_bloque(cle: str) -> bool:
    return bool(await db.blocages_codes.find_one({"cle": cle, "jusqu_au": {"$gt": now_iso()}}, SANS_ID))


async def noter_echec(cle: str, seuil: int = MAX_ESSAIS) -> bool:
    """Compte un mauvais code (ou mot de passe) ; au `seuil`-ième en 15 minutes,
    pose un blocage de 15 minutes. Renvoie True si la clé vient d'être bloquée."""
    maintenant = _maintenant()
    await db.echecs_codes.insert_one({"cle": cle, "date": maintenant.isoformat(),
                                      "expire_le": maintenant + DUREE_BLOCAGE})
    nb = await db.echecs_codes.count_documents({"cle": cle, "date": {"$gte": (maintenant - DUREE_BLOCAGE).isoformat()}})
    if nb < seuil:
        return False
    await db.blocages_codes.insert_one({"cle": cle, "jusqu_au": (maintenant + DUREE_BLOCAGE).isoformat(),
                                        "expire_le": maintenant + DUREE_BLOCAGE})
    await db.echecs_codes.delete_many({"cle": cle})
    return True


async def effacer_echecs(cle: str) -> None:
    await db.echecs_codes.delete_many({"cle": cle})


# ---------------------------------------------------------------------------
# Envoi d'un message : WhatsApp, puis SMS, puis e-mail
# ---------------------------------------------------------------------------
CANAUX = {"WHATSAPP": "WhatsApp", "SMS": "SMS", "EMAIL": "e-mail"}


async def _whatsapp(telephone: str, texte: str, code: Optional[str], infos: Optional[list[str]]) -> tuple[str, str]:
    """WhatsApp : modèle « Authentication » (WHATSAPP_CODE_TEMPLATE) qui porte le code
    (ou le mot de passe provisoire) ; à défaut, ou s'il est refusé, message texte
    (qui ne passe que si la personne a écrit au numéro depuis moins de 24 h)."""
    import envois_plateforme as envois

    s = get_settings()
    modele_code = (s.whatsapp_code_template or "").strip()
    # Un code de modèle « Authentication » : 15 caractères au plus, sans espace
    if code and modele_code and len(code) <= 15 and " " not in code:
        modele_infos = (s.whatsapp_identifiants_template or "").strip()
        if infos and modele_infos:
            # Message d'accompagnement (où et avec quoi se connecter), sans le mot de passe
            await envois.envoyer_whatsapp(telephone, infos, "", modele=modele_infos)
        composants = [{"type": "body", "parameters": [{"type": "text", "text": code}]},
                      # Bouton « Copier le code » : Meta exige d'y redonner le code
                      {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": code}]}]
        return await envois.envoyer_whatsapp(telephone, [], texte, modele=modele_code, composants=composants)
    return await envois.envoyer_whatsapp(telephone, [], texte, modele="")


async def envoyer_message(*, telephone: Optional[str] = None, email: Optional[str] = None, sujet: str, texte: str,
                          code: Optional[str] = None, infos_whatsapp: Optional[list[str]] = None,
                          boutique: Optional[dict] = None) -> dict:
    """Envoie `texte` au premier canal qui fonctionne : WhatsApp puis SMS (si un
    téléphone est donné), puis e-mail (si une adresse est donnée).
    Renvoie {"canal", "statut", "erreur", "essais": [{canal, statut, erreur}]}
    — le RÉSULTAT RÉEL, à afficher. `code` : code ou mot de passe à placer dans
    le modèle WhatsApp « Authentication »."""
    import envois_plateforme as envois

    if boutique and boutique.get("test"):
        # Boutique interne (coordonnées imaginaires) : rien ne part
        return {"canal": None, "statut": "NON_CONFIGURE", "erreur": "Boutique interne : envoi désactivé", "essais": []}
    essais: list[dict] = []

    async def _essai(canal: str, appel) -> bool:
        try:
            statut, erreur = await appel
        except Exception as exc:  # noqa: BLE001 — un fournisseur en panne ne doit rien casser
            logger.warning("Envoi %s impossible : %r", canal, exc)
            statut, erreur = "ECHEC", "Erreur inattendue du fournisseur"
        essais.append({"canal": canal, "statut": statut, "erreur": erreur})
        return statut == "ENVOYE"

    if telephone:
        if await _essai("WHATSAPP", _whatsapp(telephone, texte, code, infos_whatsapp)):
            return _resultat("WHATSAPP", essais)
        if await _essai("SMS", envois.envoyer_sms(telephone, texte)):
            return _resultat("SMS", essais)
    if email:
        if await _essai("EMAIL", envois.envoyer_email(sujet, texte, email)):
            return _resultat("EMAIL", essais)
    if not essais:
        return {"canal": None, "statut": "NON_CONFIGURE", "erreur": "Aucun téléphone ni e-mail", "essais": []}
    statut = "ECHEC" if any(e["statut"] == "ECHEC" for e in essais) else "NON_CONFIGURE"
    erreur = " ; ".join(f"{CANAUX[e['canal']]} : {e['erreur'] or e['statut']}" for e in essais)
    return {"canal": None, "statut": statut, "erreur": erreur[:500], "essais": essais}


def _resultat(canal: str, essais: list[dict]) -> dict:
    return {"canal": canal, "statut": "ENVOYE", "erreur": "", "essais": essais}


def texte_code(code: str, objet: str) -> tuple[str, str]:
    """(sujet, texte) du message qui porte un code de vérification."""
    pour = {REINIT_MDP: "pour réinitialiser votre mot de passe",
            CHANGEMENT_EMAIL: "pour confirmer votre nouvelle adresse e-mail",
            CHANGEMENT_TELEPHONE: "pour confirmer votre nouveau numéro"}[objet]
    texte = (f"adLyn : votre code {pour} est {code}. Il expire dans 10 minutes. "
             "Ne le communiquez a personne, meme a l'equipe adLyn.")
    return "[adLyn] Votre code de vérification", texte


async def envoyer_identifiants_provisoires(user: dict, boutique: dict, mot_de_passe: str) -> dict:
    """Envoie au membre son ID boutique, son identifiant et son mot de passe
    PROVISOIRE (à changer à la 1re connexion) : WhatsApp, puis SMS, puis e-mail."""
    url = get_settings().public_site_url
    identifiant = identifiant_principal(user)
    texte = (f"adLyn : bonjour {(user.get('nom') or '')[:40]}, voici vos acces a la boutique {boutique['nom'][:40]}. "
             f"ID boutique : {boutique['code_marchand']} ; identifiant : {identifiant} ; "
             f"mot de passe provisoire : {mot_de_passe} (a changer a la 1re connexion). {url}/connexion")
    return await envoyer_message(
        telephone=user.get("telephone"), email=user.get("email"), sujet=f"[adLyn] Vos accès à « {boutique['nom']} »",
        texte=texte, code=mot_de_passe, boutique=boutique,
        infos_whatsapp=[user.get("nom") or "", boutique["nom"], boutique["code_marchand"], identifiant])


async def notifier_changement(user: dict, boutique: Optional[dict], type_: str, ancien: Optional[str],
                              nouveau: Optional[str], par: str) -> list[dict]:
    """Prévient la personne, sur l'ANCIEN et sur le NOUVEAU contact, que son
    identifiant de connexion a changé (aucun secret dans le message)."""
    quoi = LIBELLES_TYPE[type_]
    if nouveau:
        texte = (f"adLyn : le {quoi} de connexion de votre compte ({user.get('nom', '')[:40]}) "
                 f"a ete modifie {par} : {masquer(nouveau)}. Si vous n'etes pas a l'origine de ce changement, "
                 "contactez le DG de votre boutique.")
    else:
        texte = (f"adLyn : le {quoi} {masquer(ancien)} a ete retire de votre compte {par}. "
                 "Si vous n'etes pas a l'origine de ce changement, contactez le DG de votre boutique.")
    sujet = "[adLyn] Identifiant de connexion modifié"
    resultats = []
    for valeur in dict.fromkeys(v for v in (ancien, nouveau) if v):  # sans doublon, ordre gardé
        cible = {"telephone": valeur} if type_ == "telephone" else {"email": valeur}
        envoi = await envoyer_message(**cible, sujet=sujet, texte=texte, boutique=boutique)
        resultats.append({"destination": masquer(valeur), "canal": envoi["canal"], "statut": envoi["statut"]})
    return resultats


# ---------------------------------------------------------------------------
# Modification des identifiants par un responsable (DG ou administrateur)
# ---------------------------------------------------------------------------
async def modifier_par_responsable(membre: dict, boutique: Optional[dict], champs: dict, *, par: dict,
                                   request: Optional[Request] = None) -> tuple[dict, list[dict]]:
    """`champs` : {"email": "..." | ""} et/ou {"telephone": "..." | ""} ("" = retirer).
    Sans code (le responsable en répond) ; la personne est prévenue sur l'ancien
    et le nouveau contact. Renvoie (fiche à jour, notifications envoyées)."""
    nouvelles: dict[str, Optional[str]] = {}
    for type_, texte in champs.items():
        nouvelles[type_] = valeur_normalisee(type_, texte) if (texte or "").strip() else None
    final = {t: nouvelles.get(t, membre.get(t)) for t in ("email", "telephone")}
    if not (final["email"] or final["telephone"]):
        raise HTTPException(400, "Le compte doit garder au moins un identifiant : e-mail ou téléphone")
    a_poser, a_retirer, changes = {}, {}, []
    for type_, valeur in nouvelles.items():
        if valeur == membre.get(type_):
            continue
        if valeur:
            await verifier_disponible(type_, valeur, sauf_user_id=membre["id"])
            a_poser.update({type_: valeur, f"{type_}_verifie": False})
        else:
            a_retirer.update({type_: "", f"{type_}_verifie": ""})
        changes.append((type_, membre.get(type_), valeur))
    if not changes:
        return membre, []
    operation: dict = {}
    if a_poser:
        operation["$set"] = a_poser
    if a_retirer:
        operation["$unset"] = a_retirer
    await _appliquer(membre["id"], operation)
    role_par = "par l'administrateur adLyn" if par.get("role") == "super_admin" else "par le DG de votre boutique"
    notifications = []
    for type_, ancien, nouveau in changes:
        notifications += await notifier_changement(membre, boutique, type_, ancien, nouveau, role_par)
        await journaliser("IDENTIFIANT_MODIFIE" if nouveau else "IDENTIFIANT_RETIRE", cible=membre, par=par,
                          request=request, details={"type": type_, "ancien": ancien or "", "nouveau": nouveau or ""})
    return await db.users.find_one({"id": membre["id"]}, SANS_ID), notifications


async def _appliquer(user_id: str, operation: dict) -> None:
    """Mise à jour d'un compte ; si deux personnes prennent le même identifiant au
    même instant, l'index unique de la base refuse la seconde (409)."""
    from pymongo.errors import DuplicateKeyError

    try:
        await db.users.update_one({"id": user_id}, operation)
    except DuplicateKeyError:
        raise HTTPException(409, "Cet identifiant vient d'être pris par un autre compte") from None


def mot_de_passe_provisoire() -> str:
    """Même format que les mots de passe provisoires des DG (10 caractères sans ambiguïté)."""
    from routes.plateforme import mot_de_passe_temporaire
    return mot_de_passe_temporaire()


# ---------------------------------------------------------------------------
# Journal des actions (sans aucun secret)
# ---------------------------------------------------------------------------
async def journaliser(action: str, *, cible: Optional[dict] = None, boutique_id: Optional[str] = None,
                      par: Optional[dict] = None, request: Optional[Request] = None, identifiant: str = "",
                      canal: Optional[str] = None, statut: str = "", details: Optional[dict] = None) -> None:
    from acces import ip_client

    cible = cible or {}
    ligne = {
        "id": new_id(), "date": now_iso(), "action": action, "libelle": ACTIONS.get(action, action),
        "boutique_id": boutique_id or cible.get("boutique_id"),
        "user_id": cible.get("id"), "user_nom": cible.get("nom", ""),
        "identifiant": masquer(identifiant) if identifiant else identifiant_principal(cible),
        "par_id": (par or {}).get("id"), "par_nom": (par or {}).get("nom", "") if par else "la personne elle-même",
        "par_role": (par or {}).get("role", ""), "ip": ip_client(request) if request else "",
        "canal": canal or "", "statut": statut, "details": details or {},
    }
    await db.journal_identifiants.insert_one(ligne.copy())
    logger.info("identifiants action=%s boutique=%s compte=%s par=%s canal=%s statut=%s", action,
                ligne["boutique_id"], ligne["user_id"] or "-", ligne["par_id"] or "-", ligne["canal"] or "-", statut or "-")


async def lire_journal(filtre: dict, limite: int = 200) -> list[dict]:
    return await db.journal_identifiants.find(filtre, SANS_ID).sort("date", -1).to_list(limite)
