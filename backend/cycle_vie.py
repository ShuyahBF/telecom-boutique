"""Cycle de vie du non-renouvellement d'un abonnement (spécification validée par le
propriétaire de la plateforme le 02/10/2026, point C).

Calendrier (jours calendaires depuis l'échéance impayée, grâce comprise ; « J+0 » = jour
de l'échéance, dernier jour payé) :
  - J+103 : avertissement « suspension dans 7 jours » ;
  - J+110 : SUSPENSION (statut SUSPENDU_NON_RENOUVELE) : plus aucun accès sauf
            super-administrateur, vitrine publique fermée (boutique inactive) ;
            avertissement « boutique suspendue » ;
  - J+112 : avertissement « dernier avis : suppression demain » ;
  - J+113 : ARCHIVE chiffrée des données de la boutique (export_boutique.py, même
            chiffrement que les exports, phrase SAUVEGARDE_AUTO_PHRASE), envoyée sur R2
            dans le dossier « archives-locataires/ », RELUE depuis R2 et vérifiée
            (déchiffrement complet + nombres de documents identiques) ; SEULEMENT si la
            vérification réussit, suppression des données (comptes compris). La fiche de
            la boutique est conservée au statut « ARCHIVE » (référence de l'archive, date,
            nombres de documents). En cas d'échec : rien n'est supprimé, alerte au
            super-administrateur (journal + e-mail), nouvel essai le lendemain.
Avertissements (WhatsApp, SMS en repli, e-mail — envois_plateforme.py) : chacun UNE seule
fois par échéance impayée (marque posée de façon atomique dans la fiche), journalisés.
Rattrapage : si la tâche n'a pas tourné un jour, l'étape en retard est faite au passage
suivant ; l'archivage n'a jamais lieu le jour même du « dernier avis » (il attend au moins
le lendemain de son envoi).

Autres règles :
  - boutiques internes / de test (`test: True`) : toujours exclues ;
  - un paiement repousse l'échéance : le cycle repart de zéro (les marques sont liées à
    l'échéance) ; une suspension levée à la main par le super-administrateur (boutique
    réactivée) met le cycle EN PAUSE : pas d'archivage tant que l'échéance ne change pas ;
  - paramètres (super-administrateur) : interrupteur « Cycle de vie automatique »
    (activé par défaut), MODE SIMULATION (liste ce qui serait fait, sans rien faire ni
    envoyer), conservation des archives en jours (365 par défaut), frais de réouverture
    (montant + devise, 0 = gratuit) ;
  - conservation : une archive plus vieille que la durée de conservation est effacée de R2 ;
  - réouverture (super-administrateur) : frais de réouverture encaissés (saisis), archive
    relue et vérifiée, restauration LIMITÉE À LA BOUTIQUE, boutique réactivée avec une
    nouvelle échéance ;
  - tâche quotidienne : POST /api/cycle-vie/declencher (même jeton que la sauvegarde
    générale, appelée par le Cron Job juste après elle) ; rapport quotidien par e-mail.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import export_boutique
import sauvegarde_auto
import transfert_donnees
from config import get_settings
from db import SANS_ID, db
from utils import new_id, now_iso

logger = logging.getLogger(__name__)

J_AVERTISSEMENT = 103
J_SUSPENSION = 110
J_DERNIER_AVIS = 112
J_ARCHIVAGE = 113
STATUT_SUSPENDU = "SUSPENDU_NON_RENOUVELE"
STATUT_ARCHIVE = "ARCHIVE"
STATUT_REOUVERT = "REOUVERT"
MOTIF_SUSPENSION = "NON_RENOUVELE"
MOTIF_ARCHIVE = "ARCHIVE"
CODE_SUSPENDU = "BOUTIQUE_SUSPENDUE_NON_RENOUVELEE"
MESSAGE_SUSPENDU = ("Boutique suspendue : abonnement non renouvelé depuis plus de 110 jours. "
                    "Contactez l'administrateur de la plateforme adLyn.")
MESSAGE_ARCHIVE = ("Boutique fermée : ses données ont été archivées après le non-renouvellement de "
                   "l'abonnement. Contactez l'administrateur de la plateforme adLyn pour la réouvrir.")
ID_PARAMETRES = "cycle_vie"
DEFAUTS = {"actif": True, "simulation": False, "conservation_jours": 365, "frais_montant": 0,
           "frais_devise": "FCFA"}
CONSERVATION_MIN, CONSERVATION_MAX = 1, 36500
AVERTISSEMENTS = {"J103": J_AVERTISSEMENT, "J110": J_SUSPENSION, "J112": J_DERNIER_AVIS}
UTILISATEUR_SYSTEME = "cycle-vie-automatique"


# ---------------------------------------------------------------------------
# Dates et paramètres
# ---------------------------------------------------------------------------
def aujourd_hui() -> date:
    """Date du jour dans le fuseau de la plateforme (remplacée dans les tests)."""
    import abonnements
    return abonnements.aujourd_hui()


def _fr(d: date) -> str:
    return d.strftime("%d/%m/%Y")


async def parametres() -> dict:
    doc = await db.parametres_plateforme.find_one({"_id": ID_PARAMETRES}, SANS_ID) or {}
    return {**DEFAUTS, **{k: doc[k] for k in DEFAUTS if k in doc},
            "modifie_le": doc.get("modifie_le"), "modifie_par": doc.get("modifie_par")}


async def enregistrer_parametres(maj: dict, par: str) -> dict:
    """Champs absents = inchangés. Conservation : 1 à 36 500 jours ; frais >= 0."""
    valeurs = {k: v for k, v in maj.items() if k in DEFAUTS and v is not None}
    if "conservation_jours" in valeurs:
        valeurs["conservation_jours"] = int(valeurs["conservation_jours"])
        if not CONSERVATION_MIN <= valeurs["conservation_jours"] <= CONSERVATION_MAX:
            raise HTTPException(400, f"Durée de conservation invalide ({CONSERVATION_MIN} à {CONSERVATION_MAX} jours)")
    if "frais_montant" in valeurs:
        valeurs["frais_montant"] = int(valeurs["frais_montant"])
        if valeurs["frais_montant"] < 0:
            raise HTTPException(400, "Les frais de réouverture ne peuvent pas être négatifs")
    if "frais_devise" in valeurs:
        valeurs["frais_devise"] = str(valeurs["frais_devise"]).strip().upper()[:10] or "FCFA"
    avant = await parametres()
    await db.parametres_plateforme.update_one({"_id": ID_PARAMETRES}, {"$set": {
        **valeurs, "modifie_le": now_iso(), "modifie_par": par}}, upsert=True)
    await journaliser(None, "PARAMETRES_MODIFIES", par=par,
                      avant={k: avant[k] for k in valeurs}, apres=valeurs)
    return await parametres()


# ---------------------------------------------------------------------------
# Situation d'une boutique
# ---------------------------------------------------------------------------
def _echeance(boutique: dict) -> date:
    from abonnements import abonnement_initial

    ab = boutique.get("abonnement") or abonnement_initial(boutique.get("created_at"))
    return date.fromisoformat(ab["echeance"])


def cycle(boutique: dict) -> dict:
    """Marques du cycle EN COURS : celles d'une ancienne échéance (payée depuis) sont ignorées."""
    cv = boutique.get("cycle_vie") or {}
    if cv.get("statut") == STATUT_ARCHIVE:
        return cv
    return cv if cv.get("echeance") == _echeance(boutique).isoformat() else {}


