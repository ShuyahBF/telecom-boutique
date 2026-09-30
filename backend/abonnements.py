"""Abonnements des boutiques à la plateforme adLyn (modèle SaaS).

Cycle de vie d'une boutique :
  1. ESSAI : 14 jours de démo complète à partir de sa création ;
  2. puis ABONNEMENT payé pour une FORMULE (1 mois, 3 mois, 1 an...) :
     chaque paiement repousse l'échéance du nombre de mois de la formule ;
  3. sans paiement à l'échéance, la boutique passe EN RETARD : elle apparaît
     dans la liste des retards du super-administrateur (jours de retard et
     montant attendu), qui choisit celles dont il SUSPEND l'accès ;
  4. un paiement reçu réactive automatiquement une boutique suspendue pour
     impayé (une suspension décidée pour un autre motif reste en place).

Rappels : WhatsApp (SMS en repli) + e-mail au DG, 3 jours avant l'échéance
puis chaque jour tant que l'abonnement n'est pas renouvelé.

Dates : chaînes « AAAA-MM-JJ » dans le fuseau de la plateforme. L'échéance
est le DERNIER jour couvert (l'accès est payé jusqu'à ce jour inclus).
"""
from __future__ import annotations

import asyncio
import calendar
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError

from config import get_settings
from db import SANS_ID, db
from utils import new_id, now_iso

logger = logging.getLogger(__name__)

# Formules proposées au premier démarrage (modifiables dans /plateforme/abonnements).
# Tarifs fixés par le propriétaire de la plateforme (modifiables ensuite dans l'écran « Formules »)
FORMULES_PAR_DEFAUT = [
    {"code": "MENSUEL", "libelle": "Mensuel (30 jours)", "mois": 1, "montant": 5000, "ordre": 1},
    {"code": "TRIMESTRIEL", "libelle": "3 mois", "mois": 3, "montant": 14000, "ordre": 2},
    {"code": "SEMESTRIEL", "libelle": "6 mois", "mois": 6, "montant": 27000, "ordre": 3},
    {"code": "ANNUEL", "libelle": "1 an", "mois": 12, "montant": 50000, "ordre": 4},
]
FORMULE_DEFAUT = "MENSUEL"

STATUTS = {
    "ESSAI": "Période d'essai",
    "ACTIF": "Abonnement actif",
    "A_RENOUVELER": "À renouveler bientôt",
    "EN_RETARD": "En retard de paiement",
    "SUSPENDU": "Accès suspendu",
}
MODES_PAIEMENT = {"PAWAPAY": "Mobile Money en ligne (PawaPay)", "MOBILE_MONEY": "Mobile Money (transfert)",
                  "ESPECES": "Espèces", "VIREMENT": "Virement", "CHEQUE": "Chèque", "OFFERT": "Geste commercial",
                  "BONUS_PARRAINAGE": "Bonus de parrainage"}


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
def aujourd_hui() -> date:
    return datetime.now(ZoneInfo(get_settings().fuseau_horaire)).date()


def ajouter_mois(d: date, mois: int) -> date:
    """31/01 + 1 mois -> 28 (ou 29)/02 : le jour est ramené à la fin du mois si besoin."""
    total = d.month - 1 + mois
    annee, mois_cible = d.year + total // 12, total % 12 + 1
    return date(annee, mois_cible, min(d.day, calendar.monthrange(annee, mois_cible)[1]))


def abonnement_initial(created_at: Optional[str]) -> dict:
    """Essai de N jours à compter de la création (date de création incluse)."""
    try:
        debut = datetime.fromisoformat(created_at).astimezone(ZoneInfo(get_settings().fuseau_horaire)).date()
    except (TypeError, ValueError):
        debut = aujourd_hui()
    fin = debut + timedelta(days=get_settings().abonnement_essai_jours - 1)
    return {"en_essai": True, "debut_essai": debut.isoformat(), "fin_essai": fin.isoformat(),
            "echeance": fin.isoformat(), "formule": FORMULE_DEFAUT, "dernier_paiement": None}


# ---------------------------------------------------------------------------
# Formules
# ---------------------------------------------------------------------------
async def initialiser() -> None:
    """Au démarrage : formules par défaut + abonnement des boutiques qui n'en ont pas encore
    (boutiques créées avant l'arrivée des abonnements : essai compté depuis leur création)."""
    if not await db.formules.count_documents({}):
        await db.formules.insert_many([{**f, "id": new_id(), "actif": True} for f in FORMULES_PAR_DEFAUT])
    async for b in db.boutiques.find({"abonnement": {"$exists": False}}, {"_id": 0, "id": 1, "created_at": 1}):
        await db.boutiques.update_one({"id": b["id"], "abonnement": {"$exists": False}},
                                      {"$set": {"abonnement": abonnement_initial(b.get("created_at"))}})


async def formules(actives_seulement: bool = True) -> list[dict]:
    filtre = {"actif": True} if actives_seulement else {}
    return await db.formules.find(filtre, SANS_ID).sort([("ordre", 1), ("mois", 1)]).to_list(50)


