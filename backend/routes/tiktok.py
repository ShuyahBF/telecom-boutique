"""Routes TikTok d'une boutique : connexion de SON compte TikTok, publication
des photos de ses produits, suivi des publications.

Droits : connecter / déconnecter = DG (« parametres ») ; publier = catalogue
(« catalogue.edition ») ; consulter l'état = tout le personnel.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

import tiktok
from auth import Contexte, permission, tout_le_personnel
from config import get_settings
from db import TenantDB
from storage import enregistrer_image
from utils import new_id, now_iso

router = APIRouter(prefix="/tiktok", tags=["TikTok"])
parametres = permission("parametres")
edition = permission("catalogue.edition")

Visibilite = Literal["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"]


def _configure_ou_503() -> None:
    if not tiktok.configure():
        raise HTTPException(503, "TikTok n'est pas encore configuré sur la plateforme (TIKTOK_CLIENT_KEY / SECRET)")


async def _compte(tdb: TenantDB) -> dict | None:
    return await tdb.tiktok_comptes.find_one({})


async def _jeton_valide(tdb: TenantDB) -> str:
    """Jeton d'accès utilisable (renouvelé automatiquement s'il expire dans moins de 5 minutes)."""
    compte = await _compte(tdb)
    if not compte:
        raise HTTPException(409, "Aucun compte TikTok n'est connecté à cette boutique")
    expire = datetime.fromisoformat(compte["expire_le"])
    if expire - datetime.now(timezone.utc) > timedelta(minutes=5):
        return tiktok.dechiffrer(compte["access_token"])
    reponse = await tiktok.rafraichir(tiktok.dechiffrer(compte["refresh_token"]))
    await tdb.tiktok_comptes.update_one({}, {"$set": {**tiktok.fiche_jetons(reponse), "modifie_le": now_iso()}})
    return reponse["access_token"]


# ---------------------------------------------------------------------------
# Connexion du compte
# ---------------------------------------------------------------------------
@router.get("/etat")
async def etat(ctx: Contexte = Depends(tout_le_personnel)):
    compte = await _compte(ctx.tdb)
    return {
        "configure": tiktok.configure(),
        "connecte": bool(compte),
        "compte": {k: compte.get(k) for k in ("display_name", "avatar_url", "connecte_le")} if compte else None,
    }


@router.get("/connexion")
async def demarrer_connexion(ctx: Contexte = Depends(parametres)):
    """Adresse de la page d'autorisation TikTok (le site y envoie le DG)."""
    _configure_ou_503()
    return {"url": tiktok.url_autorisation(tiktok.etat_signe(ctx.boutique["id"], ctx.user["id"]))}