def suspendue_par_le_cycle(boutique: dict) -> bool:
    return boutique.get("actif") is False and (boutique.get("suspension") or {}).get("motif") == MOTIF_SUSPENSION


def calendrier(boutique: dict, jour: Optional[date] = None) -> dict:
    """Dates des étapes et étape actuelle (affichées dans l'administration)."""
    jour = jour or aujourd_hui()
    echeance = _echeance(boutique)
    cv = cycle(boutique)
    j = (jour - echeance).days
    if boutique.get("test"):
        etape = "EXCLUE_TEST"
    elif cv.get("statut") == STATUT_ARCHIVE:
        etape = "ARCHIVEE"
    elif cv.get("suspendu_le") and not suspendue_par_le_cycle(boutique):
        etape = "EN_PAUSE"  # suspension levée à la main par le super-administrateur
    elif cv.get("suspendu_le"):
        etape = "SUSPENDUE"
    elif j >= J_AVERTISSEMENT:
        etape = "AVERTIE" if "J103" in (cv.get("avertissements") or {}) else "A_AVERTIR"
    else:
        etape = "NORMALE"
    return {"echeance": echeance.isoformat(), "jours_depuis_echeance": j, "etape": etape,
            "avertissement_le": (echeance + timedelta(days=J_AVERTISSEMENT)).isoformat(),
            "suspension_le": (echeance + timedelta(days=J_SUSPENSION)).isoformat(),
            "dernier_avis_le": (echeance + timedelta(days=J_DERNIER_AVIS)).isoformat(),
            "archivage_le": (echeance + timedelta(days=J_ARCHIVAGE)).isoformat(),
            "avertissements": cv.get("avertissements") or {}, "suspendu_le": cv.get("suspendu_le"),
            "archive": cv.get("archive"), "archivage_echecs": cv.get("archivage_echecs", 0),
            "derniere_erreur": cv.get("derniere_erreur", "")}


