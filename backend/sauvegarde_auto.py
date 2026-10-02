"""Sauvegarde GÉNÉRALE automatique de la plateforme (règle R3), en plus des
sauvegardes de chaque boutique (taches_nocturnes.py, Google Drive).

  - Chaque nuit, un « Cron Job » Render appelle POST /api/sauvegarde-auto/declencher
    avec l'en-tête secret X-Sauvegarde-Jeton (comparé à SAUVEGARDE_AUTO_JETON à temps
    constant). Le serveur gratuit pouvant dormir, c'est cet appel qui le réveille.
  - La route répond tout de suite ; le travail se fait en tâche de fond et une seule
    fois par jour (idempotence : un document par jour dans « sauvegardes_generales » ;
    une journée en échec peut être relancée).
  - Contenu : export COMPLET de la base, au même format chiffré que l'export manuel
    (fichier .adlexport, transfert_donnees.py + chiffrement_flux.py), avec la phrase
    secrète SAUVEGARDE_AUTO_PHRASE (variable d'environnement, jamais en base). Sans
    phrase valable, la sauvegarde générale est DÉSACTIVÉE et une alerte s'affiche.
  - Destination : Cloudflare R2, avec les identifiants R2 DÉJÀ utilisés pour les images
    (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY), dans le bucket
    ADLYN_SAUVEGARDES_BUCKET (à défaut R2_BUCKET_PRIVE), sous le préfixe
    ADLYN_SAUVEGARDES_PREFIXE (« sauvegardes-generales/ »).
  - Rétention : 7 quotidiennes + 4 hebdomadaires + 12 mensuelles (la plus récente de
    chaque jour / semaine / mois) ; les autres fichiers sont supprimés de R2.
  - Rapport par e-mail (envois_plateforme.envoyer_email, serveur SMTP de la plateforme)
    à RAPPORT_EMAIL ; alerte dans l'administration si la dernière réussite a plus de 26 h.
  - Restauration depuis R2 : import « Remplacer » de transfert_donnees.py (mot de passe
    du super-administrateur + mot REMPLACER), suivi par la page « Transfert ».
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import chiffrement_flux
import transfert_donnees
from config import get_settings
from db import SANS_ID, db
from utils import new_id, now_iso

logger = logging.getLogger(__name__)

RETENTION = {"quotidiennes": 7, "hebdomadaires": 4, "mensuelles": 12}
ALERTE_HEURES = 26
BLOCAGE_EN_COURS = timedelta(hours=3)  # une tâche « en cours » plus vieille est considérée comme interrompue
MOTIF_NOM = re.compile(r"adlyn-auto_(\d{4}-\d{2}-\d{2})_(\d{6})\.adlexport$")
UTILISATEUR_SYSTEME = {"id": None, "email": "sauvegarde-automatique"}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def jour_local(maintenant: Optional[datetime] = None) -> str:
    return (maintenant or _maintenant()).astimezone(ZoneInfo(get_settings().fuseau_horaire)).date().isoformat()


def phrase() -> Optional[str]:
    """Phrase de chiffrement valable, ou None (sauvegarde générale désactivée)."""
    brute = get_settings().sauvegarde_auto_phrase
    if not brute:
        return None
    try:
        return chiffrement_flux.valider_phrase(brute, brute)
    except chiffrement_flux.ErreurChiffrement:
        return None


def r2_configure() -> bool:
    s = get_settings()
    return bool(s.r2_account_id and s.r2_access_key_id and s.r2_secret_access_key)


def bucket() -> str:
    s = get_settings()
    return s.adlyn_sauvegardes_bucket or s.r2_bucket_prive


def prefixe() -> str:
    p = get_settings().adlyn_sauvegardes_prefixe or ""
    return p if not p or p.endswith("/") else p + "/"


def verifier_jeton(recu: Optional[str]) -> None:
    """En-tête X-Sauvegarde-Jeton comparé à SAUVEGARDE_AUTO_JETON (temps constant)."""
    attendu = get_settings().sauvegarde_auto_jeton
    if not attendu:
        raise HTTPException(503, "Sauvegarde automatique non configurée (SAUVEGARDE_AUTO_JETON manquant)")
    if not recu or not hmac.compare_digest(recu.encode("utf-8"), attendu.encode("utf-8")):
        raise HTTPException(401, "Jeton de sauvegarde invalide")


# ---------------------------------------------------------------------------
# Stockage R2 (remplacé par un faux stockage en mémoire dans les tests)
# ---------------------------------------------------------------------------
class StockageR2:
    """Opérations sur les sauvegardes générales dans R2 (client S3 du stockage existant)."""

    def __init__(self):
        from storage import _r2_client  # mêmes identifiants R2 que les images

        self._client = _r2_client()
        self._bucket = bucket()

    async def envoyer(self, cle: str, chemin: str) -> None:
        await asyncio.to_thread(self._client.upload_file, chemin, self._bucket, cle)

    async def lister(self, prefixe_: str) -> list[dict]:
        def _lister():
            resultat, jeton = [], None
            while True:
                args = {"Bucket": self._bucket, "Prefix": prefixe_, **({"ContinuationToken": jeton} if jeton else {})}
                page = self._client.list_objects_v2(**args)
                for o in page.get("Contents", []):
                    resultat.append({"cle": o["Key"], "taille": o.get("Size", 0),
                                     "date": o["LastModified"].isoformat() if o.get("LastModified") else None})
                if not page.get("IsTruncated"):
                    return resultat
                jeton = page.get("NextContinuationToken")

        return await asyncio.to_thread(_lister)

    async def supprimer(self, cle: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=cle)

    async def telecharger(self, cle: str, chemin: str) -> None:
        await asyncio.to_thread(self._client.download_file, self._bucket, cle, chemin)


def stockage():
    if not r2_configure():
        raise RuntimeError("Cloudflare R2 non configuré (R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY)")
    return StockageR2()


# ---------------------------------------------------------------------------
# Rétention 7 / 4 / 12
# ---------------------------------------------------------------------------
def a_conserver(cles: list[str]) -> set[str]:
    """Clés à garder : la plus récente de chacun des 7 derniers jours, des 4 dernières
    semaines (ISO) et des 12 derniers mois. Un fichier au nom inconnu n'est jamais supprimé."""
    datees, garder = [], set()
    for cle in cles:
        m = MOTIF_NOM.search(cle)
        if not m:
            garder.add(cle)
            continue
        datees.append((date.fromisoformat(m.group(1)), m.group(2), cle))
    datees.sort(reverse=True)
    for nombre, periode in ((RETENTION["quotidiennes"], lambda d: d),
                            (RETENTION["hebdomadaires"], lambda d: tuple(d.isocalendar())[:2]),
                            (RETENTION["mensuelles"], lambda d: (d.year, d.month))):
        vues = []
        for d, _, cle in datees:
            p = periode(d)
            if p in vues:
                continue
            if len(vues) >= nombre:
                break
            vues.append(p)
            garder.add(cle)
    return garder


