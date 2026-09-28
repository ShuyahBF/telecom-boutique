"""Service SMS des boutiques (volet « communication », facturé à part).

  - CONFIGURATION par le super-administrateur, une fois par boutique :
    nom d'expéditeur OVH déclaré pour elle (ex. « FASOMOBILE »), service OVH
    dédié (facultatif, sinon celui de la plateforme), prix d'un SMS.
    La boutique ne peut pas modifier ces réglages.
  - ENVOIS : notifications automatiques aux clients (commande, réparation...)
    et SMS saisis par le personnel. Chaque envoi est journalisé (liste par contact).
  - FACTURATION : une facture par boutique et par période (mois), égale au nombre
    de SMS facturables (un long message compte plusieurs SMS) x prix unitaire.
    Générée automatiquement le 1er du mois pour le mois écoulé, ou à la demande.
  - RETARD : une facture non payée à son échéance apparaît dans la liste des
    retards ; le super-administrateur choisit les boutiques dont il SUSPEND le
    service SMS (le reste de la boutique continue de fonctionner). Le paiement
    de toutes les factures en retard rétablit le service automatiquement.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from pymongo.errors import DuplicateKeyError

from abonnements import aujourd_hui
from config import get_settings
from db import SANS_ID, db
from utils import new_id, normaliser_telephone, now_iso

logger = logging.getLogger(__name__)

# Caractères de l'alphabet GSM 7 bits (160 caractères par SMS). Un seul caractère
# hors de cette liste (ex. « ê », « ç », emoji) fait passer le message en
# Unicode : 70 caractères par SMS seulement.
_GSM = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZ"
           "ÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
_GSM_DOUBLES = set("^{}\\[~]|€")  # comptent pour 2 caractères


def nombre_sms(texte: str) -> int:
    """Nombre de SMS facturés pour ce texte (les messages longs sont découpés)."""
    if all(c in _GSM or c in _GSM_DOUBLES for c in texte):
        longueur = sum(2 if c in _GSM_DOUBLES else 1 for c in texte)
        return 1 if longueur <= 160 else -(-longueur // 153)
    return 1 if len(texte) <= 70 else -(-len(texte) // 67)


# ---------------------------------------------------------------------------
# Configuration et état du service d'une boutique
# ---------------------------------------------------------------------------
def config(boutique: dict) -> dict:
    return boutique.get("sms") or {}


def etat(boutique: dict) -> dict:
    """État lisible du service SMS (sans rien révéler de secret)."""
    c = config(boutique)
    configure = bool(c.get("expediteur"))
    suspendu = bool(c.get("suspendu"))
    if not configure:
        statut, libelle = "NON_CONFIGURE", "Service SMS non activé (à demander à adLyn)"
    elif not c.get("actif", True):
        statut, libelle = "DESACTIVE", "Service SMS désactivé"
    elif suspendu:
        statut, libelle = "SUSPENDU", "Service SMS suspendu (facture impayée)" if c.get("motif") == "IMPAYE" \
            else "Service SMS suspendu"
    else:
        statut, libelle = "ACTIF", "Service SMS actif"
    return {"statut": statut, "libelle": libelle, "expediteur": c.get("expediteur", ""),
            "prix_sms": int(c.get("prix_sms", get_settings().sms_prix_defaut)),
            "notifications_auto": c.get("notifications_auto", True), "configure_le": c.get("configure_le"),
            "motif": c.get("motif") if suspendu else None}


def peut_envoyer(boutique: dict) -> bool:
    return etat(boutique)["statut"] == "ACTIF"


# ---------------------------------------------------------------------------
# Envoi (toujours journalisé)
# ---------------------------------------------------------------------------
async def envoyer(boutique: dict, telephone: str, texte: str, *, origine: str, contact_nom: str = "",
                  auteur: str = "") -> dict:
    """Envoie un SMS au nom de la boutique. origine : code de la notification
    (ex. MAINT_STATUT) ou « MANUEL ». Seuls les SMS ENVOYÉS sont facturés."""
    import envois_plateforme as envois

    texte = texte.strip()[:918]  # 6 SMS au maximum
    ligne = {"id": new_id(), "boutique_id": boutique["id"], "date": now_iso(), "jour": aujourd_hui().isoformat(),
             "telephone": normaliser_telephone(telephone), "contact_nom": contact_nom[:120], "texte": texte,
             "nb_sms": nombre_sms(texte), "origine": origine, "auteur": auteur, "facture_id": None}
    if not peut_envoyer(boutique):
        ligne.update({"statut": "NON_ENVOYE", "erreur": etat(boutique)["libelle"], "nb_sms": 0})
    else:
        c = config(boutique)
        statut, erreur = await envois.envoyer_sms_ovh(telephone, texte, c["expediteur"], c.get("service_ovh") or None)
        ligne.update({"statut": statut, "erreur": erreur})
        if statut != "ENVOYE":
            ligne["nb_sms"] = 0  # un échec n'est pas facturé
    await db.sms_envois.insert_one(ligne.copy())
    return ligne


# Textes courts des notifications automatiques (mêmes variables que les e-mails)
MODELES_SMS = {
    "CMD_RECUE": "{{ boutique.nom }} : commande {{ commande.numero }} reçue ({{ commande.total }} {{ boutique.devise }}). Suivi : {{ lien }}",
    "CMD_STATUT": "{{ boutique.nom }} : votre commande {{ commande.numero }} est « {{ commande.statut_libelle }} ». Suivi : {{ lien }}",
    "CMD_PAYEE": "{{ boutique.nom }} : paiement reçu pour la commande {{ commande.numero }}. Merci !",
    "MAINT_DEPOT": "{{ boutique.nom }} : appareil enregistré, dossier {{ dossier.numero }}, code {{ dossier.code_suivi }}. Suivi : {{ lien }}",
    "MAINT_STATUT": "{{ boutique.nom }} : dossier {{ dossier.numero }} « {{ dossier.statut_libelle }} ». Suivi : {{ lien }}",
}


async def notifier(boutique: dict, code: str, client: dict, contexte: dict, lien: str) -> Optional[dict]:
    """Notification automatique par SMS au client (si le service est actif,
    que la boutique a laissé les SMS automatiques, et que le client a un numéro)."""
    from messagerie import remplir

    telephone = (client or {}).get("telephone")
    e = etat(boutique)
    if code not in MODELES_SMS or not telephone or e["statut"] != "ACTIF" or not e["notifications_auto"]:
        return None
    boutique_publique = {k: boutique.get(k) for k in ("nom", "devise", "slug", "telephone")}
    texte = remplir(MODELES_SMS[code], {**contexte, "boutique": boutique_publique, "lien": lien})
    return await envoyer(boutique, telephone, texte, origine=code, contact_nom=client.get("nom", ""), auteur="automatique")


# ---------------------------------------------------------------------------
# Journal par contact
# ---------------------------------------------------------------------------
async def contacts(boutique_id: str, q: str = "") -> list[dict]:
    """Envois regroupés par numéro : nom, nombre de messages, SMS facturés, dernier envoi."""
    groupes: dict[str, dict] = {}
    async for s in db.sms_envois.find({"boutique_id": boutique_id}, SANS_ID).sort("date", 1):
        g = groupes.setdefault(s["telephone"], {"telephone": s["telephone"], "contact_nom": "", "nb_messages": 0,
                                                "nb_sms": 0, "nb_echecs": 0, "dernier_envoi": None, "dernier_texte": ""})
        g["contact_nom"] = s.get("contact_nom") or g["contact_nom"]
        g["nb_messages"] += 1
        g["nb_sms"] += s.get("nb_sms", 0)
        g["nb_echecs"] += s["statut"] != "ENVOYE"
        g["dernier_envoi"], g["dernier_texte"] = s["date"], s["texte"]
    lignes = list(groupes.values())
    if q.strip():
        t = q.strip().lower()
        lignes = [g for g in lignes if t in g["contact_nom"].lower() or t in g["telephone"]]
    return sorted(lignes, key=lambda g: g["dernier_envoi"] or "", reverse=True)


async def messages_du_contact(boutique_id: str, telephone: str) -> list[dict]:
    return await db.sms_envois.find({"boutique_id": boutique_id, "telephone": normaliser_telephone(telephone)},
                                    SANS_ID).sort("date", -1).to_list(500)


# ---------------------------------------------------------------------------
# Facturation
# ---------------------------------------------------------------------------
async def facturer(debut: str, fin: str, boutique_id: Optional[str] = None, par: str = "") -> list[dict]:
    """Une facture par boutique pour les SMS ENVOYÉS du `debut` au `fin` inclus
    et pas encore facturés. Aucune facture pour une boutique sans SMS."""
    s = get_settings()
    filtre: dict = {"statut": "ENVOYE", "facture_id": None, "jour": {"$gte": debut, "$lte": fin}}
    if boutique_id:
        filtre["boutique_id"] = boutique_id
    par_boutique: dict[str, list[dict]] = {}
    async for x in db.sms_envois.find(filtre, {"_id": 0, "id": 1, "boutique_id": 1, "nb_sms": 1}):
        par_boutique.setdefault(x["boutique_id"], []).append(x)
    factures = []
    for bid, lignes in par_boutique.items():
        b = await db.boutiques.find_one({"id": bid}, SANS_ID)
        if not b:
            continue
        prix = etat(b)["prix_sms"]
        nb = sum(x.get("nb_sms", 0) for x in lignes)
        facture = {
            "id": new_id(), "numero": f"SMS-{fin[:7]}-{b.get('code_marchand', '')}-{new_id()[:4].upper()}",
            "boutique_id": bid, "boutique_nom": b["nom"], "code_marchand": b.get("code_marchand", ""),
            "debut": debut, "fin": fin, "nb_messages": len(lignes), "nb_sms": nb, "prix_sms": prix,
            "montant": nb * prix, "date_emission": aujourd_hui().isoformat(),
            "echeance": (aujourd_hui() + timedelta(days=s.sms_facture_delai_jours)).isoformat(),
            "statut": "A_PAYER" if nb * prix > 0 else "PAYEE", "paiement": None, "cree_par": par, "created_at": now_iso(),
        }
        await db.sms_factures.insert_one(facture.copy())
        await db.sms_envois.update_many({"id": {"$in": [x["id"] for x in lignes]}, "facture_id": None},
                                        {"$set": {"facture_id": facture["id"]}})
        factures.append(facture)
    return factures


def _avec_retard(f: dict) -> dict:
    retard = (aujourd_hui() - date.fromisoformat(f["echeance"])).days
    return {**f, "jours_retard": max(retard, 0) if f["statut"] == "A_PAYER" else 0}


async def factures(boutique_id: Optional[str] = None, statut: str = "") -> list[dict]:
    filtre: dict = {}
    if boutique_id:
        filtre["boutique_id"] = boutique_id
    if statut:
        filtre["statut"] = statut
    return [_avec_retard(f) for f in await db.sms_factures.find(filtre, SANS_ID).sort("created_at", -1).to_list(2000)]


async def retards() -> list[dict]:
    """Boutiques ayant au moins une facture SMS impayée après son échéance."""
    par_boutique: dict[str, dict] = {}
    for f in await factures(statut="A_PAYER"):
        if f["jours_retard"] <= 0:
            continue
        g = par_boutique.setdefault(f["boutique_id"], {"boutique_id": f["boutique_id"], "boutique_nom": f["boutique_nom"],
                                                       "code_marchand": f["code_marchand"], "factures": [],
                                                       "montant_du": 0, "jours_retard": 0})
        g["factures"].append(f)
        g["montant_du"] += f["montant"]
        g["jours_retard"] = max(g["jours_retard"], f["jours_retard"])
    for g in par_boutique.values():
        b = await db.boutiques.find_one({"id": g["boutique_id"]}, SANS_ID) or {}
        g["service"] = etat(b)
    return sorted(par_boutique.values(), key=lambda g: -g["jours_retard"])


async def payer_facture(facture_id: str, mode: str, *, reference: str = "", saisi_par: str = "",
                        cle: Optional[str] = None) -> Optional[dict]:
    """Marque la facture payée (une seule fois) et rétablit le service SMS s'il était
    suspendu pour impayé et qu'il ne reste plus de facture en retard."""
    paiement = {"id": cle or new_id(), "date": aujourd_hui().isoformat(), "mode": mode, "reference": reference[:120],
                "saisi_par": saisi_par}
    f = await db.sms_factures.find_one_and_update({"id": facture_id, "statut": "A_PAYER"},
                                                  {"$set": {"statut": "PAYEE", "paiement": paiement}})
    facture = await db.sms_factures.find_one({"id": facture_id}, SANS_ID)
    if not f or not facture:
        return facture  # déjà payée (idempotence) ou introuvable
    b = await db.boutiques.find_one({"id": facture["boutique_id"]}, SANS_ID)
    c = config(b or {})
    if c.get("suspendu") and c.get("motif") == "IMPAYE":
        encore = [x for x in await factures(facture["boutique_id"], "A_PAYER") if x["jours_retard"] > 0]
        if not encore:
            await db.boutiques.update_one({"id": b["id"]}, {"$set": {"sms.suspendu": False, "sms.motif": None}})
            facture["service_retabli"] = True
    return facture