def actions_dues(boutique: dict, jour: date) -> list[str]:
    """Étapes à exécuter aujourd'hui, dans l'ordre (fonction pure, sans effet)."""
    if boutique.get("test"):
        return []
    cv = cycle(boutique)
    if cv.get("statut") == STATUT_ARCHIVE:
        return []
    j = (jour - _echeance(boutique)).days
    if j < J_AVERTISSEMENT:
        return []
    avert = cv.get("avertissements") or {}
    actions = []
    if not cv.get("suspendu_le"):
        if j < J_SUSPENSION:
            return [] if "J103" in avert else ["AVERTISSEMENT_J103"]
        actions.append("SUSPENSION")  # comprend l'avertissement J+110
        if j >= J_DERNIER_AVIS:
            actions.append("AVERTISSEMENT_J112")
        return actions
    if not suspendue_par_le_cycle(boutique):
        return []  # cycle en pause (suspension levée par le super-administrateur)
    if "J110" not in avert:
        actions.append("AVERTISSEMENT_J110")
    if j >= J_DERNIER_AVIS and "J112" not in avert:
        actions.append("AVERTISSEMENT_J112")
    elif j >= J_ARCHIVAGE and "J112" in avert and avert["J112"].get("jour", "") < jour.isoformat():
        actions.append("ARCHIVAGE")
    return actions


# ---------------------------------------------------------------------------
# Contrôle d'accès (auth._resoudre_contexte)
# ---------------------------------------------------------------------------
def controler(boutique: dict, user: dict) -> None:
    """Boutique suspendue par le cycle de vie ou archivée : AUCUN accès (même la page
    Abonnement), sauf pour le super-administrateur."""
    if user.get("role") == "super_admin" or boutique.get("actif") is not False:
        return
    motif = (boutique.get("suspension") or {}).get("motif")
    if motif == MOTIF_SUSPENSION:
        raise HTTPException(403, MESSAGE_SUSPENDU, headers={"X-Adlyn-Code": CODE_SUSPENDU})
    if motif == MOTIF_ARCHIVE:
        raise HTTPException(403, MESSAGE_ARCHIVE, headers={"X-Adlyn-Code": CODE_SUSPENDU})


# ---------------------------------------------------------------------------
# Journal et alertes
# ---------------------------------------------------------------------------
async def journaliser(boutique: Optional[dict], action: str, **details) -> dict:
    ligne = {"id": new_id(), "date": now_iso(), "action": action,
             "boutique_id": (boutique or {}).get("id"), "boutique_nom": (boutique or {}).get("nom", ""),
             "code_marchand": (boutique or {}).get("code_marchand", ""), **details}
    await db.cycle_vie_journal.insert_one(ligne.copy())
    return ligne


async def alerter(boutique: dict, message: str) -> None:
    """Alerte au super-administrateur : journal (niveau ALERTE, affiché dans l'écran) + e-mail."""
    import envois_plateforme

    s = get_settings()
    statut, erreur = ("NON_CONFIGURE", "RAPPORT_EMAIL non configuré")
    if s.rapport_email:
        statut, erreur = await envois_plateforme.envoyer_email(
            f"[adLyn] ALERTE cycle de vie : {boutique.get('nom', '')}", message, s.rapport_email)
    await journaliser(boutique, "ALERTE", niveau="ALERTE", message=message, email=statut, email_erreur=erreur)


# ---------------------------------------------------------------------------
# Avertissements à l'abonné (une seule fois chacun)
# ---------------------------------------------------------------------------
def _texte(code: str, boutique: dict) -> str:
    cal = calendrier(boutique)
    nom = boutique.get("nom", "")
    echeance = _fr(date.fromisoformat(cal["echeance"]))
    suspension = _fr(date.fromisoformat(cal["suspension_le"]))
    archivage = _fr(date.fromisoformat(cal["archivage_le"]))
    lien = f"{get_settings().public_site_url}/gestion/abonnement"
    if code == "J103":
        return (f"adLyn : l'abonnement de « {nom} » a expiré le {echeance}. Sans renouvellement, la boutique sera "
                f"SUSPENDUE le {suspension}, puis ses données seront archivées et supprimées de la plateforme le "
                f"{archivage}. Renouvelez dès maintenant : {lien}")
    if code == "J110":
        return (f"adLyn : la boutique « {nom} » est SUSPENDUE depuis aujourd'hui (abonnement non renouvelé depuis "
                f"le {echeance}). Ses données seront archivées puis supprimées de la plateforme le {archivage}. "
                "Contactez adLyn pour la réouvrir.")
    return (f"adLyn — DERNIER AVIS : les données de la boutique « {nom} » seront archivées puis supprimées de la "
            f"plateforme DEMAIN ({archivage}). Contactez adLyn aujourd'hui pour l'éviter.")


async def _destinataire(boutique: dict) -> dict:
    dg = await db.users.find_one({"boutique_id": boutique["id"], "role": "dg"}, SANS_ID) or {}
    return {"nom": dg.get("nom", ""), "email": dg.get("email") or boutique.get("dg_email") or "",
            "telephone": boutique.get("dg_telephone") or dg.get("telephone") or boutique.get("telephone", "")}


