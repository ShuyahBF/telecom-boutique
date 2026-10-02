"""Écran super-administrateur « KYC des DG » (spécification du 02/10/2026, adLyn).

Liste les responsables (DG) dont le dossier d'identification (KYC, kyc.py) n'est pas à
jour, d'après les statuts KYC EXISTANTS de la fiche boutique :
  - ABSENT    : statut NON_FOURNI (aucun justificatif) ;
  - REFUSE    : statut REJETE (motif de rejet affiché) ;
  - INCOMPLET : statut EN_ATTENTE mais sans « Pièce d'identité du DG » parmi les pièces ;
  - EN_ATTENTE (facultatif, case « inclure ») : dossier complet en attente de
    vérification par l'administrateur (rien à faire côté DG, donc masqué par défaut).
  Le KYC actuel n'a pas de date de validité : il n'existe donc pas de cas « expiré ».
Exclues : boutiques internes / de test (`test: True`) et boutiques archivées (cycle_vie.py).

Rappel WhatsApp aux DG sélectionnés : message prédéfini MODIFIABLE (variables {dg},
{boutique}, {etat}, {lien}), au plus UN rappel envoyé par DG et par 24 heures (un envoi
refusé par la limite est journalisé mais ne compte pas), chaque tentative journalisée
(collection kyc_rappels_journal). Modèle WhatsApp facultatif WHATSAPP_KYC_TEMPLATE ;
sans modèle, message texte (il ne passe que dans la fenêtre de 24 h de WhatsApp).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from config import get_settings
from db import SANS_ID, db
from kyc import STATUTS_KYC, kyc_vide
from utils import new_id, now_iso

LIMITE_HEURES = 24
RAPPELS_MAX_PAR_ENVOI = 200
MESSAGE_DEFAUT = ("Bonjour {dg}, le dossier d'identification (KYC) de votre boutique « {boutique} » sur adLyn "
                  "n'est pas à jour ({etat}). Merci de déposer vos justificatifs depuis Paramètres > Dossier KYC : "
                  "{lien}. L'équipe adLyn")
ETATS = {"ABSENT": "KYC absent", "REFUSE": "KYC refusé", "INCOMPLET": "KYC incomplet",
         "EN_ATTENTE": "KYC en attente de vérification"}


def etat_kyc(boutique: dict) -> Optional[str]:
    """ABSENT / REFUSE / INCOMPLET / EN_ATTENTE, ou None si le KYC est à jour (vérifié)."""
    kyc = boutique.get("kyc") or kyc_vide()
    statut = kyc.get("statut") or "NON_FOURNI"
    if statut == "VERIFIE":
        return None
    if statut == "REJETE":
        return "REFUSE"
    if statut == "EN_ATTENTE":
        types = {d.get("type") for d in kyc.get("documents", [])}
        return "EN_ATTENTE" if "PIECE_IDENTITE_DG" in types else "INCOMPLET"
    return "ABSENT"


def _depuis(heures: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=heures)).isoformat()


async def _dernier_envoi(dg_id: str) -> Optional[dict]:
    docs = await db.kyc_rappels_journal.find({"dg_id": dg_id, "statut": "ENVOYE"}, SANS_ID) \
        .sort("date", -1).to_list(1)
    return docs[0] if docs else None


async def _dg(boutique_id: str) -> Optional[dict]:
    return await db.users.find_one({"boutique_id": boutique_id, "role": "dg", "actif": {"$ne": False}}, SANS_ID)


async def lister(inclure_en_attente: bool = False) -> list[dict]:
    resultat = []
    filtre = {"test": {"$ne": True}, "cycle_vie.statut": {"$ne": "ARCHIVE"}}
    async for b in db.boutiques.find(filtre, SANS_ID).sort("nom", 1):
        etat = etat_kyc(b)
        if etat is None or (etat == "EN_ATTENTE" and not inclure_en_attente):
            continue
        dg = await _dg(b["id"]) or {}
        dernier = await _dernier_envoi(dg["id"]) if dg.get("id") else None
        prochain = None
        if dernier:
            prochain = (datetime.fromisoformat(dernier["date"]) + timedelta(hours=LIMITE_HEURES)).isoformat()
            if prochain <= now_iso():
                prochain = None
        kyc = b.get("kyc") or kyc_vide()
        resultat.append({
            "boutique_id": b["id"], "boutique_nom": b.get("nom", ""), "code_marchand": b.get("code_marchand", ""),
            "boutique_active": b.get("actif", True), "dg_id": dg.get("id"), "dg_nom": dg.get("nom") or b.get("dg_nom", ""),
            "telephone": b.get("dg_telephone") or dg.get("telephone") or "", "email": dg.get("email") or "",
            "etat": etat, "etat_libelle": ETATS[etat], "statut_kyc": kyc.get("statut") or "NON_FOURNI",
            "statut_kyc_libelle": STATUTS_KYC.get(kyc.get("statut") or "NON_FOURNI", ""),
            "motif_rejet": kyc.get("motif_rejet", ""), "pieces": len(kyc.get("documents", [])),
            "dernier_rappel": dernier["date"] if dernier else None, "rappel_possible_le": prochain,
        })
    return resultat


def composer(message: str, ligne: dict) -> str:
    """Remplace les variables du message (sans format() : un texte libre ne peut rien casser)."""
    lien = f"{get_settings().public_site_url}/gestion/parametres"
    texte = message
    for cle, valeur in (("{dg}", ligne["dg_nom"]), ("{boutique}", ligne["boutique_nom"]),
                        ("{etat}", ligne["etat_libelle"].lower()), ("{lien}", lien)):
        texte = texte.replace(cle, valeur or "")
    return texte.strip()


async def envoyer_rappels(boutique_ids: list[str], message: str, admin: dict) -> list[dict]:
    import envois_plateforme as envois

    message = (message or "").strip() or MESSAGE_DEFAUT
    if len(message) > 1000:
        raise HTTPException(400, "Message trop long (1000 caractères au plus)")
    ids = list(dict.fromkeys(boutique_ids))
    if not ids:
        raise HTTPException(400, "Sélectionnez au moins un DG")
    if len(ids) > RAPPELS_MAX_PAR_ENVOI:
        raise HTTPException(400, f"{RAPPELS_MAX_PAR_ENVOI} DG au plus par envoi")
    concernes = {x["boutique_id"]: x for x in await lister(inclure_en_attente=True)}
    s = get_settings()
    resultats = []
    for bid in ids:
        ligne = concernes.get(bid)
        base = {"id": new_id(), "date": now_iso(), "boutique_id": bid, "par": admin.get("email", "")}
        if not ligne:
            resultats.append({**base, "statut": "NON_CONCERNE", "erreur": "KYC à jour, boutique introuvable ou exclue"})
            continue
        base.update({"boutique_nom": ligne["boutique_nom"], "code_marchand": ligne["code_marchand"],
                     "dg_id": ligne["dg_id"], "dg_nom": ligne["dg_nom"], "telephone": ligne["telephone"],
                     "etat": ligne["etat"]})
        if not ligne["dg_id"]:
            entree = {**base, "statut": "SANS_DG", "erreur": "Aucun compte DG actif pour cette boutique"}
        else:
            verrou = f"kyc-rappel-{ligne['dg_id']}"
            try:  # deux clics simultanés : un seul envoi
                await db.verrous.insert_one({"_id": verrou, "date": now_iso()})
            except DuplicateKeyError:
                resultats.append({**base, "statut": "EN_COURS", "erreur": "Envoi déjà en cours pour ce DG"})
                continue
            try:
                dernier = await _dernier_envoi(ligne["dg_id"])
                if dernier and dernier["date"] > _depuis(LIMITE_HEURES):
                    entree = {**base, "statut": "LIMITE_24H",
                              "erreur": f"Un rappel a déjà été envoyé à ce DG le {dernier['date'][:16].replace('T', ' ')} (UTC)"}
                else:
                    texte = composer(message, ligne)
                    statut, erreur = await envois.envoyer_whatsapp(
                        ligne["telephone"], [ligne["dg_nom"], ligne["boutique_nom"], ligne["etat_libelle"].lower()],
                        texte, modele=s.whatsapp_kyc_template or "")
                    entree = {**base, "statut": statut, "erreur": erreur, "message": texte}
            finally:
                await db.verrous.delete_one({"_id": verrou})
        await db.kyc_rappels_journal.insert_one(entree.copy())
        resultats.append(entree)
    return resultats


async def journal(limite: int = 200) -> list[dict]:
    return await db.kyc_rappels_journal.find({}, SANS_ID).sort("date", -1).to_list(limite)
