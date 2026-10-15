"""Lot B — inscription LIBRE d'un commerçant et connexion par téléphone + code WhatsApp.

1) INSCRIPTION (page publique « Créer ma boutique », sans être connecté) :
   a. POST /api/inscription/demander-code : le commerçant a rempli tout le formulaire
      (téléphone WhatsApp, prénom, nom, nom de la boutique, ville, quartier / adresse,
      position GPS facultative, secteur d'activité). Le formulaire est CONTRÔLÉ, le
      numéro doit être libre, puis un code à 6 chiffres part par WhatsApp.
      RIEN n'est créé à cette étape (seule l'empreinte du code est enregistrée).
   b. POST /api/inscription/confirmer : même formulaire + le code reçu. Code bon ->
      création de la boutique (EN ATTENTE DE VALIDATION, origine « inscription »,
      secteur choisi) et du compte DG du commerçant (identifié par son téléphone,
      e-mail facultatif, SANS mot de passe), puis ouverture immédiate de la session.

2) CONNEXION PAR WHATSAPP (page de connexion, onglet « Avec WhatsApp ») :
   a. POST /api/auth/whatsapp/demander-code : numéro de téléphone -> code envoyé si un
      compte du personnel d'une boutique porte ce numéro. Réponse IDENTIQUE que le
      compte existe ou non (on ne révèle rien) ; l'envoi part après la réponse.
   b. POST /api/auth/whatsapp/connexion : numéro + code -> session (mêmes contrôles
      que la connexion par mot de passe). Le super-administrateur n'y a pas accès.

Anti-abus : limites d'envoi (1 par minute, 5 par heure, par numéro ET par adresse IP),
5 essais par code, blocage de l'adresse IP après 20 mauvais codes (15 minutes),
adresses IP bloquées par le super-administrateur refusées, maintenance respectée.
Règles des codes : voir inscription_otp.py.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

import blocages_acces
import identifiants
import inscription_otp as otp
import maintenance_plateforme
from acces import ip_client
from config import get_settings
from db import SANS_ID, db
from routes.auth import ouvrir_session_personnel
from routes.espace_client import ip_masquee, telephone_masque
from routes.plateforme import enregistrer_boutique
from routes.webhooks import DOMAINES_JETABLES, NOMS_INTERDITS
from utils import now_iso, slugifier, telephone_e164

logger = logging.getLogger("adlyn.inscription")

public = APIRouter(prefix="/inscription", tags=["Inscription libre des commerçants (public)"])
connexion = APIRouter(prefix="/auth/whatsapp", tags=["Connexion par code WhatsApp"])

# Messages communs (aucune information sensible)
TROP_DE_DEMANDES = "Patientez avant de redemander un code (1 par minute et 5 par heure au maximum)."
TROP_D_ESSAIS = "Trop de codes incorrects depuis cette connexion : réessayez dans 15 minutes."
MESSAGE_CONNEXION = ("Si ce numéro correspond à un compte adLyn, un code à 6 chiffres vient de lui être envoyé "
                     "par WhatsApp. Il est valable 10 minutes.")
ECHEC_ENVOI = ("Le code n'a pas pu être envoyé. Vérifiez que ce numéro utilise WhatsApp, "
               "puis réessayez dans quelques minutes.")


# ---------------------------------------------------------------------------
# Petits outils
# ---------------------------------------------------------------------------
def _numero(texte: str) -> str:
    """Numéro saisi -> format international E.164 (« +22670123456 »), ou erreur 400."""
    tel = telephone_e164(texte)
    if not tel:
        raise HTTPException(400, "Numéro de téléphone invalide (ex. 70 12 34 56 ou +226 70 12 34 56)")
    return tel


def _cles_limite(prefixe: str, tel: str, ip: str) -> list[str]:
    """Compteurs d'envoi : par numéro (propre au parcours) et par adresse IP (commun)."""
    return [f"{prefixe}-tel|{tel}", f"otp-ip|{ip}"]


async def _refuser_si_ip_bloquee(ip: str) -> None:
    if await identifiants.est_bloque(f"otp-essais-ip|{ip}"):
        raise HTTPException(429, TROP_D_ESSAIS)


async def _noter_mauvais_code(ip: str, resultat: str) -> None:
    """Mauvais code : compté pour l'adresse IP (blocage au-delà de 20 en 15 minutes), puis 400."""
    await identifiants.noter_echec(f"otp-essais-ip|{ip}", seuil=otp.MAX_ESSAIS_IP)
    raise HTTPException(400, {"code": f"code_{resultat.lower()}", "message": otp.message_erreur_code(resultat)})