async def avertir(boutique: dict, code: str, jour: date) -> Optional[dict]:
    """Envoie l'avertissement `code` (J103 / J110 / J112) s'il n'a pas encore été envoyé
    pour cette échéance. La marque est posée AVANT l'envoi, de façon atomique : deux
    exécutions simultanées n'envoient jamais deux fois. Renvoie la ligne du journal."""
    import envois_plateforme as envois

    champ = f"cycle_vie.avertissements.{code}"
    res = await db.boutiques.update_one(
        {"id": boutique["id"], "cycle_vie.echeance": _echeance(boutique).isoformat(), champ: {"$exists": False}},
        {"$set": {champ: {"jour": jour.isoformat(), "date": now_iso()}}})
    if not res.modified_count:
        return None
    s = get_settings()
    dest = await _destinataire(boutique)
    texte = _texte(code, boutique)
    wa, wa_err = await envois.envoyer_whatsapp(dest["telephone"], [boutique.get("nom", ""), texte], texte,
                                               modele=s.whatsapp_cycle_vie_template or "")
    sms, sms_err = ("NON_ENVOYE", "")
    if wa != "ENVOYE":  # repli SMS
        sms, sms_err = await envois.envoyer_sms(dest["telephone"], texte)
    email, email_err = await envois.envoyer_email(
        f"[adLyn] {'Dernier avis' if code == 'J112' else 'Abonnement non renouvelé'} — {boutique.get('nom', '')}",
        f"Bonjour {dest['nom']},\n\n{texte}\n\nL'équipe adLyn", dest["email"])
    envoi = {"whatsapp": wa, "whatsapp_erreur": wa_err, "sms": sms, "sms_erreur": sms_err,
             "email": email, "email_erreur": email_err, "telephone": dest["telephone"], "destinataire_email": dest["email"]}
    await db.boutiques.update_one({"id": boutique["id"]}, {"$set": {f"{champ}.envoi": envoi}})
    return await journaliser(boutique, f"AVERTISSEMENT_{code}", jour=jour.isoformat(), texte=texte, **envoi)


# ---------------------------------------------------------------------------
# Suspension (J+110)
# ---------------------------------------------------------------------------
async def _preparer(boutique: dict) -> dict:
    """Le cycle de vie est rattaché à l'échéance impayée actuelle (repart de zéro sinon)."""
    echeance = _echeance(boutique).isoformat()
    cv = boutique.get("cycle_vie") or {}
    if cv.get("statut") != STATUT_ARCHIVE and cv.get("echeance") != echeance:
        historique = (cv.get("historique") or [])[-10:]
        if cv.get("echeance"):
            historique.append({k: v for k, v in cv.items() if k != "historique"})
        await db.boutiques.update_one({"id": boutique["id"]}, {"$set": {"cycle_vie": {
            "echeance": echeance, "statut": "EN_COURS", "avertissements": {}, "historique": historique}}})
        boutique = await db.boutiques.find_one({"id": boutique["id"]}, SANS_ID)
    return boutique


async def suspendre(boutique: dict, jour: date) -> dict:
    res = await db.boutiques.update_one(
        {"id": boutique["id"], "cycle_vie.suspendu_le": {"$exists": False}},
        {"$set": {"actif": False,
                  "suspension": {"motif": MOTIF_SUSPENSION, "date": now_iso(), "par": UTILISATEUR_SYSTEME,
                                 "precedente": boutique.get("suspension")},
                  "cycle_vie.statut": STATUT_SUSPENDU, "cycle_vie.suspendu_le": now_iso(),
                  "cycle_vie.jour_suspension": jour.isoformat()}})
    if res.modified_count:
        await journaliser(boutique, "SUSPENSION", jour=jour.isoformat())
    boutique = await db.boutiques.find_one({"id": boutique["id"]}, SANS_ID)
    await avertir(boutique, "J110", jour)
    return {"suspendue": bool(res.modified_count)}


# ---------------------------------------------------------------------------
# Archivage (J+113) : export -> R2 -> relecture et vérification -> suppression
# ---------------------------------------------------------------------------
def bucket() -> str:
    return sauvegarde_auto.bucket()


def prefixe_archives() -> str:
    p = get_settings().adlyn_archives_prefixe or "archives-locataires/"
    return p if p.endswith("/") else p + "/"


def _temporaire(nature: str) -> str:
    transfert_donnees.DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
    return str(transfert_donnees.DOSSIER / f"cycle-vie-{nature}-{new_id()}{transfert_donnees.EXTENSION}")


def _effacer(*chemins: str) -> None:
    for chemin in chemins:
        try:
            os.remove(chemin)
        except (FileNotFoundError, TypeError):
            pass