@router.get("/callback")
async def retour_tiktok(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    """Retour de TikTok après autorisation. La boutique est lue dans l'état SIGNÉ."""
    retour = f"{get_settings().public_site_url}/gestion/parametres?onglet=reseaux&"
    if error:
        return RedirectResponse(f"{retour}tiktok=refuse")
    donnees = tiktok.lire_etat(state)
    if not donnees or not code:
        return RedirectResponse(f"{retour}tiktok=erreur")
    tdb = TenantDB(donnees["b"])
    try:
        jetons = await tiktok.echanger_code(code)
        infos = await tiktok.profil(jetons["access_token"])
    except (HTTPException, httpx.HTTPError, KeyError):
        return RedirectResponse(f"{retour}tiktok=erreur")
    await tdb.tiktok_comptes.delete_many({})  # un seul compte TikTok par boutique
    await tdb.tiktok_comptes.insert_one({
        **tiktok.fiche_jetons(jetons), "display_name": infos.get("display_name"), "avatar_url": infos.get("avatar_url"),
        "connecte_par": donnees["u"], "connecte_le": now_iso(), "modifie_le": now_iso()})
    return RedirectResponse(f"{retour}tiktok=connecte")


@router.post("/deconnexion")
async def deconnecter(ctx: Contexte = Depends(parametres)):
    compte = await _compte(ctx.tdb)
    if compte and tiktok.configure():
        try:
            await tiktok.revoquer(tiktok.dechiffrer(compte["access_token"]))
        except HTTPException:
            pass
    await ctx.tdb.tiktok_comptes.delete_many({})  # jetons supprimés de la base
    return {"ok": True}


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------
@router.get("/createur")
async def createur(ctx: Contexte = Depends(edition)):
    """Infos du compte à afficher dans l'écran de publication (appelé à chaque ouverture)."""
    _configure_ou_503()
    return await tiktok.infos_createur(await _jeton_valide(ctx.tdb))


class Publication(BaseModel):
    produit_id: str = Field(min_length=1, max_length=64)
    titre: str = Field(min_length=1, max_length=90)
    description: str = Field(default="", max_length=4000)
    visibilite: Visibilite
    autoriser_commentaires: bool = False
    contenu_commercial: bool = False
    ma_marque: bool = False  # « Your brand » -> Contenu promotionnel
    contenu_sponsorise: bool = False  # « Branded content » -> Partenariat rémunéré
    accord: bool = False  # l'utilisateur a accepté la déclaration TikTok


@router.post("/publications", status_code=201)
async def publier(data: Publication, ctx: Contexte = Depends(edition)):
    _configure_ou_503()
    # Règles de l'écran de publication, revérifiées côté serveur
    if not data.accord:
        raise HTTPException(400, "Acceptez la déclaration TikTok avant de publier")
    if data.contenu_commercial and not (data.ma_marque or data.contenu_sponsorise):
        raise HTTPException(400, "Contenu commercial : cochez « Ma marque » et/ou « Contenu sponsorisé »")
    if data.contenu_sponsorise and data.visibilite == "SELF_ONLY":
        raise HTTPException(400, "Un contenu sponsorisé ne peut pas être publié en « Moi uniquement »")
    produit = await ctx.tdb.produits.find_one({"id": data.produit_id})
    if not produit:
        raise HTTPException(404, "Produit introuvable")
    if not produit.get("image_url"):
        raise HTTPException(400, "Ce produit n'a pas de photo à publier")

    jeton = await _jeton_valide(ctx.tdb)
    createur_infos = await tiktok.infos_createur(jeton)
    if data.visibilite not in (createur_infos.get("privacy_level_options") or []):
        raise HTTPException(400, "Cette visibilité n'est pas autorisée pour ce compte TikTok")
    commentaires_bloques = bool(createur_infos.get("comment_disabled"))

    # Copie JPEG ≤ 1080 px de la photo (format exigé par TikTok), sans aucun ajout
    try:
        jpeg = tiktok.photo_pour_tiktok(await tiktok.telecharger(produit["image_url"]))
    except Exception as exc:  # image illisible ou injoignable
        raise HTTPException(400, "Photo du produit illisible : remplacez-la puis réessayez") from exc
    url_photo = await enregistrer_image(ctx.boutique["id"], "tiktok", jpeg, "image/jpeg")

    publish_id = await tiktok.publier_photos(
        jeton, urls=[url_photo], titre=data.titre.strip(), description=data.description.strip(),
        visibilite=data.visibilite, desactiver_commentaires=commentaires_bloques or not data.autoriser_commentaires,
        ma_marque=data.contenu_commercial and data.ma_marque,
        contenu_sponsorise=data.contenu_commercial and data.contenu_sponsorise)
    publication = {
        "id": new_id(), "produit_id": produit["id"], "produit_nom": produit.get("nom"), "publish_id": publish_id,
        "visibilite": data.visibilite, "statut": "PROCESSING_DOWNLOAD", "photo_url": url_photo,
        "publie_par": ctx.user["id"], "cree_le": now_iso(),
    }
    await ctx.tdb.tiktok_publications.insert_one(publication)
    return publication


@router.get("/publications")
async def lister_publications(produit_id: str = Query(default=""), ctx: Contexte = Depends(tout_le_personnel)):
    filtre = {"produit_id": produit_id} if produit_id else {}
    return await ctx.tdb.tiktok_publications.find(filtre).sort("cree_le", -1).to_list(50)


@router.get("/publications/{publication_id}/statut")
async def actualiser_statut(publication_id: str, ctx: Contexte = Depends(tout_le_personnel)):
    """État de la publication chez TikTok (traitement, publiée, échec)."""
    pub = await ctx.tdb.tiktok_publications.find_one({"id": publication_id})
    if not pub:
        raise HTTPException(404, "Publication introuvable")
    if pub["statut"] in ("PUBLISH_COMPLETE", "FAILED"):
        return pub
    infos = await tiktok.statut_publication(await _jeton_valide(ctx.tdb), pub["publish_id"])
    maj = {"statut": infos.get("status", pub["statut"]), "raison_echec": infos.get("fail_reason"), "verifie_le": now_iso()}
    return await ctx.tdb.tiktok_publications.find_one_and_update({"id": publication_id}, {"$set": maj})