async def appliquer_retention(stock) -> int:
    fichiers = await stock.lister(prefixe())
    garder = a_conserver([f["cle"] for f in fichiers])
    supprimes = 0
    for f in fichiers:
        if f["cle"] not in garder:
            await stock.supprimer(f["cle"])
            supprimes += 1
    return supprimes


# ---------------------------------------------------------------------------
# Déclenchement (idempotent sur la journée) et exécution
# ---------------------------------------------------------------------------
async def reserver_jour(jour: str) -> Optional[dict]:
    """Réserve la sauvegarde du jour ; None si elle est déjà faite ou en cours.
    Une journée en échec (ou bloquée « en cours » depuis plus de 3 h) peut être relancée."""
    doc = {"_id": jour, "jour": jour, "statut": "EN_COURS", "debut": now_iso(), "tentatives": 1}
    try:
        await db.sauvegardes_generales.insert_one(doc.copy())
        return doc
    except DuplicateKeyError:
        pass
    limite = (_maintenant() - BLOCAGE_EN_COURS).isoformat()
    reprise = await db.sauvegardes_generales.find_one_and_update(
        {"_id": jour, "$or": [{"statut": "ECHEC"}, {"statut": "EN_COURS", "debut": {"$lt": limite}}]},
        {"$set": {"statut": "EN_COURS", "debut": now_iso(), "erreur": ""}, "$inc": {"tentatives": 1}},
        return_document=ReturnDocument.AFTER)
    return reprise