async def archiver(boutique: dict, jour: date) -> dict:
    """Archive chiffrée vérifiée PUIS suppression. Toute anomalie : rien n'est supprimé,
    alerte au super-administrateur, nouvel essai à la prochaine exécution."""
    verrou = f"cycle-vie-archivage-{boutique['id']}"
    try:
        await db.verrous.insert_one({"_id": verrou, "date": now_iso()})
    except DuplicateKeyError:
        return {"statut": "DEJA_EN_COURS"}
    export = relu = ""
    cle, stock = "", None
    try:
        phrase = sauvegarde_auto.phrase()
        if not phrase:
            raise RuntimeError("SAUVEGARDE_AUTO_PHRASE absente ou trop courte : archivage impossible")
        stock = sauvegarde_auto.stockage()
        noms = await export_boutique.collections_de(boutique["id"])
        attendus = await export_boutique.compter(boutique["id"], noms)
        export, relu = _temporaire("export"), _temporaire("relu")
        manifest = await export_boutique.exporter(boutique["id"], phrase, export)
        ecrits = {c["nom"]: c["documents"] for c in manifest["collections"]}
        if ecrits != attendus:
            raise RuntimeError("Export incomplet : nombres de documents différents de la base")
        horodatage = datetime.now(timezone.utc).strftime("%H%M%S")
        cle = (f"{prefixe_archives()}{boutique.get('code_marchand') or 'boutique'}_{boutique['id']}_"
               f"{jour.isoformat()}_{horodatage}{transfert_donnees.EXTENSION}")
        await stock.envoyer(cle, export)
        # Relecture DEPUIS R2 (et non du fichier local) : c'est la copie distante qui compte
        await stock.telecharger(cle, relu)
        verification = await export_boutique.verifier(relu, phrase, boutique["id"], attendus)
        if not verification["conforme"]:
            raise RuntimeError("Vérification de l'archive en échec (collections : "
                               + ", ".join(verification["ecarts"]) + ")")
        if await export_boutique.compter(boutique["id"], noms) != attendus:
            raise RuntimeError("Des données ont changé pendant l'archivage")
        taille = os.path.getsize(relu)
    except Exception as exc:  # noqa: BLE001 — rien n'est supprimé, alerte
        erreur = str(getattr(exc, "detail", None) or exc)[:500]
        logger.warning("Archivage de %s en échec : %s", boutique.get("nom"), erreur)
        if cle and stock is not None:
            try:  # copie non vérifiée : retirée de R2 (la base, elle, est intacte)
                await stock.supprimer(cle)
            except Exception:  # noqa: BLE001
                pass
        await db.boutiques.update_one({"id": boutique["id"]}, {
            "$inc": {"cycle_vie.archivage_echecs": 1}, "$set": {"cycle_vie.derniere_erreur": erreur}})
        await journaliser(boutique, "ARCHIVAGE_ECHEC", jour=jour.isoformat(), erreur=erreur)
        await alerter(boutique, f"L'archivage de la boutique « {boutique.get('nom', '')} » "
                                f"({boutique.get('code_marchand', '')}) a échoué : {erreur}\n\n"
                                "AUCUNE donnée n'a été supprimée. Nouvel essai à la prochaine exécution.")
        return {"statut": "ECHEC", "erreur": erreur}
    finally:
        _effacer(export, relu)
        await db.verrous.delete_one({"_id": verrou})

    # Archive vérifiée : suppression des données de la boutique (comptes compris)
    supprimes = await export_boutique.supprimer(boutique["id"], noms)
    archive = {"id": new_id(), "cle": cle, "bucket": bucket(), "jour": jour.isoformat(), "date": now_iso(),
               "taille": taille, "comptes": attendus, "documents": sum(attendus.values()),
               "comptes_utilisateurs": attendus.get("users", 0)}
    await db.cycle_vie_archives.insert_one({**archive, "boutique_id": boutique["id"], "boutique_nom": boutique.get("nom", ""),
                                            "code_marchand": boutique.get("code_marchand", ""), "efface_le": None})
    await db.boutiques.update_one({"id": boutique["id"]}, {"$set": {
        "actif": False, "suspension": {"motif": MOTIF_ARCHIVE, "date": now_iso(), "par": UTILISATEUR_SYSTEME},
        "cycle_vie.statut": STATUT_ARCHIVE, "cycle_vie.archive": archive, "cycle_vie.derniere_erreur": ""}})
    await journaliser(boutique, "ARCHIVAGE", jour=jour.isoformat(), cle=cle, comptes=attendus, supprimes=supprimes)
    return {"statut": "ARCHIVEE", "cle": cle, "comptes": attendus, "supprimes": supprimes}


# ---------------------------------------------------------------------------
# Conservation des archives
# ---------------------------------------------------------------------------
async def archives_expirees(jour: date, conservation_jours: int) -> list[dict]:
    limite = (jour - timedelta(days=conservation_jours)).isoformat()
    return await db.cycle_vie_archives.find({"efface_le": None, "jour": {"$lte": limite}}, SANS_ID).to_list(None)