def _variantes_numero(tel: str) -> list[str]:
    """Écritures possibles d'un même numéro dans les fiches boutiques (champ dg_telephone,
    normalisé sans espaces mais pas toujours en E.164) : +22670…, 22670…, 0022670…, 70…"""
    chiffres = tel.lstrip("+")
    variantes = {tel, chiffres, "00" + chiffres}
    if chiffres.startswith("226") and len(chiffres) == 11:
        variantes.add(chiffres[3:])  # numéro local burkinabè (8 chiffres)
    return sorted(variantes)


async def _numero_deja_inscrit(tel: str) -> Optional[dict]:
    """Détail de l'erreur 409 si ce numéro sert déjà à un compte adLyn ou au DG d'une
    boutique ; None s'il est libre. Le commerçant est invité à se connecter."""
    compte = await db.users.find_one({"telephone": tel}, {"_id": 0, "role": 1})
    if compte and compte.get("role") == "dg":
        return {"code": "numero_deja_inscrit",
                "message": "Ce numéro a déjà une boutique sur adLyn : connectez-vous avec WhatsApp."}
    if compte:
        return {"code": "numero_deja_inscrit",
                "message": "Ce numéro est déjà utilisé par un compte adLyn : connectez-vous avec WhatsApp."}
    if await db.boutiques.find_one({"dg_telephone": {"$in": _variantes_numero(tel)}}, {"_id": 0, "id": 1}):
        return {"code": "numero_deja_inscrit",
                "message": "Ce numéro a déjà une boutique sur adLyn : connectez-vous avec votre ID boutique "
                           "et votre mot de passe."}
    return None


# ---------------------------------------------------------------------------
# 1) Inscription libre
# ---------------------------------------------------------------------------
class Inscription(BaseModel):
    """Formulaire « Créer ma boutique » (champs inconnus refusés : erreurs d'intégration visibles)."""
    model_config = {"extra": "forbid"}

    telephone: str = Field(..., min_length=8, max_length=30)  # numéro WhatsApp du commerçant
    prenom: str = Field(..., min_length=2, max_length=60)
    nom: str = Field(..., min_length=2, max_length=60)  # nom de famille du commerçant
    nom_boutique: str = Field(..., min_length=3, max_length=120)
    pays: str = Field("Burkina Faso", min_length=2, max_length=60)
    ville: str = Field(..., min_length=2, max_length=80)
    adresse: str = Field("", max_length=500)  # quartier / adresse
    # Géolocalisation FACULTATIVE (bouton « Utiliser ma position »)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    secteur: str = Field(..., min_length=1, max_length=40)  # secteur d'activité principal
    email: Optional[EmailStr] = None  # facultatif
    accepte_conditions: bool = False
    # Lot 55 : case FACULTATIVE « J'accepte de recevoir les nouveautés et offres d'adLyn sur WhatsApp » (jamais cochée d'office)
    accepte_whatsapp: bool = False


class ConfirmationInscription(Inscription):
    code: str = Field(..., max_length=12)


def _controler_formulaire(f: Inscription) -> None:
    """Contrôles de vraisemblance (mêmes principes que le webhook de création) -> 400 lisible."""
    if not f.accepte_conditions:
        raise HTTPException(400, "Acceptez les conditions d'utilisation d'adLyn pour continuer")
    for libelle, valeur in (("Prénom", f.prenom), ("Nom", f.nom)):
        if len(re.sub(r"[^a-zA-Z]", "", slugifier(valeur))) < 2:
            raise HTTPException(400, f"{libelle} non valable")
    nom_simple = slugifier(f.nom_boutique)
    if len(re.sub(r"[^a-zA-Z]", "", nom_simple)) < 3:
        raise HTTPException(400, "Nom de boutique non valable (au moins 3 lettres)")
    if nom_simple.replace("-", "") in NOMS_INTERDITS or re.search(r"(.)\1{3,}", f.nom_boutique.lower()):
        raise HTTPException(400, "Nom de boutique non valable")
    if re.search(r"https?://|www\.|<|>", " ".join((f.prenom, f.nom, f.nom_boutique, f.ville, f.adresse))):
        raise HTTPException(400, "Les liens et balises ne sont pas acceptés")
    if (f.latitude is None) != (f.longitude is None):
        raise HTTPException(400, "Position incomplète : latitude et longitude vont ensemble")
    if f.email and str(f.email).split("@")[-1].lower() in DOMAINES_JETABLES:
        raise HTTPException(400, "Adresse e-mail jetable refusée")