async def formule(code: str) -> Optional[dict]:
    return await db.formules.find_one({"code": code}, SANS_ID)


# ---------------------------------------------------------------------------
# État d'une boutique
# ---------------------------------------------------------------------------
async def etat(boutique: dict, tarifs: Optional[dict] = None) -> dict:
    """Situation de l'abonnement : statut, échéance, jours restants / de retard, montant attendu.
    `tarifs` (code -> formule) évite de relire les formules pour chaque boutique d'une liste."""
    ab = boutique.get("abonnement") or abonnement_initial(boutique.get("created_at"))
    if tarifs is None:
        tarifs = {f["code"]: f for f in await formules(False)}
    f = tarifs.get(ab.get("formule") or FORMULE_DEFAUT) or tarifs.get(FORMULE_DEFAUT) or {}
    echeance = date.fromisoformat(ab["echeance"])
    restants = (echeance - aujourd_hui()).days
    if boutique.get("actif") is False:
        statut = "SUSPENDU"
    elif restants < 0:
        statut = "EN_RETARD"
    elif ab.get("en_essai"):
        statut = "ESSAI"
    elif restants < get_settings().abonnement_rappel_jours_avant:
        statut = "A_RENOUVELER"
    else:
        statut = "ACTIF"
    return {
        **ab, "statut": statut, "statut_libelle": STATUTS[statut],
        "jours_restants": max(restants, 0), "jours_retard": max(-restants, 0),
        "formule_libelle": f.get("libelle", ""), "montant_attendu": int(f.get("montant", 0)),
        "motif_suspension": (boutique.get("suspension") or {}).get("motif") if boutique.get("actif") is False else None,
    }


# ---------------------------------------------------------------------------
# Paiement d'un abonnement (en ligne ou saisi par le super-admin)
# ---------------------------------------------------------------------------
async def enregistrer_paiement(boutique_id: str, code_formule: str, montant: int, mode: str, *,
                               reference: str = "", saisi_par: str = "", cle: Optional[str] = None,
                               date_paiement: Optional[str] = None, bonus_deduit: int = 0) -> dict:
    """Repousse l'échéance du nombre de mois de la formule, trace le paiement et,
    si la boutique était suspendue POUR IMPAYÉ, lui rend l'accès.
    `cle` : identifiant unique (ex. « pawapay-<depot> ») pour ne jamais compter deux fois un paiement."""
    f = await formule(code_formule)
    if not f:
        raise ValueError("Formule inconnue")
    boutique = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not boutique:
        raise ValueError("Boutique introuvable")
    paiement_id = cle or new_id()
    # Réservation du paiement AVANT de toucher à l'échéance (idempotence)
    try:
        await db.abonnement_paiements.insert_one({
            "_id": paiement_id, "id": paiement_id, "boutique_id": boutique_id, "boutique_nom": boutique["nom"],
            "code_marchand": boutique.get("code_marchand", ""), "formule": f["code"], "formule_libelle": f["libelle"],
            "mois": f["mois"], "montant": int(montant), "mode": mode, "reference": reference[:120],
            # Bonus de parrainage déduit du prix de la formule (montant = somme réellement payée)
            "bonus_deduit": int(bonus_deduit),
            "saisi_par": saisi_par, "date": date_paiement or aujourd_hui().isoformat(), "created_at": now_iso(),
            "statut": "EN_COURS"})
    except DuplicateKeyError:
        return await db.abonnement_paiements.find_one({"_id": paiement_id}, SANS_ID)

    ab = boutique.get("abonnement") or abonnement_initial(boutique.get("created_at"))
    ancienne = date.fromisoformat(ab["echeance"])
    suspendue_impaye = boutique.get("actif") is False and (boutique.get("suspension") or {}).get("motif") == "IMPAYE"
    # Point de départ : l'ancienne échéance (jours déjà consommés dus, essai conservé)...
    # ... sauf pour une boutique suspendue pour impayé : elle repart du jour du paiement
    depart = aujourd_hui() - timedelta(days=1) if suspendue_impaye else ancienne
    nouvelle = ajouter_mois(depart, f["mois"])
    maj = {"abonnement": {**ab, "en_essai": False, "echeance": nouvelle.isoformat(), "formule": f["code"],
                          "dernier_paiement": {"id": paiement_id, "date": aujourd_hui().isoformat(),
                                               "montant": int(montant), "formule": f["code"]}}}
    if suspendue_impaye:
        maj.update({"actif": True, "suspension": None})
    await db.boutiques.update_one({"id": boutique_id}, {"$set": maj})
    await db.abonnement_paiements.update_one({"_id": paiement_id}, {"$set": {
        "statut": "VALIDE", "ancienne_echeance": ancienne.isoformat(), "nouvelle_echeance": nouvelle.isoformat(),
        "reactivee": suspendue_impaye}})
    return await db.abonnement_paiements.find_one({"_id": paiement_id}, SANS_ID)