async def effacer_archives(jour: date, conservation_jours: int, simulation: bool) -> list[dict]:
    resultats = []
    for a in await archives_expirees(jour, conservation_jours):
        ligne = {"boutique_id": a["boutique_id"], "boutique_nom": a.get("boutique_nom", ""), "cle": a["cle"],
                 "jour_archive": a["jour"], "action": "EFFACEMENT_ARCHIVE"}
        if simulation:
            resultats.append({**ligne, "statut": "SIMULE"})
            continue
        try:
            await sauvegarde_auto.stockage().supprimer(a["cle"])
        except Exception as exc:  # noqa: BLE001
            resultats.append({**ligne, "statut": "ECHEC", "erreur": str(exc)[:300]})
            continue
        await db.cycle_vie_archives.update_one({"id": a["id"]}, {"$set": {"efface_le": now_iso()}})
        await db.boutiques.update_one({"id": a["boutique_id"], "cycle_vie.archive.id": a["id"]},
                                      {"$set": {"cycle_vie.archive.efface_le": now_iso()}})
        await journaliser({"id": a["boutique_id"], "nom": a.get("boutique_nom", ""),
                           "code_marchand": a.get("code_marchand", "")}, "EFFACEMENT_ARCHIVE", cle=a["cle"],
                          conservation_jours=conservation_jours)
        resultats.append({**ligne, "statut": "EFFACEE"})
    return resultats


# ---------------------------------------------------------------------------
# Exécution quotidienne (ou manuelle, ou simulation)
# ---------------------------------------------------------------------------
def _simuler(boutique: dict, action: str, jour: date) -> dict:
    """Effet d'une action sur une COPIE de la fiche (mode simulation : rien n'est écrit)."""
    b = {**boutique, "cycle_vie": {**cycle(boutique), "echeance": _echeance(boutique).isoformat()}}
    cv = b["cycle_vie"]
    cv["avertissements"] = dict(cv.get("avertissements") or {})
    marque = {"jour": jour.isoformat()}
    if action == "SUSPENSION":
        b.update({"actif": False, "suspension": {"motif": MOTIF_SUSPENSION}})
        cv.update({"suspendu_le": now_iso(), "statut": STATUT_SUSPENDU})
        cv["avertissements"]["J110"] = marque
    elif action.startswith("AVERTISSEMENT_"):
        cv["avertissements"][action.split("_", 1)[1]] = marque
    elif action == "ARCHIVAGE":
        cv["statut"] = STATUT_ARCHIVE
    return b


async def traiter_boutique(boutique: dict, jour: date, simulation: bool) -> list[dict]:
    faites = []
    if not simulation and (jour - _echeance(boutique)).days >= J_AVERTISSEMENT:
        boutique = await _preparer(boutique)
    for _ in range(5):
        actions = actions_dues(boutique, jour)
        if not actions:
            break
        action = actions[0]
        ligne = {"boutique_id": boutique["id"], "boutique_nom": boutique.get("nom", ""),
                 "code_marchand": boutique.get("code_marchand", ""), "action": action,
                 "jours_depuis_echeance": (jour - _echeance(boutique)).days}
        if simulation:
            faites.append({**ligne, "statut": "SIMULE"})
            boutique = _simuler(boutique, action, jour)
            continue
        if action == "SUSPENSION":
            await suspendre(boutique, jour)
            faites.append({**ligne, "statut": "FAIT"})
        elif action.startswith("AVERTISSEMENT_"):
            envoi = await avertir(boutique, action.split("_", 1)[1], jour)
            faites.append({**ligne, "statut": "FAIT" if envoi else "DEJA_FAIT",
                           **({k: envoi.get(k) for k in ("whatsapp", "sms", "email")} if envoi else {})})
        elif action == "ARCHIVAGE":
            r = await archiver(boutique, jour)
            faites.append({**ligne, "statut": r["statut"], "erreur": r.get("erreur", ""), "cle": r.get("cle", "")})
            if r["statut"] != "ARCHIVEE":
                break
        boutique = await db.boutiques.find_one({"id": boutique["id"]}, SANS_ID)
    return faites


async def executer(jour: Optional[date] = None, declencheur: str = "manuel",
                   simulation: Optional[bool] = None) -> dict:
    """Passe sur toutes les boutiques (sauf test). `simulation` None = réglage de la plateforme."""
    jour = jour or aujourd_hui()
    p = await parametres()
    simulation = p["simulation"] if simulation is None else simulation
    rapport = {"id": new_id(), "jour": jour.isoformat(), "debut": now_iso(), "declencheur": declencheur,
               "simulation": simulation, "statut": "TERMINE", "actions": [], "archives_effacees": [], "erreurs": []}
    if not p["actif"]:
        rapport["statut"] = "DESACTIVE"
    else:
        async for b in db.boutiques.find({"test": {"$ne": True}}, SANS_ID).sort("nom", 1):
            try:
                rapport["actions"] += await traiter_boutique(b, jour, simulation)
            except Exception as exc:  # noqa: BLE001 — une boutique en erreur n'arrête pas les autres
                logger.exception("Cycle de vie de %s", b.get("nom"))
                rapport["erreurs"].append({"boutique_id": b["id"], "boutique_nom": b.get("nom", ""),
                                           "erreur": str(exc)[:300]})
        rapport["archives_effacees"] = await effacer_archives(jour, int(p["conservation_jours"]), simulation)
    rapport["fin"] = now_iso()
    rapport["email"] = await envoyer_rapport(rapport)
    await db.cycle_vie_executions.insert_one(rapport.copy())
    return rapport


