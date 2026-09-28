"""PawaPay — paiement Mobile Money des commandes du portail.

Porté depuis beauthentik.net (ShuyahBF/site-meetafrican,
backend/routes/payments_pawapay.py), mêmes principes de fiabilité :
  - le paiement est enregistré EN BASE avant l'appel à PawaPay ;
  - le statut n'est JAMAIS cru sur parole : il est redemandé à PawaPay
    avant de marquer une commande comme payée (montant contrôlé) ;
  - le passage à l'état final est atomique (appliqué une seule fois) ;
  - le compte PawaPay est partagé (son URL de callback pointe vers Sawali) :
    une boucle de fond interroge donc PawaPay chaque minute pour les
    paiements en attente, en plus du webhook et de la page de retour.
Le client choisit Orange / Moov / Telecel sur la page hébergée PawaPay :
le site ne collecte jamais de code PIN.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request

from config import get_settings
from db import SANS_ID, TenantDB, db
from journal_paiements import journaliser
from utils import new_id, now_iso

router = APIRouter(prefix="/paiements", tags=["Paiements — PawaPay"])
logger = logging.getLogger(__name__)

PAWAPAY_HOSTS = {"sandbox": "https://api.sandbox.pawapay.io", "production": "https://api.pawapay.io"}
_DEVISE_PAR_PAYS = {"BFA": "XOF", "BEN": "XOF", "CIV": "XOF", "GNB": "XOF", "MLI": "XOF", "NER": "XOF",
                    "SEN": "XOF", "TGO": "XOF"}


def _token() -> Optional[str]:
    s = get_settings()
    return s.pawapay_api_token_production if s.pawapay_environment == "production" else s.pawapay_api_token_sandbox


def paiement_disponible() -> bool:
    return bool(_token())


def _base_url() -> str:
    return PAWAPAY_HOSTS.get(get_settings().pawapay_environment, PAWAPAY_HOSTS["sandbox"])


def _lisible(champ: Any) -> Optional[str]:
    """PawaPay renvoie les erreurs sous forme d'objets : on les rend affichables."""
    if champ is None:
        return None
    if isinstance(champ, str):
        return champ
    if isinstance(champ, dict):
        msg = champ.get("failureMessage") or champ.get("rejectionMessage")
        code = champ.get("failureCode") or champ.get("rejectionCode")
        return f"{code} — {msg}" if msg and code else (msg or code)
    return str(champ)[:300]


async def _ouvrir_page(paiement: Dict[str, Any], reason: str, retour: str, msisdn: str = "") -> str:
    """Partie commune à tous les paiements en ligne (commandes, abonnements) :
    enregistre le paiement EN BASE, demande la page hébergée à PawaPay et
    renvoie son adresse. `paiement` contient déjà deposit_id, montant, etc."""
    s = get_settings()
    token = _token()
    corps: Dict[str, Any] = {
        "depositId": paiement["deposit_id"], "returnUrl": retour, "country": paiement["pays"],
        "reason": reason[:50], "customerMessage": s.pawapay_customer_message[:22], "language": "FR",
        "amountDetails": {"amount": str(paiement["montant"]), "currency": paiement["devise"]},
    }
    chiffres = "".join(ch for ch in msisdn if ch.isdigit())
    if chiffres:
        corps["phoneNumber"] = chiffres
    # Métadonnées transmises à PawaPay (visibles dans leur tableau de bord et leurs rapports) :
    # PawaPay peut ainsi rattacher chaque dépôt à la boutique concernée, sans données personnelles.
    corps["metadata"] = metadonnees_pawapay(paiement)
    deposit_id = paiement["deposit_id"]
    # Enregistré AVANT l'appel : on ne perd jamais un depositId
    await db.paiements.insert_one(paiement.copy())
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"{_base_url()}/v2/paymentpage", json=corps,
                                  headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            try:
                reponse = r.json()
            except ValueError:
                reponse = {"raw": r.text[:500]}
    except httpx.HTTPError as exc:
        await db.paiements.update_one({"deposit_id": deposit_id}, {"$set": {"statut": "echec", "api_message": str(exc)[:200]}})
        await _tracer(paiement, "ECHEC", "PawaPay injoignable")
        raise HTTPException(502, "PawaPay est momentanément injoignable, réessayez") from exc
    url = (reponse or {}).get("redirectUrl")
    if not url:
        message = _lisible(reponse.get("failureReason") or reponse.get("message"))
        await db.paiements.update_one({"deposit_id": deposit_id}, {"$set": {
            "statut": "echec", "api_statut": "PAYMENT_PAGE_REJECTED", "api_message": message, "updated_at": now_iso()}})
        await _tracer(paiement, "ECHEC", message or "Page de paiement refusée")
        raise HTTPException(502, message or "PawaPay n'a pas renvoyé de page de paiement")
    await db.paiements.update_one({"deposit_id": deposit_id},
                                  {"$set": {"statut": "en_attente", "redirect_url": url, "updated_at": now_iso()}})
    return url


