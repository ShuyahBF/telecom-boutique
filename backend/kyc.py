"""Dossier d'identification (KYC) d'une boutique : identité du DG, pièce
d'identité, IFU, CNSS, registre du commerce, géolocalisation.

Les pièces justificatives sont des données SENSIBLES : rangées dans le
stockage privé, jamais exposées par une adresse publique, consultables
uniquement par l'administrateur de la plateforme et le DG de la boutique.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from db import SANS_ID, db
from storage import (chemin_local_prive, enregistrer_prive, lien_temporaire_prive, lire_document,
                     supprimer_prive)
from utils import new_id, now_iso

TYPES_PIECES_KYC = {
    "PIECE_IDENTITE_DG": "Pièce d'identité du DG",
    "RCCM": "Registre du commerce (RCCM)",
    "IFU": "Attestation IFU",
    "CNSS": "Attestation CNSS",
    "AUTRE": "Autre justificatif",
}
STATUTS_KYC = {"NON_FOURNI": "Non fourni", "EN_ATTENTE": "En attente de vérification",
               "VERIFIE": "Vérifié", "REJETE": "Rejeté"}


def kyc_vide() -> dict:
    return {"statut": "NON_FOURNI", "motif_rejet": "", "documents": [], "verifie_par": "", "date_verification": None}


# Lot D — champs de l'analyse IA réservés à l'équipe adLyn (scores, comparaison des
# visages, motifs détaillés de la revue) : jamais renvoyés au commerçant
CHAMPS_IA_EQUIPE = ("visage", "motifs_revue", "confiance", "seuil", "seuil_visage", "comparaison", "erreur_ia")


def revue_requise(kyc: dict) -> bool:
    """Lot D — vrai si le dossier attend la décision d'un humain (file « KYC à vérifier »).
    Dossiers du lot C (sans l'indicateur) : en attente après une lecture par l'IA,
    sans nouvelle photo demandée au commerçant."""
    if "revue_humaine_requise" in kyc:
        return bool(kyc["revue_humaine_requise"])
    return kyc.get("statut") == "EN_ATTENTE" and bool(kyc.get("ia")) and not kyc.get("nouvelle_photo")


def kyc_public(kyc: Optional[dict], super_admin: bool = False) -> dict:
    """Version renvoyée au navigateur : sans les clés de stockage des fichiers.
    Lot D : `super_admin=False` (commerçant) retire aussi les scores de l'IA, la comparaison
    des visages et le détail des motifs de la revue humaine."""
    kyc = kyc or kyc_vide()
    public = {**kyc, "statut_libelle": STATUTS_KYC.get(kyc.get("statut"), ""),
              "documents": [{k: v for k, v in d.items() if k != "cle"} for d in kyc.get("documents", [])],
              "revue_humaine_requise": revue_requise(kyc)}
    # Lot C — dernière lecture par l'IA : seul le numéro MASQUÉ de la pièce peut sortir
    # (protection supplémentaire : le numéro complet n'est de toute façon jamais enregistré)
    if isinstance(public.get("ia"), dict) and isinstance(public["ia"].get("lecture"), dict):
        public["ia"] = {**public["ia"], "lecture": {k: v for k, v in public["ia"]["lecture"].items()
                                                   if k != "numero_piece"}}
    if not super_admin:
        # Lot D — commerçant : ni scores, ni analyse des visages, ni motifs détaillés
        if isinstance(public.get("ia"), dict):
            ia = {k: v for k, v in public["ia"].items() if k not in CHAMPS_IA_EQUIPE}
            if isinstance(ia.get("lecture"), dict):
                ia["lecture"] = {k: v for k, v in ia["lecture"].items() if k != "confiance"}
            public["ia"] = ia
        public.pop("revue", None)
    return public


async def ajouter_piece(boutique: dict, fichier: UploadFile, type_piece: str, auteur: str,
                        super_admin: bool = False) -> dict:
    if type_piece not in TYPES_PIECES_KYC:
        raise HTTPException(400, "Type de justificatif inconnu")
    contenu, type_mime = await lire_document(fichier)
    cle = await enregistrer_prive(boutique["id"], contenu, type_mime)
    piece = {"id": new_id(), "type": type_piece, "libelle": TYPES_PIECES_KYC[type_piece],
             "nom_fichier": (fichier.filename or "")[:150], "format": type_mime, "cle": cle,
             "ajoute_par": auteur, "date": now_iso()}
    kyc = boutique.get("kyc") or kyc_vide()
    kyc["documents"] = [*kyc.get("documents", []), piece]
    # Toute nouvelle pièce doit être (re)vérifiée par l'administrateur
    kyc.update({"statut": "EN_ATTENTE", "motif_rejet": ""})
    await db.boutiques.update_one({"id": boutique["id"]}, {"$set": {"kyc": kyc}})
    return kyc_public(kyc, super_admin=super_admin)


async def retirer_piece(boutique: dict, piece_id: str, super_admin: bool = False) -> dict:
    kyc = boutique.get("kyc") or kyc_vide()
    piece = next((d for d in kyc.get("documents", []) if d["id"] == piece_id), None)
    if not piece:
        raise HTTPException(404, "Justificatif introuvable")
    kyc["documents"] = [d for d in kyc["documents"] if d["id"] != piece_id]
    if not kyc["documents"]:
        kyc["statut"] = "NON_FOURNI"
    await db.boutiques.update_one({"id": boutique["id"]}, {"$set": {"kyc": kyc}})
    await supprimer_prive(piece.get("cle"))
    return kyc_public(kyc, super_admin=super_admin)


async def ouvrir_piece(boutique: dict, piece_id: str, super_admin: bool = False):
    """Accès au fichier, APRÈS contrôle des droits par la route appelante :
    lien temporaire (R2) ou envoi direct du fichier (mode local)."""
    piece = next((d for d in (boutique.get("kyc") or {}).get("documents", []) if d["id"] == piece_id), None)
    if not piece:
        raise HTTPException(404, "Justificatif introuvable")
    # Lot D — la photo du visage (selfie, donnée biométrique) est réservée à l'équipe adLyn
    if piece.get("type") == "SELFIE_DG" and not super_admin:
        raise HTTPException(403, "Photo de vérification réservée à l'équipe adLyn")
    lien = await lien_temporaire_prive(piece["cle"])
    if lien:
        return RedirectResponse(lien)
    chemin = chemin_local_prive(piece["cle"])
    if not chemin.exists():
        raise HTTPException(404, "Fichier introuvable")
    return FileResponse(chemin, media_type=piece["format"], filename=piece.get("nom_fichier") or None)


async def boutique_ou_404(boutique_id: str) -> dict:
    b = await db.boutiques.find_one({"id": boutique_id}, SANS_ID)
    if not b:
        raise HTTPException(404, "Boutique introuvable")
    return b