def texte_rapport(r: dict) -> tuple[str, str]:
    mode = "SIMULATION — " if r["simulation"] else ""
    if r["statut"] == "DESACTIVE":
        return (f"[adLyn] Cycle de vie du {r['jour']} : désactivé",
                "Le cycle de vie automatique est désactivé (Plateforme > Cycle de vie) : aucune action.")
    lignes = [f"{mode}Cycle de vie du non-renouvellement — {r['jour']} ({r['declencheur']})", ""]
    if not r["actions"] and not r["archives_effacees"]:
        lignes.append("Aucune action aujourd'hui.")
    for a in r["actions"]:
        lignes.append(f"  - {a['code_marchand']} {a['boutique_nom']} : {a['action']} (J+{a['jours_depuis_echeance']}) "
                      f"-> {a['statut']}{' : ' + a['erreur'] if a.get('erreur') else ''}")
    for a in r["archives_effacees"]:
        lignes.append(f"  - Archive de {a['boutique_nom']} ({a['jour_archive']}) effacée de R2 -> {a['statut']}")
    for e in r["erreurs"]:
        lignes.append(f"  - ERREUR {e['boutique_nom']} : {e['erreur']}")
    echecs = sum(1 for a in r["actions"] if a["statut"] == "ECHEC") + len(r["erreurs"])
    sujet = f"[adLyn] {mode}Cycle de vie du {r['jour']} : {len(r['actions'])} action(s)" + (
        f", {echecs} ÉCHEC(S)" if echecs else "")
    return sujet, "\n".join(lignes)


async def envoyer_rapport(r: dict) -> dict:
    import envois_plateforme

    s = get_settings()
    if not s.rapport_email:
        return {"statut": "NON_CONFIGURE", "erreur": "RAPPORT_EMAIL non configuré"}
    sujet, corps = texte_rapport(r)
    statut, erreur = await envois_plateforme.envoyer_email(sujet, corps, s.rapport_email)
    return {"statut": statut, "erreur": erreur}


async def reserver_jour(jour: str) -> bool:
    """Déclenchement par le Cron Job : une seule exécution réelle par jour."""
    try:
        await db.verrous.insert_one({"_id": f"cycle-vie-{jour}", "date": now_iso()})
        return True
    except DuplicateKeyError:
        return False