async def _controler_inscription(f: Inscription, request: Request) -> tuple[str, str, str]:
    """Contrôles communs aux deux étapes -> (numéro E.164, code du secteur, adresse IP)."""
    import secteurs as service_secteurs

    await maintenance_plateforme.refuser_si_maintenance()
    tel = _numero(f.telephone)
    # Adresse IP bloquée pour tous les comptes par le super-administrateur (onglet « Usage »)
    await blocages_acces.controler_creation(request, identifiant=identifiants.masquer(tel))
    ip = ip_client(request)
    await _refuser_si_ip_bloquee(ip)
    _controler_formulaire(f)
    code_secteur = await service_secteurs.code_valide(f.secteur)
    deja = await _numero_deja_inscrit(tel)
    if deja:
        raise HTTPException(409, deja)
    if f.email and await db.users.find_one({"email": str(f.email).lower()}, {"_id": 0, "id": 1}):
        raise HTTPException(409, "Un compte adLyn existe déjà avec cet e-mail : connectez-vous ou laissez le champ vide.")
    return tel, code_secteur, ip


@public.post("/demander-code")
async def demander_code_inscription(payload: Inscription, request: Request):
    """Étape 1 : formulaire contrôlé, numéro libre -> code envoyé par WhatsApp. Rien n'est créé."""
    tel, _, ip = await _controler_inscription(payload, request)
    cles = _cles_limite("otp-insc", tel, ip)
    if await identifiants.limite_atteinte(cles):
        raise HTTPException(429, TROP_DE_DEMANDES)
    await identifiants.noter_envoi(cles)
    code = await otp.creer_code(tel, otp.INSCRIPTION)
    envoi = await otp.envoyer_code(tel, otp.INSCRIPTION, code)
    if envoi["statut"] != "ENVOYE":
        # Le code ne sert à rien s'il n'est pas parti : on l'efface
        await otp.annuler_code(tel, otp.INSCRIPTION)
        logger.warning("inscription : code non envoyé (%s)", envoi.get("erreur", "")[:200])
        raise HTTPException(502, ECHEC_ENVOI)
    return {"ok": True, "telephone_masque": telephone_masque(tel),
            "canal": "SMS" if envoi["canal"] == "SMS" else "WhatsApp",
            "validite_minutes": int(otp.CODE_VALIDITE.total_seconds() // 60),
            "renvoi_dans_secondes": int(identifiants.DELAI_ENTRE_ENVOIS.total_seconds())}


@public.post("/confirmer", status_code=201)
async def confirmer_inscription(payload: ConfirmationInscription, request: Request, response: Response,
                                taches: BackgroundTasks):
    """Étape 2 : code bon -> boutique EN ATTENTE DE VALIDATION + compte DG + session ouverte."""
    tel, code_secteur, ip = await _controler_inscription(payload, request)
    resultat = await otp.verifier_code(tel, otp.INSCRIPTION, payload.code)
    if resultat != otp.CODE_BON:
        await _noter_mauvais_code(ip, resultat)
    await identifiants.effacer_echecs(f"otp-essais-ip|{ip}")

    # Création (même fonction que le super-admin, le webhook et le parrainage)
    prenom, nom = payload.prenom.strip(), payload.nom.strip()
    # Lot 55 : consentement WhatsApp donné par la personne elle-même (case facultative) : date, moyen et adresse IP gardés
    # comme preuve sur la fiche du DG. Case non cochée : aucune trace (« pas de réponse » ≠ « refus »).
    consentement = ({"accepte_whatsapp": True, "accepte_whatsapp_le": now_iso(), "accepte_whatsapp_moyen": "inscription",
                     "accepte_whatsapp_ip": ip} if payload.accepte_whatsapp else {})
    donnees = {
        "nom": payload.nom_boutique.strip(), "telephone": tel, "email": str(payload.email or ""),
        "pays": payload.pays.strip(), "ville": payload.ville.strip(), "adresse": payload.adresse.strip(),
        "latitude": payload.latitude, "longitude": payload.longitude,
        "dg_nom": f"{prenom} {nom}", "dg_telephone": tel, "secteur": code_secteur,
    }
    boutique, dg, _ = await enregistrer_boutique(
        donnees, dg_email=str(payload.email) if payload.email else None, dg_mot_de_passe=None,
        validee=False, origine="inscription", dg_telephone=tel,
        # Prénom et nom séparés : serviront au lot C (comparaison avec la pièce d'identité)
        dg_complements={"prenom": prenom, "nom_famille": nom, **consentement})
    # Suivi de l'inscription + Paramètres (dont le dossier KYC) et Abonnement toujours
    # accessibles au DG, quel que soit le secteur choisi
    suivi = {"date": now_iso(), "telephone_verifie": tel, "canal_code": "WHATSAPP",
             "dg_prenom": prenom, "dg_nom_famille": nom, "ip": ip_masquee(ip),
             "position_gps": payload.latitude is not None}
    await db.boutiques.update_one({"id": boutique["id"]}, {"$set": {
        "inscription": suivi, "options_sidebar.parametres": True, "options_sidebar.abonnement": True}})
    await identifiants.journaliser("COMPTE_CREE", cible=dg, request=request, canal="WHATSAPP", statut="INSCRIPTION",
                                   details={"origine": "inscription en ligne"})

    # Prévenir l'équipe adLyn (e-mail du rapport), après la réponse
    s = get_settings()
    if s.rapport_email:
        async def _prevenir_equipe():
            import envois_plateforme as envois
            try:
                await envois.envoyer_email(
                    f"[adLyn] Nouvelle inscription en ligne à valider : {boutique['nom']}",
                    "\n".join([f"Boutique : {boutique['nom']} ({boutique.get('ville', '')}, {boutique.get('pays', '')})",
                               f"Secteur : {code_secteur}",
                               f"DG : {dg['nom']} — {identifiants.masquer(tel)} (numéro vérifié par code WhatsApp)", "",
                               f"À valider dans l'administration : {s.public_site_url}/plateforme"]),
                    s.rapport_email)
            except Exception:  # noqa: BLE001 — un e-mail en échec ne doit rien casser
                logger.warning("inscription : e-mail à l'équipe impossible")
        taches.add_task(_prevenir_equipe)

    # Ouverture immédiate de la session du commerçant
    user = await db.users.find_one({"id": dg["id"]}, SANS_ID)
    session = await ouvrir_session_personnel(user, request, response, methode="inscription",
                                             identifiant=identifiants.masquer(tel))
    if isinstance(session, dict):
        session["inscription"] = {"code_boutique": boutique["code_marchand"], "statut": "EN_ATTENTE_VALIDATION"}
    return session


# ---------------------------------------------------------------------------
# 2) Connexion par téléphone + code WhatsApp
# ---------------------------------------------------------------------------
class DemandeCodeConnexion(BaseModel):
    telephone: str = Field(..., min_length=8, max_length=30)


class ConnexionWhatsapp(DemandeCodeConnexion):
    code: str = Field(..., max_length=12)


async def _compte_du_numero(tel: str) -> Optional[dict]:
    """Compte du PERSONNEL d'une boutique qui porte ce numéro (actif) ; jamais le super-admin."""
    user = await db.users.find_one({"telephone": tel}, SANS_ID)
    if not user or user.get("role") == "super_admin" or not user.get("actif", True) or not user.get("boutique_id"):
        return None
    return user


@connexion.post("/demander-code")
async def demander_code_connexion(payload: DemandeCodeConnexion, request: Request, taches: BackgroundTasks):
    """Code de connexion envoyé par WhatsApp. Réponse identique, que le compte existe ou non."""
    await maintenance_plateforme.refuser_si_maintenance()
    tel = _numero(payload.telephone)
    ip = ip_client(request)
    await _refuser_si_ip_bloquee(ip)
    cles = _cles_limite("otp-cnx", tel, ip)
    if await identifiants.limite_atteinte(cles):
        raise HTTPException(429, TROP_DE_DEMANDES)
    await identifiants.noter_envoi(cles)
    reponse = {"ok": True, "message": MESSAGE_CONNEXION, "telephone_masque": telephone_masque(tel),
               "validite_minutes": int(otp.CODE_VALIDITE.total_seconds() // 60),
               "renvoi_dans_secondes": int(identifiants.DELAI_ENTRE_ENVOIS.total_seconds())}
    user = await _compte_du_numero(tel)
    if not user:
        return reponse
    code = await otp.creer_code(tel, otp.CONNEXION)

    async def _envoyer():
        # Après la réponse : le temps de réponse ne trahit pas l'existence du compte
        envoi = await otp.envoyer_code(tel, otp.CONNEXION, code)
        if envoi["statut"] != "ENVOYE":
            logger.warning("connexion WhatsApp : code non envoyé (%s)", (envoi.get("erreur") or "")[:200])

    taches.add_task(_envoyer)
    return reponse


@connexion.post("/connexion")
async def connexion_whatsapp(payload: ConnexionWhatsapp, request: Request, response: Response):
    """Numéro + code reçu -> session ouverte (mêmes contrôles que la connexion par mot de passe)."""
    await maintenance_plateforme.refuser_si_maintenance()
    tel = _numero(payload.telephone)
    ip = ip_client(request)
    await _refuser_si_ip_bloquee(ip)
    resultat = await otp.verifier_code(tel, otp.CONNEXION, payload.code)
    user = await _compte_du_numero(tel) if resultat == otp.CODE_BON else None
    if not user:
        # Mauvais code, code expiré, ou compte devenu introuvable / désactivé entre-temps
        await _noter_mauvais_code(ip, resultat if resultat != otp.CODE_BON else otp.CODE_EXPIRE)
    await identifiants.effacer_echecs(f"otp-essais-ip|{ip}")
    return await ouvrir_session_personnel(user, request, response, methode="whatsapp",
                                          identifiant=identifiants.masquer(tel))