async def noter_desactivee() -> None:
    """Appel reçu sans phrase de chiffrement valable : noté pour l'alerte de l'administration."""
    await db.parametres_plateforme.update_one({"_id": "sauvegarde_auto_desactivee"}, {"$set": {"date": now_iso()}},
                                              upsert=True)


async def executer(jour: str, declencheur: str = "cron") -> dict:
    """Export complet chiffré -> R2 -> rétention -> rapport. Le résultat est enregistré
    dans le document du jour (collection sauvegardes_generales)."""
    resultat = {"statut": "ECHEC", "fichier": "", "cle": "", "taille": 0, "documents": 0, "purges": 0, "erreur": "",
                "declencheur": declencheur}
    chemin = ""
    try:
        secret = phrase()
        if not secret:
            raise RuntimeError("SAUVEGARDE_AUTO_PHRASE absente ou trop courte : sauvegarde générale désactivée")
        stock = stockage()
        horodatage = datetime.now(ZoneInfo(get_settings().fuseau_horaire)).strftime("%H%M%S")
        nom = f"adlyn-auto_{jour}_{horodatage}{transfert_donnees.EXTENSION}"
        chemin = str(transfert_donnees.DOSSIER / f"auto-{new_id()}{transfert_donnees.EXTENSION}")
        # Même export que l'export manuel (tâche « privée », hors liste des transferts de l'écran)
        tache = {"id": f"auto-{jour}", "type": "export", "statut": "EN_COURS", "etape": "", "progression": 0,
                 "documents_traites": 0, "documents_total": 0, "fichier_nom": nom, "_chemin": chemin}
        await transfert_donnees._executer_export(tache, secret, UTILISATEUR_SYSTEME, "sauvegarde-auto")  # noqa: SLF001
        if tache["statut"] != "TERMINE":
            raise RuntimeError(tache.get("erreur") or "Export en échec")
        cle = prefixe() + nom
        await stock.envoyer(cle, chemin)
        resultat.update({"statut": "SUCCES", "fichier": nom, "cle": cle, "taille": tache.get("taille", 0),
                         "documents": (tache.get("rapport") or {}).get("documents", 0)})
        resultat["purges"] = await appliquer_retention(stock)
    except Exception as exc:  # noqa: BLE001 — l'échec est enregistré et rapporté
        logger.exception("Sauvegarde générale automatique en échec")
        resultat["erreur"] = str(getattr(exc, "detail", None) or exc)[:500]
    finally:
        if chemin:
            try:
                os.remove(chemin)  # jamais de copie laissée sur le disque du serveur
            except FileNotFoundError:
                pass
    resultat["fin"] = now_iso()
    resultat["rapport"] = await envoyer_rapport(jour, resultat)
    await db.sauvegardes_generales.update_one({"_id": jour}, {"$set": resultat}, upsert=True)
    return resultat


async def envoyer_rapport(jour: str, r: dict) -> dict:
    """Rapport par e-mail avec le mécanisme d'envoi existant (SMTP de la plateforme)."""
    import envois_plateforme

    s = get_settings()
    ok = r["statut"] == "SUCCES"
    sujet = f"[adLyn] Sauvegarde générale du {jour} : {'réussie' if ok else 'ÉCHEC'}"
    corps = (f"Sauvegarde générale automatique du {jour}\n\n"
             + (f"Fichier : {r['fichier']} ({r['taille']} octets, {r['documents']} documents)\n"
                f"Emplacement : R2 {bucket()}/{r['cle']}\nAnciennes sauvegardes supprimées : {r['purges']}\n"
                if ok else f"Erreur : {r['erreur']}\n"))
    if not s.rapport_email:
        return {"statut": "NON_CONFIGURE", "erreur": "RAPPORT_EMAIL non configuré"}
    statut, erreur = await envois_plateforme.envoyer_email(sujet, corps, s.rapport_email)
    return {"statut": statut, "erreur": erreur}


# ---------------------------------------------------------------------------
# État (administration, alerte) et dernière sauvegarde (Mon compte)
# ---------------------------------------------------------------------------
async def derniere_reussite() -> Optional[dict]:
    docs = await db.sauvegardes_generales.find({"statut": "SUCCES"}, SANS_ID).sort("fin", -1).to_list(1)
    return docs[0] if docs else None