def metadonnees_pawapay(paiement: Dict[str, Any]) -> list:
    """Liste « clé : valeur » envoyée à PawaPay avec chaque dépôt : type de paiement,
    boutique (identifiant interne + code marchand) et pièce concernée (commande, formule, facture)."""
    champs = {
        "typePaiement": paiement.get("type") or "commande",  # commande | abonnement | facture_sms
        "boutiqueId": paiement.get("boutique_id"),
        "codeMarchand": paiement.get("code_marchand"),
        "commandeNumero": paiement.get("commande_numero"),
        "formule": paiement.get("formule"),
        "factureNumero": paiement.get("facture_numero"),
    }
    # Format PawaPay : un objet par métadonnée ; les champs vides ne sont pas envoyés
    return [{cle: str(valeur)} for cle, valeur in champs.items() if valeur]


def _nouveau_paiement(boutique_id: str, montant: int, **extra) -> Dict[str, Any]:
    """Document « paiement » initial (avant l'appel à PawaPay)."""
    s = get_settings()
    pays = s.pawapay_default_country.upper()
    return {"id": new_id(), "deposit_id": new_id(), "boutique_id": boutique_id, "montant": montant,
            "devise": _DEVISE_PAR_PAYS.get(pays, "XOF"), "pays": pays, "environnement": s.pawapay_environment,
            "statut": "initie", "api_statut": None, "api_message": None, "redirect_url": None,
            "created_at": now_iso(), "updated_at": now_iso(), **extra}


async def creer_page_paiement(boutique: dict, commande: dict, msisdn: str = "") -> str:
    """Crée la page de paiement PawaPay d'une commande et renvoie l'adresse
    vers laquelle rediriger le client."""
    if not _token():
        raise HTTPException(503, "Le paiement Mobile Money n'est pas encore configuré")
    # Double contrôle KYC (la vitrine masque déjà l'option) : pas d'encaissement pour le
    # compte d'une boutique dont le dossier d'identification n'est pas validé
    if (boutique.get("kyc") or {}).get("statut") != "VERIFIE":
        raise HTTPException(400, "Le paiement Mobile Money n'est pas disponible pour cette boutique")
    paiement = _nouveau_paiement(boutique["id"], commande["total"], type="commande", commande_id=commande["id"],
                                 commande_numero=commande["numero"], client_nom=commande["client"]["nom"],
                                 code_marchand=boutique.get("code_marchand", ""))
    retour = (f"{get_settings().public_site_url}/b/{boutique['slug']}/paiement?"
              f"depot={paiement['deposit_id']}&commande={commande['numero']}")
    url = await _ouvrir_page(paiement, f"Commande {commande['numero']} {boutique['nom']}", retour, msisdn)
    await TenantDB(boutique["id"]).commandes.update_one(
        {"id": commande["id"]}, {"$set": {"paiement.statut": "EN_ATTENTE", "paiement.deposit_id": paiement["deposit_id"]}})
    await _tracer(paiement, "EN_ATTENTE", "")
    return url


async def creer_page_abonnement(boutique: dict, formule: dict, msisdn: str = "") -> str:
    """Page PawaPay pour payer l'abonnement adLyn d'une boutique (formule choisie par le DG).
    L'argent arrive sur le compte PawaPay de la plateforme."""
    if not _token():
        raise HTTPException(503, "Le paiement Mobile Money n'est pas encore configuré")
    paiement = _nouveau_paiement(boutique["id"], int(formule["montant"]), type="abonnement",
                                 formule=formule["code"], formule_libelle=formule["libelle"],
                                 boutique_nom=boutique["nom"], code_marchand=boutique.get("code_marchand", ""))
    retour = f"{get_settings().public_site_url}/gestion/abonnement?depot={paiement['deposit_id']}"
    return await _ouvrir_page(paiement, f"Abonnement adLyn {formule['libelle']} {boutique.get('code_marchand', '')}",
                              retour, msisdn)


async def creer_page_facture_sms(boutique: dict, facture: dict, msisdn: str = "") -> str:
    """Page PawaPay pour payer une facture du service SMS (argent versé à la plateforme)."""
    if not _token():
        raise HTTPException(503, "Le paiement Mobile Money n'est pas encore configuré")
    paiement = _nouveau_paiement(boutique["id"], int(facture["montant"]), type="facture_sms",
                                 facture_id=facture["id"], facture_numero=facture["numero"], boutique_nom=boutique["nom"],
                                 code_marchand=boutique.get("code_marchand", ""))
    retour = f"{get_settings().public_site_url}/gestion/abonnement?depot={paiement['deposit_id']}"
    return await _ouvrir_page(paiement, f"Facture SMS adLyn {facture['numero']}", retour, msisdn)