async def suspendre(boutique_ids: list[str], motif: str = "IMPAYE") -> int:
    res = await db.boutiques.update_many({"id": {"$in": boutique_ids}, "sms.expediteur": {"$exists": True}},
                                         {"$set": {"sms.suspendu": True, "sms.motif": motif, "sms.suspendu_le": now_iso()}})
    return res.modified_count


async def reactiver(boutique_ids: list[str]) -> int:
    res = await db.boutiques.update_many({"id": {"$in": boutique_ids}}, {"$set": {"sms.suspendu": False, "sms.motif": None}})
    return res.modified_count


# ---------------------------------------------------------------------------
# Facturation automatique le 1er du mois (appelée par la tâche de la nuit)
# ---------------------------------------------------------------------------
async def facturation_mensuelle() -> list[dict]:
    """Le 1er du mois : factures du mois écoulé (une seule fois, même avec plusieurs serveurs)."""
    jour = aujourd_hui()
    if jour.day != 1:
        return []
    fin = jour - timedelta(days=1)
    try:
        await db.verrous.insert_one({"_id": f"factures-sms-{fin.isoformat()[:7]}", "date": now_iso()})
    except DuplicateKeyError:
        return []
    try:
        return await facturer(fin.replace(day=1).isoformat(), fin.isoformat(), par="automatique")
    except Exception:  # noqa: BLE001 — noté dans les journaux, la nuit continue
        logger.exception("Facturation SMS mensuelle impossible")
        return []


def notifier_en_fond(boutique: dict, code: str, client: dict, contexte: dict, lien: str) -> None:
    """SMS automatique sans faire attendre la réponse HTTP."""
    async def _run():
        try:
            await notifier(boutique, code, client, contexte, lien)
        except Exception:  # noqa: BLE001
            logger.exception("SMS %s impossible", code)
    asyncio.create_task(_run())