async def etat() -> dict:
    s = get_settings()
    derniere = await derniere_reussite()
    alertes = []
    if not phrase():
        alertes.append("Sauvegarde générale DÉSACTIVÉE : variable SAUVEGARDE_AUTO_PHRASE absente ou trop courte "
                       f"({chiffrement_flux.PHRASE_MIN} caractères minimum).")
    if not s.sauvegarde_auto_jeton:
        alertes.append("Variable SAUVEGARDE_AUTO_JETON absente : le Cron Job ne peut pas déclencher la sauvegarde.")
    if not r2_configure():
        alertes.append("Cloudflare R2 non configuré : la sauvegarde générale ne peut pas être envoyée.")
    if not derniere:
        alertes.append("Aucune sauvegarde générale réussie n'est enregistrée.")
    elif _maintenant() - datetime.fromisoformat(derniere["fin"]) > timedelta(hours=ALERTE_HEURES):
        alertes.append(f"La dernière sauvegarde générale réussie date de plus de {ALERTE_HEURES} h.")
    historique = await db.sauvegardes_generales.find({}, SANS_ID).sort("jour", -1).to_list(30)
    return {"active": bool(phrase()), "jeton_configure": bool(s.sauvegarde_auto_jeton), "r2_configure": r2_configure(),
            "bucket": bucket(), "prefixe": prefixe(), "retention": RETENTION, "derniere_reussite": derniere,
            "alerte": bool(alertes), "alertes": alertes, "historique": historique}


async def lister_r2() -> list[dict]:
    fichiers = await stockage().lister(prefixe())
    return sorted(fichiers, key=lambda f: f["cle"], reverse=True)


class _FichierLocal:
    """Adaptateur « fichier envoyé » pour transfert_donnees.preparer_import (lecture par morceaux)."""

    def __init__(self, chemin: str, nom: str):
        self.filename = nom
        self._f = open(chemin, "rb")  # noqa: SIM115 — fermé par fermer()

    async def read(self, taille: int = -1) -> bytes:
        return await asyncio.to_thread(self._f.read, taille)

    def fermer(self) -> None:
        self._f.close()


async def restaurer(cle: str, user: dict, ip: str) -> dict:
    """Télécharge une sauvegarde générale depuis R2 puis lance l'import « Remplacer »
    (contrôles du mot de passe et du mot REMPLACER faits par la route)."""
    secret = phrase()
    if not secret:
        raise HTTPException(503, "SAUVEGARDE_AUTO_PHRASE absente : impossible de déchiffrer la sauvegarde")
    if not cle.startswith(prefixe()) or not MOTIF_NOM.search(cle):
        raise HTTPException(400, "Sauvegarde inconnue")
    stock = stockage()
    if cle not in {f["cle"] for f in await stock.lister(prefixe())}:
        raise HTTPException(404, "Sauvegarde introuvable dans R2")
    chemin = str(transfert_donnees.DOSSIER / f"restauration-{new_id()}{transfert_donnees.EXTENSION}")
    await stock.telecharger(cle, chemin)
    fichier = _FichierLocal(chemin, cle.rsplit("/", 1)[-1])
    try:
        return await transfert_donnees.preparer_import(user, fichier, secret, "remplacer", ip)
    finally:
        fichier.fermer()
        try:
            os.remove(chemin)
        except FileNotFoundError:
            pass


def _texte_date(iso: Optional[str]) -> Optional[dict]:
    if not iso:
        return None
    d = datetime.fromisoformat(iso)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return {"date": iso, "texte": d.astimezone(ZoneInfo(get_settings().fuseau_horaire)).strftime("%d/%m/%Y %H:%M")}


async def dernieres_sauvegardes(boutique_id: Optional[str]) -> dict:
    """Pour « Mon compte » et le pied de page : dernière sauvegarde générale et dernière
    sauvegarde réussie de la boutique (Google Drive ou avant restauration)."""
    generale = await derniere_reussite()
    resultat = {"generale": _texte_date(generale["fin"]) if generale else None, "boutique": None,
                "a_une_boutique": bool(boutique_id)}
    if boutique_id:
        docs = await db.sauvegardes.find({"boutique_id": boutique_id, "statut": "SUCCES"}, SANS_ID) \
            .sort("date", -1).to_list(1)
        resultat["boutique"] = _texte_date(docs[0]["date"]) if docs else None
    return resultat