async def _tracer(paiement: Dict[str, Any], statut: str, motif: str) -> None:
    """Ligne de l'historique des paiements de la boutique pour ce dépôt PawaPay.
    Les abonnements (argent versé PAR la boutique à la plateforme) n'y figurent pas :
    ils ont leur propre historique (abonnement_paiements)."""
    if paiement.get("type", "commande") != "commande":
        return
    await journaliser(paiement["boutique_id"], f"pawapay-{paiement['deposit_id']}", canal="PAWAPAY", mode="MM",
                      montant=paiement["montant"], statut=statut, motif=motif or "",
                      objet=f"Commande {paiement['commande_numero']}", reference=paiement["deposit_id"],
                      client_nom=paiement.get("client_nom", ""),
                      # XOF (code ISO utilisé par PawaPay) = FCFA : même libellé que les règlements en caisse
                      devise="FCFA" if paiement.get("devise", "XOF") == "XOF" else paiement["devise"],
                      liens={"commande_id": paiement["commande_id"]})


def _extraire_depot(corps: Any) -> Optional[Dict[str, Any]]:
    if isinstance(corps, list):
        return corps[0] if corps else None
    if isinstance(corps, dict):
        interne = corps.get("data")
        if isinstance(interne, list):
            return interne[0] if interne else None
        if isinstance(interne, dict):
            return interne
        if corps.get("depositId"):
            return corps
    return None


async def _statut_pawapay(deposit_id: str) -> Optional[Dict[str, Any]]:
    """Statut FAISANT FOI, demandé directement à PawaPay."""
    token = _token()
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{_base_url()}/v2/deposits/{deposit_id}", headers={"Authorization": f"Bearer {token}"})
        if r.status_code >= 400:
            return None
        return _extraire_depot(r.json())
    except (httpx.HTTPError, ValueError):
        return None


def _montant(depot: Dict[str, Any]) -> Optional[float]:
    for cle in ("amount", "depositedAmount", "requestedAmount"):
        if depot.get(cle) not in (None, ""):
            try:
                return float(depot[cle])
            except (TypeError, ValueError):
                return None
    details = depot.get("amountDetails") or {}
    try:
        return float(details["amount"]) if details.get("amount") not in (None, "") else None
    except (TypeError, ValueError):
        return None


async def appliquer_statut(paiement: Dict[str, Any], depot: Dict[str, Any]) -> Dict[str, Any]:
    """Point d'entrée UNIQUE (webhook, page de retour, rapprochement) : la
    commande ne peut être marquée payée ni oubliée, ni deux fois."""
    from messagerie import lien_suivi, notifier_client_en_fond

    deposit_id = paiement["deposit_id"]
    brut = (depot.get("status") or "").upper()
    final = {"COMPLETED": "paye", "FAILED": "echec", "REJECTED": "echec"}.get(brut)
    maj: Dict[str, Any] = {"api_statut": brut or None, "updated_at": now_iso()}
    message = _lisible(depot.get("failureReason") or depot.get("rejectionReason"))
    if message:
        maj["api_message"] = message
    if final == "paye":
        recu = _montant(depot)
        if recu is not None and abs(recu - float(paiement["montant"])) > 0.01:
            maj.update({"statut": "montant_incoherent", "api_message": f"Montant reçu {recu} ≠ attendu {paiement['montant']}"})
            await db.paiements.update_one({"deposit_id": deposit_id}, {"$set": maj})
            await _tracer(paiement, "ECHEC", maj["api_message"])
            return {"ok": False, "raison": "montant incohérent"}
    if not final:
        await db.paiements.update_one({"deposit_id": deposit_id}, {"$set": maj})
        return {"ok": True, "applique": False}
    maj["statut"] = final
    res = await db.paiements.update_one({"deposit_id": deposit_id, "statut": {"$nin": ["paye", "echec"]}}, {"$set": maj})
    if not res.modified_count:
        return {"ok": True, "applique": False}  # déjà traité (idempotence)

    await _tracer(paiement, "SUCCES" if final == "paye" else "ECHEC", "" if final == "paye" else (message or brut))
    if paiement.get("type") == "facture_sms":
        # Facture du service SMS payée en ligne (rétablit le service s'il était suspendu)
        if final == "paye":
            import sms_boutiques
            await sms_boutiques.payer_facture(paiement["facture_id"], "PAWAPAY", reference=deposit_id,
                                              saisi_par="PawaPay", cle=f"pawapay-{deposit_id}")
        return {"ok": True, "applique": True}
    if paiement.get("type") == "abonnement":
        # Abonnement payé en ligne : l'échéance est repoussée (une seule fois grâce à la clé)
        if final == "paye":
            import abonnements
            await abonnements.enregistrer_paiement(
                paiement["boutique_id"], paiement["formule"], int(paiement["montant"]), "PAWAPAY",
                reference=deposit_id, saisi_par="PawaPay", cle=f"pawapay-{deposit_id}")
        return {"ok": True, "applique": True}
    tdb = TenantDB(paiement["boutique_id"])
    if final == "paye":
        commande = await tdb.commandes.find_one_and_update(
            {"id": paiement["commande_id"]},
            {"$set": {"paiement.statut": "PAYEE", "paiement.montant_paye": paiement["montant"],
                      "paiement.date": now_iso(), "date_maj": now_iso()}})
        if commande and commande.get("facture_id"):
            reglement = {"id": f"mm-{deposit_id}", "montant": paiement["montant"], "mode": "MM",
                         "date": now_iso()[:10], "reference": deposit_id, "saisi_par": "PawaPay", "created_at": now_iso()}
            await tdb.documents.update_one({"id": commande["facture_id"], "reglements.id": {"$ne": reglement["id"]}},
                                           {"$push": {"reglements": reglement}})
        boutique = await db.boutiques.find_one({"id": paiement["boutique_id"]}, SANS_ID)
        if commande and boutique:
            notifier_client_en_fond(boutique, "CMD_PAYEE", commande["client"],
                                    {"commande": commande, "client": commande["client"]}, lien_suivi(boutique, "commande", commande))
    else:
        await tdb.commandes.update_one({"id": paiement["commande_id"], "paiement.statut": {"$ne": "PAYEE"}},
                                       {"$set": {"paiement.statut": "ECHEC"}})
    return {"ok": True, "applique": True}