# ---------------------------------------------------------------------------
# Réouverture d'une boutique archivée (super-administrateur)
# ---------------------------------------------------------------------------
async def reouvrir(boutique_id: str, *, mode: str, montant: int, reference: str, formule: Optional[str],
                   admin: dict, montant_abonnement: int = 0) -> dict:
    """Frais de réouverture encaissés (saisis par le super-administrateur), puis archive
    relue depuis R2, vérifiée et restaurée (limitée à la boutique), boutique réactivée."""
    import abonnements

    boutique = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not boutique:
        raise HTTPException(404, "Boutique introuvable")
    cv = boutique.get("cycle_vie") or {}
    archive = cv.get("archive") or {}
    if cv.get("statut") != STATUT_ARCHIVE or not archive.get("cle"):
        raise HTTPException(400, "Cette boutique n'est pas archivée")
    if archive.get("efface_le"):
        raise HTTPException(410, "L'archive de cette boutique a été effacée (durée de conservation dépassée)")
    p = await parametres()
    frais = int(p["frais_montant"])
    if mode not in abonnements.MODES_PAIEMENT:
        raise HTTPException(400, "Mode de paiement inconnu")
    if mode != "OFFERT" and int(montant) < frais:
        raise HTTPException(400, f"Frais de réouverture : {frais} {p['frais_devise']} à encaisser")
    if formule and not await abonnements.formule(formule):
        raise HTTPException(400, "Formule inconnue")
    phrase = sauvegarde_auto.phrase()
    if not phrase:
        raise HTTPException(503, "SAUVEGARDE_AUTO_PHRASE absente : impossible de déchiffrer l'archive")
    verrou = f"cycle-vie-reouverture-{boutique_id}"
    try:
        await db.verrous.insert_one({"_id": verrou, "date": now_iso()})
    except DuplicateKeyError:
        raise HTTPException(409, "Une réouverture de cette boutique est déjà en cours") from None
    reouverture = {"id": new_id(), "date": now_iso(), "boutique_id": boutique_id, "boutique_nom": boutique.get("nom", ""),
                   "frais_attendus": frais, "devise": p["frais_devise"], "montant": int(montant), "mode": mode,
                   "reference": reference[:120], "par": admin.get("email", ""), "archive": archive["cle"],
                   "statut": "EN_COURS"}
    await db.cycle_vie_reouvertures.insert_one(reouverture.copy())
    chemin = _temporaire("reouverture")
    try:
        await sauvegarde_auto.stockage().telecharger(archive["cle"], chemin)
        verification = await export_boutique.verifier(chemin, phrase, boutique_id, archive.get("comptes") or {})
        if not verification["conforme"]:
            raise export_boutique.ErreurArchive("Archive non conforme (collections : " + ", ".join(verification["ecarts"]) + ")")
        resultat = await export_boutique.restaurer(chemin, phrase, boutique_id)
    except Exception as exc:  # noqa: BLE001
        erreur = str(getattr(exc, "detail", None) or exc)[:300]
        await db.cycle_vie_reouvertures.update_one({"id": reouverture["id"]}, {"$set": {"statut": "ECHEC", "erreur": erreur}})
        await journaliser(boutique, "REOUVERTURE_ECHEC", erreur=erreur, par=admin.get("email", ""))
        raise HTTPException(400 if isinstance(exc, export_boutique.ErreurArchive) else 502,
                            f"Réouverture impossible : {erreur}") from exc
    finally:
        _effacer(chemin)
        await db.verrous.delete_one({"_id": verrou})

    # Fiche : celle de l'archive, réactivée, avec une nouvelle échéance (aujourd'hui ; la
    # formule éventuellement payée en même temps la repousse ensuite)
    jour = aujourd_hui()
    fiche = resultat["fiche"]
    ab = dict(fiche.get("abonnement") or {})
    ab.update({"en_essai": False, "echeance": (jour - timedelta(days=1) if formule else jour).isoformat()})
    historique = (cv.get("historique") or [])[-10:] + [{k: v for k, v in cv.items() if k != "historique"}]
    fiche.update({"actif": True, "suspension": None, "abonnement": ab, "grace_prolongations": None,
                  "cycle_vie": {"statut": STATUT_REOUVERT, "echeance": ab["echeance"], "avertissements": {},
                                "reouvert_le": now_iso(), "reouverture_id": reouverture["id"],
                                "historique": historique}})
    await db.boutiques.replace_one({"id": boutique_id}, fiche)
    paiement = None
    if formule:
        paiement = await abonnements.enregistrer_paiement(boutique_id, formule, int(montant_abonnement), mode,
                                                          reference=f"Réouverture {reference}"[:120],
                                                          saisi_par=admin.get("email", ""))
    await db.cycle_vie_reouvertures.update_one({"id": reouverture["id"]}, {"$set": {
        "statut": "TERMINEE", "documents": resultat["documents"], "avertissements": resultat["avertissements"],
        "paiement_abonnement": (paiement or {}).get("id")}})
    await journaliser(boutique, "REOUVERTURE", par=admin.get("email", ""), montant=int(montant), mode=mode,
                      devise=p["frais_devise"], documents=resultat["documents"])
    return {"reouverture": {**reouverture, "statut": "TERMINEE"}, "restauration": {k: v for k, v in resultat.items()
                                                                                   if k != "fiche"},
            "boutique": await db.boutiques.find_one({"id": boutique_id}, SANS_ID)}


# ---------------------------------------------------------------------------
# Écran d'administration
# ---------------------------------------------------------------------------
async def etat() -> dict:
    jour = aujourd_hui()
    concernees = []
    async for b in db.boutiques.find({"test": {"$ne": True}}, SANS_ID).sort("nom", 1):
        cal = calendrier(b, jour)
        # Boutiques engagées dans le cycle, ou à moins de 30 jours du premier avertissement
        if cal["etape"] == "NORMALE" and cal["jours_depuis_echeance"] < J_AVERTISSEMENT - 30:
            continue
        concernees.append({"id": b["id"], "nom": b.get("nom", ""), "code_marchand": b.get("code_marchand", ""),
                           "actif": b.get("actif", True), "test": bool(b.get("test")), **cal,
                           "actions_dues": actions_dues(b, jour)})
    return {"jour": jour.isoformat(), "parametres": await parametres(), "boutiques": concernees,
            "archives": await db.cycle_vie_archives.find({}, SANS_ID).sort("date", -1).to_list(200),
            "executions": await db.cycle_vie_executions.find({}, {"_id": 0}).sort("debut", -1).to_list(15),
            "alertes": await db.cycle_vie_journal.find({"niveau": "ALERTE"}, SANS_ID).sort("date", -1).to_list(10),
            "r2_configure": sauvegarde_auto.r2_configure(), "phrase_configuree": bool(sauvegarde_auto.phrase()),
            "calendrier": {"avertissement": J_AVERTISSEMENT, "suspension": J_SUSPENSION,
                           "dernier_avis": J_DERNIER_AVIS, "archivage": J_ARCHIVAGE},
            "prefixe_archives": prefixe_archives(), "bucket": bucket()}


async def journal(limite: int = 100) -> list[dict]:
    return await db.cycle_vie_journal.find({}, SANS_ID).sort("date", -1).to_list(limite)