async def suspendre(boutique_id: str, motif: str, par: str) -> bool:
    """Coupe l'accès (back-office ET vitrine). motif : IMPAYE ou MANUEL."""
    res = await db.boutiques.update_one({"id": boutique_id}, {"$set": {
        "actif": False, "suspension": {"motif": motif, "date": now_iso(), "par": par}}})
    return bool(res.matched_count)


# ---------------------------------------------------------------------------
# Rappels (WhatsApp, SMS en repli, e-mail) : chaque jour à l'heure prévue
# ---------------------------------------------------------------------------
def _texte_echeance(e: dict) -> str:
    fin = date.fromisoformat(e["echeance"]).strftime("%d/%m/%Y")
    if e["jours_retard"]:
        return f"a expiré le {fin} ({e['jours_retard']} jour(s) de retard)"
    if e["jours_restants"] == 0:
        return f"expire aujourd'hui ({fin})"
    return f"expire le {fin} (dans {e['jours_restants']} jour(s))"


async def envoyer_rappels(declencheur: str = "planification") -> list[dict]:
    """Un rappel par boutique et par jour au plus (verrou en base), pour les
    boutiques dont l'échéance est dans N jours ou moins, ou dépassée."""
    import envois_plateforme as envois

    s = get_settings()
    tarifs = {f["code"]: f for f in await formules(False)}
    jour = aujourd_hui().isoformat()
    resultats = []
    async for b in db.boutiques.find({"test": {"$ne": True}}, SANS_ID):  # jamais les boutiques internes
        e = await etat(b, tarifs)
        a_rappeler = (e["jours_retard"] > 0 and e["jours_retard"] <= s.abonnement_rappel_retard_max_jours) \
            or (e["jours_retard"] == 0 and e["jours_restants"] <= s.abonnement_rappel_jours_avant)
        if not a_rappeler:
            continue
        try:  # un seul rappel par boutique et par jour, même avec plusieurs serveurs
            await db.abonnement_rappels.insert_one({"_id": f"{b['id']}-{jour}", "date": now_iso()})
        except DuplicateKeyError:
            continue
        dg = await db.users.find_one({"boutique_id": b["id"], "role": "dg", "actif": True}, SANS_ID) or {}
        telephone = b.get("dg_telephone") or b.get("telephone", "")
        quoi = "Votre période d'essai adLyn" if e.get("en_essai") else "Votre abonnement adLyn"
        montant = f"{e['montant_attendu']:,} FCFA".replace(",", " ")
        lien = f"{s.public_site_url}/gestion/abonnement"
        texte = (f"{quoi} pour « {b['nom']} » {_texte_echeance(e)}. Montant à régler : {montant} "
                 f"({e['formule_libelle']}). Payez en ligne : {lien}")
        wa_statut, wa_erreur = await envois.envoyer_whatsapp(
            telephone, [b["nom"], _texte_echeance(e), montant], texte)
        sms_statut, sms_erreur = ("NON_ENVOYE", "")
        if wa_statut != "ENVOYE":  # repli SMS si WhatsApp n'a pas pu partir
            sms_statut, sms_erreur = await envois.envoyer_sms(telephone, texte)
        email_statut, email_erreur = await envois.envoyer_email(
            f"[adLyn] {quoi} {_texte_echeance(e)}", f"Bonjour {dg.get('nom', '')},\n\n{texte}\n\nL'équipe adLyn",
            dg.get("email", ""))
        rappel = {"id": new_id(), "date": now_iso(), "jour": jour, "declencheur": declencheur,
                  "boutique_id": b["id"], "boutique_nom": b["nom"], "code_marchand": b.get("code_marchand", ""),
                  "statut_abonnement": e["statut"], "jours_retard": e["jours_retard"],
                  "jours_restants": e["jours_restants"], "montant": e["montant_attendu"], "telephone": telephone,
                  "whatsapp": wa_statut, "whatsapp_erreur": wa_erreur, "sms": sms_statut, "sms_erreur": sms_erreur,
                  "email": email_statut, "email_erreur": email_erreur}
        await db.abonnement_rappels_journal.insert_one(rappel.copy())
        resultats.append(rappel)
    return resultats


def prochain_rappel(maintenant: Optional[datetime] = None) -> datetime:
    s = get_settings()
    tz = ZoneInfo(s.fuseau_horaire)
    maintenant = maintenant or datetime.now(tz)
    cible = maintenant.replace(hour=s.abonnement_rappel_heure, minute=0, second=0, microsecond=0)
    return cible if cible > maintenant else cible + timedelta(days=1)


async def boucle_rappels() -> None:
    """Démarrée avec le serveur : envoi des rappels chaque jour à l'heure prévue (9h par défaut)."""
    tz = ZoneInfo(get_settings().fuseau_horaire)
    while True:
        cible = prochain_rappel()
        await asyncio.sleep(max((cible - datetime.now(tz)).total_seconds(), 1))
        try:
            await envoyer_rappels()
        except Exception:  # noqa: BLE001 — une erreur ponctuelle n'arrête jamais la boucle
            logger.exception("Erreur pendant l'envoi des rappels d'abonnement")