@router.get("/{deposit_id}")
async def etat_paiement(deposit_id: str, refresh: bool = False):
    """Page de retour du portail : état du paiement (public, l'identifiant
    de dépôt étant un UUID imprévisible). refresh=true interroge PawaPay."""
    paiement = await db.paiements.find_one({"deposit_id": deposit_id}, SANS_ID)
    if not paiement:
        raise HTTPException(404, "Paiement introuvable")
    if refresh and paiement["statut"] not in ("paye", "echec"):
        depot = await _statut_pawapay(deposit_id)
        if depot:
            await appliquer_statut(paiement, depot)
        paiement = await db.paiements.find_one({"deposit_id": deposit_id}, SANS_ID)
    return {k: paiement.get(k) for k in ("deposit_id", "statut", "montant", "devise", "commande_numero", "api_message",
                                         "type", "formule_libelle")}


@router.post("/webhooks/depots/{secret}", include_in_schema=False)
async def webhook(secret: str, request: Request):
    """Notification PawaPay : le secret filtre les appels, et le statut est
    quand même redemandé à PawaPay (une notification forgée n'a aucun effet)."""
    attendu = (get_settings().pawapay_callback_secret or "").strip()
    if not attendu or not secrets.compare_digest(secret, attendu):
        raise HTTPException(403, "secret de callback invalide")
    try:
        corps = await request.json()
    except ValueError:
        raise HTTPException(400, "contenu invalide")
    deposit_id = corps.get("depositId") or corps.get("deposit_id")
    paiement = await db.paiements.find_one({"deposit_id": deposit_id}, SANS_ID) if deposit_id else None
    if not paiement:
        return {"ok": False, "raison": "paiement inconnu"}
    depot = await _statut_pawapay(deposit_id)
    if not depot:
        raise HTTPException(503, "vérification PawaPay impossible, réessayer")
    return await appliquer_statut(paiement, depot)


INTERVALLE_RAPPROCHEMENT = 60  # secondes
AGE_MAX_HEURES = 48  # au-delà, un paiement en attente est abandonné


async def rapprocher_paiements() -> int:
    """Une passe : interroge PawaPay pour chaque paiement encore en attente."""
    limite = (datetime.now(timezone.utc) - timedelta(hours=AGE_MAX_HEURES)).isoformat()
    en_attente = await db.paiements.find({"statut": "en_attente", "created_at": {"$gte": limite}}, SANS_ID).to_list(200)
    finalises = 0
    for p in en_attente:
        depot = await _statut_pawapay(p["deposit_id"])
        if depot and (await appliquer_statut(p, depot)).get("applique"):
            finalises += 1
    return finalises


async def boucle_rapprochement() -> None:
    """Démarrée avec le serveur ; une erreur ponctuelle n'arrête jamais la boucle."""
    while True:
        try:
            if _token():
                await rapprocher_paiements()
        except Exception:  # noqa: BLE001
            logger.exception("Erreur pendant le rapprochement des paiements PawaPay")
        await asyncio.sleep(INTERVALLE_RAPPROCHEMENT)
