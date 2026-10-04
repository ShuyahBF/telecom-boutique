"""Maintenance des équipements confiés (ordinateurs, imprimantes, onduleurs, écrans…).

À ne pas confondre avec le SAV des téléphones (routes/maintenance.py, dossiers
MNT-AAAA-00001, pièces sorties du stock, suivi public) : ici, un client confie un
MATÉRIEL pour diagnostic et réparation, et chaque dépôt est une FICHE :
  - numéro automatique MNT-<CODE>-<AAAA>-0001 (par espace et par année) ;
  - client, date de réception, type de matériel (liste par défaut + ajouts de
    l'espace), marque / modèle / n° de série, état à la réception (mauvais,
    moyen, bon), motif du dépôt ;
  - diagnostic, remplacement de pièces (oui / non + pièces), observations,
    équipe (noms, texte libre), prix du diagnostic (10 000 FCFA par défaut) ;
  - dates d'entrée en atelier et de sortie ; statut reçu -> en diagnostic ->
    en réparation -> prêt -> rendu (« rendu » dès qu'une date de sortie est portée) ;
  - photos de l'équipement ou des pièces (JPEG / PNG, 5 Mo, 12 au plus),
    annotées dans le navigateur avant l'envoi ;
  - envoi de la fiche par WhatsApp, lien de paiement Mobile Money (PawaPay),
    facturation.

DEUX ESPACES, même logique :
  1. PLATEFORME (super-administrateur adLyn) : /api/plateforme/maintenance-equipements
     Le client est une BOUTIQUE adLyn ; son téléphone est celui qui reçoit les
     messages de la plateforme (téléphone du DG, sinon celui de la boutique),
     modifiable. Le paiement est encaissé pour la plateforme (non reversé) ;
     la facture est une facture adLyn imprimable (numéro FMT-AAAA-00001).
  2. BOUTIQUE : /api/maintenance-equipements
     Fonction ACTIVÉE boutique par boutique par l'administrateur (champ
     `maintenance_equipements` de la boutique), réservée aux rôles qui ont la
     permission « maintenance ». Le client est un client de la boutique (fiche
     Clients) ou saisi librement. Le paiement Mobile Money suit la règle des
     commandes (dossier KYC validé) et entre dans les reversements ; « Facturer »
     crée une facture ou une proforma dans « Factures & proformas ».

Les données sont cloisonnées comme partout ailleurs (TenantDB) : l'espace de la
plateforme utilise l'identifiant réservé « plateforme ».

Collections : maintenance_fiches, maintenance_types, compteurs (+ paiements, documents).
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import date
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

import envois_plateforme as envois
from auth import Contexte, get_super_admin, permission
from config import get_settings
from db import SANS_ID, TenantDB, db
from routes.documents import creer_document
from routes.tiers import trouver_ou_creer_client
from storage import enregistrer_image, supprimer_image
from utils import motif_recherche, new_id, normaliser_telephone, now_iso

logger = logging.getLogger(__name__)

boutique = APIRouter(prefix="/maintenance-equipements", tags=["Maintenance des équipements (boutique)"])
admin = APIRouter(prefix="/plateforme/maintenance-equipements", tags=["Maintenance des équipements (super-admin)"])
public = APIRouter(prefix="/public/maintenance-paiement", tags=["Maintenance des équipements (paiement public)"])

# Identifiant réservé de l'espace de la plateforme (jamais un identifiant de boutique)
ESPACE_PLATEFORME = "plateforme"
TYPES_PAR_DEFAUT = ["Ordinateur portable", "Ordinateur de bureau", "Imprimante", "Onduleur", "Écran",
                    "Téléphone", "Tablette", "Serveur", "Équipement réseau", "Autre"]
ETATS = {"mauvais": "Mauvais", "moyen": "Moyen", "bon": "Bon"}
STATUTS = ("recu", "diagnostic", "reparation", "pret", "rendu")
LIBELLES_STATUT = {"recu": "Reçu", "diagnostic": "En diagnostic", "reparation": "En réparation",
                   "pret": "Prêt à rendre", "rendu": "Rendu"}
PHOTOS_MAX = 12
PHOTO_MAX_OCTETS = 5 * 1024 * 1024  # limite de WhatsApp pour une image
TYPES_PHOTO = ("image/jpeg", "image/png")  # formats acceptés par WhatsApp
DATE = r"^\d{4}-\d{2}-\d{2}$"


def fonction_active(b: Optional[dict]) -> bool:
    """La boutique a-t-elle la fonction « Maintenance des équipements » (activée par l'administrateur) ?"""
    return bool((b or {}).get("maintenance_equipements"))


def encaissement_possible(b: dict) -> bool:
    """Même règle que les commandes en ligne : encaissement Mobile Money seulement pour une
    boutique réelle, au dossier d'identification (KYC) validé, qui accepte le Mobile Money."""
    return (b.get("kyc") or {}).get("statut") == "VERIFIE" and not b.get("test") and b.get("paiement_mobile_money") is not False


# ---------------------------------------------------------------------------
# Espace de travail : plateforme (super-admin) ou boutique
# ---------------------------------------------------------------------------
class Espace:
    """Ce dont les routes ont besoin : l'espace (données cloisonnées), l'utilisateur
    et, côté boutique, le contexte habituel (pour la facturation)."""

    def __init__(self, espace_id: str, user: dict, ctx: Optional[Contexte] = None):
        self.id = espace_id
        self.user = user
        self.ctx = ctx
        self.tdb = TenantDB(espace_id)

    @property
    def plateforme(self) -> bool:
        return self.ctx is None

    @property
    def boutique(self) -> Optional[dict]:
        return self.ctx.boutique if self.ctx else None

    @property
    def emetteur(self) -> str:
        return self.boutique["nom"] if self.boutique else "adLyn"

    @property
    def code(self) -> str:
        return (self.boutique or {}).get("code_marchand") or "ADLYN"

    @property
    def devise(self) -> str:
        return (self.boutique or {}).get("devise") or "FCFA"

    @property
    def auteur(self) -> str:
        return self.user.get("nom") or self.user.get("email") or ""


async def espace_boutique(ctx: Contexte = Depends(permission("maintenance"))) -> Espace:
    if not fonction_active(ctx.boutique):
        raise HTTPException(403, "La fonction « Maintenance des équipements » n'est pas activée pour votre boutique. "
                                 "Demandez son activation à l'administrateur adLyn.")
    return Espace(ctx.boutique["id"], ctx.user, ctx)


async def espace_plateforme(user: dict = Depends(get_super_admin)) -> Espace:
    return Espace(ESPACE_PLATEFORME, user)


# ---------------------------------------------------------------------------
# Saisies
# ---------------------------------------------------------------------------
class FicheIn(BaseModel):
    boutique_client_id: Optional[str] = None  # plateforme : la boutique cliente
    client_id: Optional[str] = None  # boutique : un client de la fiche Clients
    client_nom: Optional[str] = Field(None, max_length=160)
    client_telephone: Optional[str] = Field(None, max_length=40)
    date_reception: Optional[str] = Field(None, pattern=DATE)
    type_materiel: str = Field(..., min_length=1, max_length=80)
    marque_modele: Optional[str] = Field(None, max_length=160)
    numero_serie: Optional[str] = Field(None, max_length=80)
    etat_materiel: Literal["mauvais", "moyen", "bon"] = "moyen"
    motif: str = Field(..., min_length=1, max_length=2000)
    diagnostic: Optional[str] = Field(None, max_length=4000)
    remplacement_pieces: bool = False
    pieces: Optional[str] = Field(None, max_length=2000)
    observations: Optional[str] = Field(None, max_length=2000)
    date_entree: Optional[str] = Field(None, pattern=DATE)
    date_sortie: Optional[str] = Field(None, pattern=DATE)
    statut: Optional[Literal["recu", "diagnostic", "reparation", "pret", "rendu"]] = None
    prix_diagnostic: Optional[int] = Field(None, ge=0, le=100_000_000)  # vide = prix par défaut
    equipe: Optional[str] = Field(None, max_length=300)  # noms des intervenants, texte libre


class TypeIn(BaseModel):
    libelle: str = Field(..., min_length=2, max_length=80)


class EnvoiWhatsAppIn(BaseModel):
    # auto : modèle Meta s'il est configuré, sinon message libre
    mode: Literal["auto", "texte", "modele"] = "auto"
    # modèle à utiliser : sans en-tête (texte) ou avec la 1re photo en en-tête image
    modele: Literal["texte", "image"] = "texte"
    message: Optional[str] = Field(None, max_length=3000)
    photos: bool = True
    inclure_lien_paiement: bool = True


class LienPaiementIn(BaseModel):
    montant: Optional[int] = Field(None, gt=0, le=100_000_000)  # par défaut : prix du diagnostic


class LigneIn(BaseModel):
    designation: str = Field(..., min_length=1, max_length=255)
    quantite: float = Field(1, gt=0)
    prix_unitaire: int = Field(..., ge=0)


class FacturerIn(BaseModel):
    type_document: Literal["FAC", "PRO"] = "FAC"  # proforma : espace boutique seulement
    lignes: list[LigneIn] = Field(default_factory=list, max_length=30)  # en plus du diagnostic


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------
def statut_de(fiche: dict) -> str:
    """Statut affiché : « rendu » dès qu'une date de sortie est portée ; sinon celui choisi."""
    if fiche.get("date_sortie"):
        return "rendu"
    return fiche.get("statut") if fiche.get("statut") in STATUTS[:-1] else "recu"


def montant_fr(n: Any) -> str:
    """10000 -> « 10 000 » (espaces des milliers)."""
    try:
        return f"{int(round(float(n or 0))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def materiel(f: dict) -> str:
    return f"{f.get('type_materiel')}" + (f" {f['marque_modele']}" if f.get("marque_modele") else "")


def texte_fiche(f: dict, emetteur: str, devise: str = "FCFA", lien_paiement: Optional[str] = None) -> str:
    """Résumé de la fiche envoyé par WhatsApp (message libre)."""
    lignes = [f"*Fiche de maintenance {f.get('numero')}* — {emetteur}",
              f"Client : {f.get('client_nom') or '—'}",
              f"Matériel : {f.get('type_materiel')}" + (f" — {f['marque_modele']}" if f.get("marque_modele") else "")]
    if f.get("numero_serie"):
        lignes.append(f"N° de série : {f['numero_serie']}")
    lignes += [f"Reçu le : {(f.get('date_reception') or '')[:10]}",
               f"État à la réception : {ETATS.get(f.get('etat_materiel'), '—')}",
               f"Motif : {f.get('motif')}",
               f"Statut : {LIBELLES_STATUT.get(statut_de(f), '—')}"]
    if f.get("diagnostic"):
        lignes.append(f"Diagnostic : {f['diagnostic']}")
    if f.get("remplacement_pieces"):
        lignes.append(f"Pièces à remplacer : {f.get('pieces') or 'oui'}")
    if f.get("equipe"):
        lignes.append(f"Équipe : {f['equipe']}")
    if f.get("date_sortie"):
        lignes.append(f"Restitué le : {f['date_sortie'][:10]}")
    lignes.append(f"Prix du diagnostic : *{montant_fr(f.get('prix_diagnostic'))} {devise}*")
    if f.get("observations"):
        lignes.append(f"Observations : {f['observations']}")
    if lien_paiement:
        lignes.append(f"\nPayer par Mobile Money : {lien_paiement}")
    return "\n".join(lignes)


def _variable_meta(texte: Any, longueur: int = 300) -> str:
    """Variable d'un modèle Meta : pas de retour à la ligne ni de tabulation, jamais vide."""
    propre = re.sub(r"\s+", " ", str(texte or "")).strip()
    return propre[:longueur] or "—"


async def _compteur(espace_id: str, prefixe: str) -> tuple[int, int]:
    """Prochain numéro (année, rang) de l'espace pour ce préfixe : $inc atomique, repart à 1 chaque année."""
    annee = date.today().year
    c = await db.compteurs.find_one_and_update(
        {"boutique_id": espace_id, "prefixe": prefixe, "annee": annee}, {"$inc": {"dernier": 1}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return annee, c["dernier"]


async def _numero(espace: Espace) -> str:
    annee, n = await _compteur(espace.id, "MNT-EQ")
    return f"MNT-{espace.code}-{annee}-{n:04d}"


def _telephone_alertes(b: dict) -> str:
    """Numéro d'une boutique qui reçoit les messages de la plateforme (rappels d'abonnement…)."""
    return b.get("dg_telephone") or b.get("telephone") or ""


async def _client(espace: Espace, data: FicheIn) -> dict:
    """Client de la fiche : boutique (plateforme), client de la boutique, ou saisi librement."""
    tel_saisi = normaliser_telephone(data.client_telephone)
    if data.boutique_client_id:
        if not espace.plateforme:
            raise HTTPException(403, "Seul l'administrateur adLyn choisit une boutique comme client")
        b = await db.boutiques.find_one({"id": data.boutique_client_id}, SANS_ID)
        if not b:
            raise HTTPException(400, "Boutique introuvable")
        return {"boutique_client_id": b["id"], "client_id": None, "client_nom": b["nom"],
                "client_code": b.get("code_marchand", ""),
                "client_telephone": tel_saisi or normaliser_telephone(_telephone_alertes(b))}
    if data.client_id:
        if espace.plateforme:
            raise HTTPException(400, "Choisissez une boutique ou saisissez le client")
        c = await espace.tdb.clients.find_one({"id": data.client_id})
        if not c:
            raise HTTPException(400, "Client introuvable dans votre fichier clients")
        return {"boutique_client_id": None, "client_id": c["id"], "client_nom": c["nom"], "client_code": "",
                "client_telephone": tel_saisi or c.get("telephone", "")}
    if not (data.client_nom or "").strip():
        raise HTTPException(400, "Indiquez le client (choisi dans la liste ou saisi)")
    return {"boutique_client_id": None, "client_id": None, "client_nom": data.client_nom.strip(), "client_code": "",
            "client_telephone": tel_saisi}


def _champs(data: FicheIn) -> dict:
    d = data.model_dump(exclude={"boutique_client_id", "client_id", "client_nom", "client_telephone"})
    for k in ("marque_modele", "numero_serie", "diagnostic", "pieces", "observations", "equipe"):
        d[k] = (d.get(k) or "").strip() or None
    d["type_materiel"] = d["type_materiel"].strip()
    d["motif"] = d["motif"].strip()
    if d["prix_diagnostic"] is None:
        d["prix_diagnostic"] = get_settings().maintenance_prix_diagnostic
    if d.get("date_sortie") and d.get("date_entree") and d["date_sortie"] < d["date_entree"]:
        raise HTTPException(400, "La date de sortie précède la date d'entrée")
    return d


async def _fiche(espace: Espace, fid: str) -> dict:
    f = await espace.tdb.maintenance_fiches.find_one({"id": fid})
    if not f:
        raise HTTPException(404, "Fiche introuvable")
    f["statut"] = statut_de(f)
    return f


# ---------------------------------------------------------------------------
# Routes communes aux deux espaces
# ---------------------------------------------------------------------------
def _enregistrer_routes(router: APIRouter, dependance) -> None:
    """Déclare les mêmes routes pour l'espace plateforme et l'espace boutique.
    Les chemins fixes (/types, /clients) sont déclarés AVANT /{fid}."""

    # ---- Types de matériel (liste par défaut + ajouts de l'espace) ----
    @router.get("/types")
    async def types(espace: Espace = Depends(dependance)):
        ajoutes = await espace.tdb.maintenance_types.find().sort("libelle", 1).to_list(200)
        return {"defaut": TYPES_PAR_DEFAUT, "ajoutes": ajoutes,
                # « Autre » reste en dernier
                "tous": TYPES_PAR_DEFAUT[:-1] + [t["libelle"] for t in ajoutes] + TYPES_PAR_DEFAUT[-1:],
                "prix_diagnostic_defaut": get_settings().maintenance_prix_diagnostic}

    @router.post("/types", status_code=201)
    async def ajouter_type(data: TypeIn, espace: Espace = Depends(dependance)):
        libelle = data.libelle.strip()
        existants = [t.lower() for t in TYPES_PAR_DEFAUT] + [
            t["libelle"].lower() async for t in espace.tdb.maintenance_types.find({}, {"libelle": 1})]
        if libelle.lower() in existants:
            raise HTTPException(409, "Ce type existe déjà")
        doc = {"id": new_id(), "libelle": libelle, "cree_le": now_iso(), "cree_par": espace.auteur}
        await espace.tdb.maintenance_types.insert_one(doc)
        return {**doc, "boutique_id": espace.id}

    @router.delete("/types/{tid}")
    async def supprimer_type(tid: str, espace: Espace = Depends(dependance)):
        r = await espace.tdb.maintenance_types.delete_one({"id": tid})
        if not r.deleted_count:
            raise HTTPException(404, "Type introuvable")
        return {"ok": True}

    # ---- Clients proposés : boutiques (plateforme) ou clients de la boutique ----
    @router.get("/clients")
    async def clients(espace: Espace = Depends(dependance)):
        if espace.plateforme:
            boutiques = await db.boutiques.find({}, {"_id": 0, "id": 1, "nom": 1, "code_marchand": 1, "telephone": 1,
                                                     "dg_telephone": 1}).sort("nom", 1).to_list(3000)
            items = [{"type": "boutique", "id": b["id"], "nom": b["nom"], "code": b.get("code_marchand", ""),
                      "telephone": _telephone_alertes(b)} for b in boutiques]
            return {"type": "boutique", "items": items}
        liste = await espace.tdb.clients.find({}, {"_id": 0, "id": 1, "nom": 1, "telephone": 1}).sort("nom", 1).to_list(5000)
        return {"type": "client", "items": [{"type": "client", "id": c["id"], "nom": c["nom"], "code": "",
                                             "telephone": c.get("telephone", "")} for c in liste]}

    # ---- Services disponibles (affichage des boutons de la fiche) ----
    @router.get("/services")
    async def services(espace: Espace = Depends(dependance)):
        from routes.paiements import paiement_disponible

        modeles = modeles_configures()
        canal = canal_whatsapp()
        # Modèles Meta : seulement avec le WABA de la plateforme (Liluvine gère elle-même la fenêtre de 24 h)
        return {"whatsapp": canal is not None, "canal_whatsapp": canal,
                "modele_texte": canal == "waba" and bool(modeles["texte"]),
                "modele_image": canal == "waba" and bool(modeles["image"]),
                "paiement": paiement_disponible() and (espace.plateforme or encaissement_possible(espace.boutique)),
                "facturation": espace.plateforme or espace.ctx.peut("facturation"),
                "suppression": espace.user.get("role") in ("dg", "super_admin")}

    # ---- Fiches ----
    @router.get("")
    async def lister(q: str = "", statut: str = "", type_materiel: str = "", espace: Espace = Depends(dependance)):
        filtre: dict = {}
        if type_materiel:
            filtre["type_materiel"] = type_materiel
        if q.strip():
            motif = motif_recherche(q)
            filtre["$or"] = [{k: {"$regex": motif, "$options": "i"}} for k in
                             ("numero", "client_nom", "client_telephone", "marque_modele", "numero_serie", "motif")]
        fiches = await espace.tdb.maintenance_fiches.find(filtre).sort("date_reception", -1).to_list(1000)
        for f in fiches:
            f["statut"] = statut_de(f)
        compte = {s: 0 for s in STATUTS}
        for f in fiches:
            compte[f["statut"]] += 1
        if statut:
            fiches = [f for f in fiches if f["statut"] == statut]
        return {"fiches": fiches, "compte": compte}

    @router.post("", status_code=201)
    async def creer(data: FicheIn, espace: Espace = Depends(dependance)):
        doc = {"id": new_id(), "numero": await _numero(espace), **await _client(espace, data), **_champs(data),
               "photos": [], "lien_paiement": None, "facture": None, "envois_whatsapp": [],
               "cree_par": espace.auteur, "cree_le": now_iso(), "maj_le": now_iso()}
        doc["date_reception"] = doc.get("date_reception") or now_iso()[:10]
        doc["statut"] = statut_de(doc)
        await espace.tdb.maintenance_fiches.insert_one(doc)
        return {**doc, "boutique_id": espace.id}

    @router.get("/{fid}")
    async def lire(fid: str, espace: Espace = Depends(dependance)):
        return await _fiche(espace, fid)

    @router.put("/{fid}")
    async def modifier(fid: str, data: FicheIn, espace: Espace = Depends(dependance)):
        await _fiche(espace, fid)
        maj = {**await _client(espace, data), **_champs(data), "maj_le": now_iso(), "maj_par": espace.auteur}
        maj["statut"] = statut_de(maj)
        await espace.tdb.maintenance_fiches.update_one({"id": fid}, {"$set": maj})
        return await _fiche(espace, fid)

    @router.delete("/{fid}")
    async def supprimer(fid: str, espace: Espace = Depends(dependance)):
        f = await _fiche(espace, fid)
        # Côté boutique, seul le DG supprime une fiche (le super-admin a tous les droits)
        if espace.user.get("role") not in ("dg", "super_admin"):
            raise HTTPException(403, "Seul le DG de la boutique peut supprimer une fiche")
        if (f.get("lien_paiement") or {}).get("paye") or (f.get("facture") and f["facture"].get("type_document") == "FAC"):
            raise HTTPException(409, "Fiche payée ou facturée : elle ne peut plus être supprimée")
        await espace.tdb.maintenance_fiches.delete_one({"id": fid})
        for p in f.get("photos") or []:
            try:
                await supprimer_image(espace.id, p.get("url"))
            except Exception:  # noqa: BLE001 — une photo restée sur le stockage ne bloque pas la suppression
                logger.warning("Photo de la fiche %s non supprimée du stockage", f["numero"])
        return {"ok": True}

    # ---- Photos (annotées dans le navigateur avant l'envoi) ----
    @router.post("/{fid}/photos", status_code=201)
    async def ajouter_photo(fid: str, fichier: UploadFile = File(...), espace: Espace = Depends(dependance)):
        f = await _fiche(espace, fid)
        if len(f.get("photos") or []) >= PHOTOS_MAX:
            raise HTTPException(400, f"{PHOTOS_MAX} photos au maximum par fiche")
        type_contenu = (fichier.content_type or "").lower()
        if type_contenu not in TYPES_PHOTO:
            raise HTTPException(400, "Photo JPEG ou PNG uniquement (formats acceptés par WhatsApp)")
        contenu = await fichier.read(PHOTO_MAX_OCTETS + 1)
        if len(contenu) > PHOTO_MAX_OCTETS:
            raise HTTPException(400, "Photo trop lourde : 5 Mo au maximum")
        # Rangée dans le dossier de l'espace (R2 en production : adresse publique https lue par WhatsApp)
        url = await enregistrer_image(espace.id, "maintenance", contenu, type_contenu)
        extension = "png" if type_contenu == "image/png" else "jpg"
        photo = {"id": new_id(), "url": url, "nom": (fichier.filename or f"photo.{extension}")[:120],
                 "ajoutee_le": now_iso(), "par": espace.auteur}
        await espace.tdb.maintenance_fiches.update_one({"id": fid}, {"$push": {"photos": photo}, "$set": {"maj_le": now_iso()}})
        return photo

    @router.delete("/{fid}/photos/{pid}")
    async def supprimer_photo(fid: str, pid: str, espace: Espace = Depends(dependance)):
        f = await _fiche(espace, fid)
        photo = next((p for p in f.get("photos") or [] if p["id"] == pid), None)
        if not photo:
            raise HTTPException(404, "Photo introuvable")
        await espace.tdb.maintenance_fiches.update_one({"id": fid}, {"$pull": {"photos": {"id": pid}}})
        try:
            await supprimer_image(espace.id, photo["url"])
        except Exception:  # noqa: BLE001
            logger.warning("Photo %s non supprimée du stockage", pid)
        return {"ok": True}

    # ---- Lien de paiement Mobile Money (PawaPay) ----
    @router.post("/{fid}/lien-paiement")
    async def creer_lien_paiement(fid: str, data: LienPaiementIn, espace: Espace = Depends(dependance)):
        from routes.paiements import paiement_disponible

        f = await _fiche(espace, fid)
        if not paiement_disponible():
            raise HTTPException(503, "Le paiement Mobile Money n'est pas encore configuré sur la plateforme")
        if espace.boutique is not None and not encaissement_possible(espace.boutique):
            raise HTTPException(400, "Le paiement Mobile Money n'est pas disponible pour votre boutique "
                                     "(dossier d'identification à faire valider par adLyn)")
        if (f.get("lien_paiement") or {}).get("paye"):
            raise HTTPException(409, "Cette fiche est déjà payée")
        montant = int(data.montant or f.get("prix_diagnostic") or 0)
        if montant <= 0:
            raise HTTPException(400, "Indiquez un prix de diagnostic ou un montant")
        jeton = secrets.token_urlsafe(18)
        lien = {"jeton": jeton, "url": f"{get_settings().public_site_url}/paiement/maintenance/{jeton}",
                "montant": montant, "devise": espace.devise, "paye": False, "statut": "NON_PAYE",
                "cree_le": now_iso(), "cree_par": espace.auteur}
        await espace.tdb.maintenance_fiches.update_one({"id": fid}, {"$set": {"lien_paiement": lien}})
        return lien

    # ---- Envoi de la fiche par WhatsApp ----
    @router.post("/{fid}/whatsapp")
    async def envoyer_whatsapp(fid: str, data: EnvoiWhatsAppIn, espace: Espace = Depends(dependance)):
        f = await _fiche(espace, fid)
        return await _envoyer_whatsapp(espace, f, data)

    # ---- Facturation ----
    @router.post("/{fid}/facturer")
    async def facturer(fid: str, data: FacturerIn, espace: Espace = Depends(dependance)):
        f = await _fiche(espace, fid)
        if espace.plateforme:
            return await _facturer_plateforme(espace, f, data)
        return await _facturer_boutique(espace, f, data)


# ---------------------------------------------------------------------------
# WhatsApp : API Cloud de Meta (numéro de la plateforme) ou, à défaut,
# Transmission WA Universelle Liluvine (SAWALI)
# ---------------------------------------------------------------------------
def canal_whatsapp() -> Optional[str]:
    """Canal d'envoi de la fiche : « waba » (numéro WhatsApp de la plateforme),
    sinon « liluvine » (transmission universelle), sinon None (rien de branché)."""
    import transmission_wa

    if envois.whatsapp_configure():
        return "waba"
    return "liluvine" if transmission_wa.liluvine_configure() else None


async def _poster_whatsapp(corps: dict) -> tuple[bool, str]:
    s = get_settings()
    url = envois.WA_GRAPH_URL.format(phone_number_id=s.whatsapp_phone_number_id)
    try:
        async with httpx.AsyncClient(timeout=20) as client_http:
            r = await client_http.post(url, json=corps, headers={"Authorization": f"Bearer {s.whatsapp_access_token}"})
    except httpx.HTTPError as exc:
        return False, repr(exc)[:200]
    if r.status_code == 200:
        return True, ""
    return False, f"HTTP {r.status_code} {r.text[:200]}"


def modeles_configures() -> dict:
    """Modèles Meta de la fiche : sans en-tête (texte) et avec en-tête image (1re photo)."""
    s = get_settings()
    return {"texte": (s.whatsapp_maintenance_template or "").strip(),
            "image": (s.whatsapp_maintenance_template_image or "").strip()}


async def _envoyer_whatsapp(espace: Espace, f: dict, data: EnvoiWhatsAppIn) -> dict:
    """Envoi de la fiche au numéro de la fiche.
    adLyn ne reçoit pas les messages WhatsApp entrants : il ne peut donc pas savoir si le
    client a écrit dans les dernières 24 h. « auto » choisit le MODÈLE Meta s'il est
    configuré (seul moyen fiable hors fenêtre de 24 h), sinon le message libre (texte +
    photos, qui ne passe que si le client a écrit au numéro adLyn dans les 24 h).
    Sans WABA de la plateforme, la fiche part par la Transmission WA Universelle Liluvine
    (texte + une image par message) ; si le WABA échoue (hors numéro invalide), repli Liluvine."""
    canal = canal_whatsapp()
    if canal is None:
        raise HTTPException(503, "WhatsApp n'est pas encore branché sur la plateforme adLyn")
    numero = envois.msisdn(f.get("client_telephone") or "")
    if not numero:
        raise HTTPException(400, "Numéro WhatsApp du client manquant ou invalide sur la fiche")
    modeles = modeles_configures()
    mode = data.mode
    if canal == "liluvine":
        # Sans WABA : la transmission universelle envoie le texte et les photos ; c'est SAWALI
        # qui choisit message direct ou modèle selon la fenêtre de 24 h (pas de modèle Meta ici)
        mode = "texte"
    elif mode == "auto":
        mode = "modele" if modeles[data.modele] else "texte"
    # Lien de paiement joint seulement s'il reste à payer
    lien_paiement = f.get("lien_paiement") or {}
    lien = lien_paiement.get("url") if data.inclure_lien_paiement and not lien_paiement.get("paye") else None
    # Photos envoyables : adresse publique https (WhatsApp va les chercher lui-même)
    photos = [p for p in (f.get("photos") or []) if (p.get("url") or "").startswith("https://")] if data.photos else []
    rapport: dict = {"mode": mode, "canal": canal, "texte": False, "photos_envoyees": 0, "photos_non_envoyees": 0,
                     "erreurs": []}

    if mode == "modele":
        nom = modeles[data.modele]
        if not nom:
            raise HTTPException(400, "Aucun modèle Meta configuré pour la fiche de maintenance "
                                     + ("avec en-tête image (WHATSAPP_MAINTENANCE_TEMPLATE_IMAGE)" if data.modele == "image"
                                        else "(WHATSAPP_MAINTENANCE_TEMPLATE)"))
        if data.modele == "image" and not photos:
            # Meta refuse un modèle à en-tête image envoyé sans image : message clair avant l'envoi
            raise HTTPException(400, "Ce modèle a un en-tête image, mais la fiche n'a aucune photo publiée "
                                     "(ou « Joindre les photos » est décoché). Ajoutez une photo à la fiche, "
                                     "ou choisissez le modèle sans en-tête image.")

    if espace.boutique and espace.boutique.get("test"):
        # Boutique de démonstration : aucun message réel ne part (comme le carrousel)
        rapport.update({"non_envoye": True, "erreurs": ["Envoi désactivé pour cette boutique"]})
        return rapport

    if canal == "liluvine":
        # Pas de WABA : tout part par la Transmission WA Universelle Liluvine
        corps_texte = (data.message or "").strip() or texte_fiche(f, espace.emetteur, espace.devise, lien)
        await _envoyer_par_liluvine(espace, f, numero, corps_texte, photos, rapport, "liluvine")
    elif mode == "texte":
        corps_texte = (data.message or "").strip() or texte_fiche(f, espace.emetteur, espace.devise, lien)
        ok, erreur = await _poster_whatsapp({"messaging_product": "whatsapp", "to": numero, "type": "text",
                                             "text": {"body": corps_texte[:4000]}})
        if not ok:
            # WABA en échec (fenêtre de 24 h…) : repli par Liluvine si possible (protocole v3, section 4)
            if not await _repli_liluvine(espace, f, numero, corps_texte, photos, rapport, erreur):
                raise HTTPException(502, f"Envoi refusé par WhatsApp : {erreur}")
            return await _tracer_envoi(espace, f, rapport, numero, modeles, data)
        rapport["texte"] = True
        for i, p in enumerate(photos, 1):
            ok, erreur = await _poster_whatsapp({"messaging_product": "whatsapp", "to": numero, "type": "image",
                                                 "image": {"link": p["url"], "caption": f"{f['numero']} — photo {i}/{len(photos)}"}})
            if ok:
                rapport["photos_envoyees"] += 1
            else:
                rapport["erreurs"].append(f"Photo {i} : {erreur}")
    else:
        # Structure attendue du modèle (voir config.py) : 6 variables dans le corps
        variables = [espace.emetteur, f["numero"], materiel(f), LIBELLES_STATUT.get(statut_de(f), ""),
                     f"{montant_fr(f.get('prix_diagnostic'))} {espace.devise}", lien or "—"]
        composants: list = []
        if data.modele == "image":
            composants.append({"type": "header", "parameters": [{"type": "image", "image": {"link": photos[0]["url"]}}]})
        composants.append({"type": "body", "parameters": [{"type": "text", "text": _variable_meta(v)} for v in variables]})
        ok, erreur = await _poster_whatsapp({
            "messaging_product": "whatsapp", "to": numero, "type": "template",
            "template": {"name": modeles[data.modele], "language": {"code": get_settings().whatsapp_template_langue},
                         "components": composants}})
        if not ok:
            # Modèle refusé (non approuvé, panne…) : repli par Liluvine avec le texte complet de la fiche
            corps_texte = texte_fiche(f, espace.emetteur, espace.devise, lien)
            if not await _repli_liluvine(espace, f, numero, corps_texte, photos, rapport, erreur):
                raise HTTPException(502, f"Envoi refusé par WhatsApp : {erreur}")
            return await _tracer_envoi(espace, f, rapport, numero, modeles, data)
        rapport["texte"] = True
        rapport["photos_envoyees"] = 1 if data.modele == "image" else 0
        # Hors fenêtre de 24 h, WhatsApp refuse les images libres : les autres photos partiront
        # par un envoi « message libre » quand le client aura répondu
        rapport["photos_non_envoyees"] = len(photos) - rapport["photos_envoyees"]

    return await _tracer_envoi(espace, f, rapport, numero, modeles, data)


async def _tracer_envoi(espace: Espace, f: dict, rapport: dict, numero: str, modeles: dict,
                        data: EnvoiWhatsAppIn) -> dict:
    """Trace de l'envoi sur la fiche (30 dernières), puis rapport renvoyé à l'écran."""
    mode = rapport["mode"]
    trace = {"le": now_iso(), "par": espace.auteur, "mode": mode, "canal": rapport.get("canal"), "telephone": numero,
             "photos": rapport["photos_envoyees"], "modele": modeles[data.modele] if mode == "modele" else None}
    await espace.tdb.maintenance_fiches.update_one({"id": f["id"]}, {"$push": {"envois_whatsapp": {"$each": [trace], "$slice": -30}}})
    return rapport


async def _repli_liluvine(espace: Espace, f: dict, numero: str, corps_texte: str, photos: list, rapport: dict,
                          erreur: str) -> bool:
    """Repli quand le WABA de la plateforme échoue (protocole v3, section 4) : seulement si
    Liluvine est configurée et que l'erreur ne vient pas d'un numéro invalide.
    Renvoie False si le repli n'est pas permis (l'appelant garde alors l'erreur WABA)."""
    import transmission_wa

    if not transmission_wa.liluvine_configure() or not transmission_wa.repli_autorise(erreur):
        return False
    rapport.update({"mode": "texte", "erreur_waba": (erreur or "")[:300]})
    await _envoyer_par_liluvine(espace, f, numero, corps_texte, photos, rapport, "liluvine_repli")
    return True


async def _envoyer_par_liluvine(espace: Espace, f: dict, numero: str, corps_texte: str, photos: list,
                                rapport: dict, canal: str) -> None:
    """Fiche envoyée par la Transmission WA Universelle Liluvine :
      - sans photo : un seul message texte ;
      - avec photos : UN MESSAGE PAR IMAGE ; la 1re porte le texte de la fiche en légende
        (si le texte dépasse la limite d'une légende WhatsApp, 1 024 caractères, il part
        d'abord seul, puis chaque photo avec une légende courte).
    Le 1er message en échec arrête l'envoi (409 si le client s'est désinscrit, sinon 502)."""
    import transmission_wa

    rapport["canal"] = canal
    source = transmission_wa.source_par_defaut(espace.boutique)
    boutique_id = (espace.boutique or {}).get("id")

    async def _un_envoi(texte: str, photo: Optional[dict] = None, legende: Optional[str] = None) -> dict:
        media = {"type": "image", "url": photo["url"], "legende": legende} if photo else None
        return await transmission_wa.envoyer_liluvine(numero, texte, source=source, media=media, canal=canal,
                                                      boutique_id=boutique_id)

    def _echec(res: dict) -> None:
        if res.get("desinscrit"):
            raise HTTPException(409, "Le client s'est désinscrit des messages WhatsApp (il a répondu STOP)")
        raise HTTPException(502, f"Envoi refusé par la transmission WhatsApp : {res.get('erreur')}")

    texte_en_legende = bool(photos) and len(corps_texte) <= transmission_wa.LEGENDE_MAX
    # 1) Texte seul (pas de photo, ou texte trop long pour une légende)
    if not texte_en_legende:
        res = await _un_envoi(corps_texte[:transmission_wa.LONGUEUR_MAX])
        if not res["ok"]:
            _echec(res)
        rapport["texte"] = True
    # 2) Une image par message (la 1re porte le texte de la fiche si elle tient en légende)
    for i, p in enumerate(photos, 1):
        courte = f"{f['numero']} — photo {i}/{len(photos)}"
        legende = corps_texte if (texte_en_legende and i == 1) else courte
        res = await _un_envoi(legende, p, legende)
        if res["ok"]:
            rapport["photos_envoyees"] += 1
            if texte_en_legende and i == 1:
                rapport["texte"] = True
        elif texte_en_legende and i == 1:
            _echec(res)  # le message qui porte le texte de la fiche n'est pas parti
        else:
            rapport["erreurs"].append(f"Photo {i} : {res.get('erreur')}")


# ---------------------------------------------------------------------------
# Facturation
# ---------------------------------------------------------------------------
def _lignes_facture(f: dict, data: FacturerIn) -> list[dict]:
    lignes = []
    if f.get("prix_diagnostic"):
        lignes.append({"designation": f"Diagnostic {materiel(f)} — fiche {f['numero']}"[:255],
                       "quantite": 1, "prix_unitaire": int(f["prix_diagnostic"])})
    lignes += [{"designation": l.designation.strip(), "quantite": l.quantite, "prix_unitaire": l.prix_unitaire}
               for l in data.lignes if l.designation.strip()]
    if not lignes:
        raise HTTPException(400, "Rien à facturer : indiquez un prix de diagnostic ou des lignes")
    return lignes


async def _facturer_boutique(espace: Espace, f: dict, data: FacturerIn) -> dict:
    """Facture (brouillon, numérotée à la validation) ou proforma dans « Factures & proformas »."""
    ctx = espace.ctx
    if not ctx.peut("facturation"):
        raise HTTPException(403, "La facturation est réservée au DG, aux commerciaux et au comptable")
    if data.type_document == "FAC" and (f.get("facture") or {}).get("type_document") == "FAC":
        existante = await ctx.tdb.documents.find_one({"id": f["facture"]["id"]})
        if existante and existante.get("statut") != "ANNULE":
            raise HTTPException(409, "Cette fiche a déjà une facture")
    lignes = _lignes_facture(f, data)
    # Client de la facture : sa fiche Clients, retrouvée par téléphone ou créée
    client = await ctx.tdb.clients.find_one({"id": f["client_id"]}) if f.get("client_id") else None
    if client is None and f.get("client_telephone"):
        client = await trouver_ou_creer_client(ctx.tdb, f["client_nom"], f["client_telephone"])
    if client is None:
        client = {"id": new_id(), "type_client": "PART", "nom": f["client_nom"], "telephone": "", "email": "",
                  "adresse": "", "ifu": "", "notes": f"Créé depuis la fiche de maintenance {f['numero']}",
                  "created_at": now_iso()}
        await ctx.tdb.clients.insert_one(client)
    doc = await creer_document(ctx, data.type_document, client, lignes, f"Maintenance {materiel(f)} — fiche {f['numero']}",
                               origine={"fiche_maintenance_origine": {"id": f["id"], "numero": f["numero"]}})
    ref = {"id": doc["id"], "type_document": data.type_document, "numero": doc.get("numero"),
           "montant": doc.get("total_ttc"), "le": now_iso()}
    maj: dict = {"client_id": client["id"]}
    if data.type_document == "FAC" or not (f.get("facture") or {}).get("type_document") == "FAC":
        maj["facture"] = ref
    await ctx.tdb.maintenance_fiches.update_one({"id": f["id"]}, {"$set": maj})
    return ref


async def _facturer_plateforme(espace: Espace, f: dict, data: FacturerIn) -> dict:
    """Facture adLyn adressée à la boutique cliente (numéro FMT-AAAA-00001), imprimable
    depuis la fiche. Il n'existe pas de module de facturation générale de la plateforme :
    la facture est conservée sur la fiche elle-même."""
    if data.type_document != "FAC":
        raise HTTPException(400, "Espace adLyn : seule une facture peut être émise (pas de proforma)")
    if f.get("facture"):
        raise HTTPException(409, f"Fiche déjà facturée ({f['facture']['numero']})")
    lignes = [{**l, "montant": int(round(l["quantite"] * l["prix_unitaire"]))} for l in _lignes_facture(f, data)]
    b = await db.boutiques.find_one({"id": f["boutique_client_id"]}, SANS_ID) if f.get("boutique_client_id") else None
    client = {"nom": f["client_nom"], "telephone": f.get("client_telephone", ""), "code_marchand": (b or {}).get("code_marchand", ""),
              "adresse": ", ".join(x for x in ((b or {}).get("adresse"), (b or {}).get("ville"), (b or {}).get("pays")) if x),
              "ifu": (b or {}).get("ifu", ""), "rccm": (b or {}).get("rccm", "")}
    annee, n = await _compteur(ESPACE_PLATEFORME, "FMT")
    facture = {"id": new_id(), "type_document": "FAC", "numero": f"FMT-{annee}-{n:05d}", "date": now_iso()[:10],
               "client": client, "lignes": lignes, "montant": sum(l["montant"] for l in lignes), "devise": "FCFA",
               "le": now_iso(), "par": espace.auteur}
    await espace.tdb.maintenance_fiches.update_one({"id": f["id"]}, {"$set": {"facture": facture}})
    return facture


_enregistrer_routes(boutique, espace_boutique)
_enregistrer_routes(admin, espace_plateforme)


# ---------------------------------------------------------------------------
# Page publique du lien de paiement (le jeton, imprévisible, fait office de clé)
# ---------------------------------------------------------------------------
async def _fiche_du_jeton(jeton: str) -> dict:
    f = await db.maintenance_fiches.find_one({"lien_paiement.jeton": jeton}, SANS_ID) if len(jeton) >= 16 else None
    if not f:
        raise HTTPException(404, "Lien de paiement introuvable ou remplacé")
    return f


async def _emetteur(f: dict) -> Optional[dict]:
    """Boutique qui a émis la fiche (None pour l'espace de la plateforme)."""
    if f["boutique_id"] == ESPACE_PLATEFORME:
        return None
    return await db.boutiques.find_one({"id": f["boutique_id"]}, SANS_ID)


class PaiementPublicIn(BaseModel):
    telephone: str = Field("", max_length=30)


@public.get("/{jeton}")
async def lire_lien(jeton: str):
    from routes.paiements import paiement_disponible

    f = await _fiche_du_jeton(jeton)
    b = await _emetteur(f)
    lien = f["lien_paiement"]
    # Rien de confidentiel : pas de téléphone, pas de diagnostic détaillé
    return {"numero": f["numero"], "emetteur": b["nom"] if b else "adLyn", "client_nom": f.get("client_nom", ""),
            "materiel": materiel(f), "montant": lien["montant"], "devise": lien.get("devise", "FCFA"),
            "paye": bool(lien.get("paye")), "disponible": paiement_disponible()}


@public.post("/{jeton}")
async def payer_lien(jeton: str, payload: PaiementPublicIn):
    from routes.paiements import creer_page_maintenance

    f = await _fiche_du_jeton(jeton)
    if f["lien_paiement"].get("paye"):
        raise HTTPException(409, "Cette fiche est déjà payée")
    return {"url": await creer_page_maintenance(f, await _emetteur(f), payload.telephone)}
