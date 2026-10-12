"""Lot E — liens de partage de la boutique (page d'accueil de la vitrine) et des produits.

Le DG ou un collaborateur partage sa vitrine ou un article (WhatsApp, Facebook,
partage natif du téléphone, lien copié, QR code). Deux familles de routes :

1. Pages de partage PUBLIQUES (sans connexion), destinées aux liens envoyés :
     GET /api/partage/b/{slug}                    -> boutique
     GET /api/partage/b/{slug}/p/{produit_slug}   -> produit
   La vitrine est une application React : les robots de WhatsApp / Facebook
   ne lisent pas son JavaScript, donc ne voient pas le titre, la photo ni le
   prix propres à chaque produit. Ces pages renvoient une petite page HTML
   avec les balises Open Graph / Twitter (titre, description, image, url),
   puis renvoient aussitôt le visiteur HUMAIN vers la vraie page de la vitrine
   (meta refresh + JavaScript + lien de secours). Les robots d'aperçu
   (reconnus à leur « User-Agent ») reçoivent la même page SANS redirection,
   pour lire les balises sans être envoyés vers la vitrine.
   Boutique inconnue / non validée, produit masqué / inactif / sans prix :
   simple redirection (302) vers l'accueil du site ou la vitrine, jamais d'erreur.

2. Route du PERSONNEL (connecté) : GET /api/partage/lien[?produit_id=...]
   Renvoie le lien à partager, le message prérempli, et si le partage est
   possible (sinon la raison, affichée telle quelle par le site).

Statistiques (sans aucune donnée personnelle : ni adresse IP, ni navigateur) :
chaque ouverture d'un lien par un humain ajoute 1 au compteur du produit (ou de
la boutique) et au cumul du jour dans la collection `partages_clics`, par canal
(paramètre ?via=whatsapp|facebook|copie|qr|natif).

Adresses : le site public = FRONTEND_ORIGIN (première adresse, `public_site_url`) ;
l'API = API_PUBLIC_URL si renseignée, sinon l'adresse par laquelle la requête est
arrivée (en https derrière le proxy de Render, en-tête X-Forwarded-Proto).
"""
from __future__ import annotations

import html
import json
import re
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import Contexte, permission, tout_le_personnel
from config import get_settings
from db import SANS_ID, TenantDB, db
from routes.public import EN_VENTE, VISIBLE
from utils import now_iso

# Pages publiques (liens envoyés aux clients) et route du personnel
public = APIRouter(prefix="/partage", tags=["Partage (public)"])
boutique = APIRouter(prefix="/partage", tags=["Partage (personnel)"])

# Canaux reconnus dans ?via= ; toute autre valeur est comptée comme « autre »
CANAUX = ("whatsapp", "facebook", "copie", "qr", "natif")

# Durée de mise en cache des pages de partage (secondes) : courte, pour qu'un
# changement de prix ou de photo apparaisse vite dans les nouveaux aperçus
CACHE_SECONDES = 300

# Robots d'aperçu des réseaux sociaux et messageries (lecture des balises Open Graph).
# Ils ne sont ni redirigés ni comptés dans les statistiques.
_ROBOTS = re.compile(r"facebookexternalhit|facebookcatalog|meta-externalagent|whatsapp|twitterbot|telegrambot|"
                     r"slackbot|linkedinbot|discordbot|skypeuripreview|pinterest|googlebot|bingbot|embedly|"
                     r"redditbot|applebot|vkshare|viber", re.I)

# Message affiché au personnel quand la boutique n'est pas encore validée (lot 42 / lot B)
RAISON_NON_VALIDEE = ("Le partage sera disponible après la validation de votre boutique "
                      "par l'équipe adLyn : votre vitrine n'est pas encore visible du public.")


# ---------------------------------------------------------------------------
# Adresses (site public et API)
# ---------------------------------------------------------------------------
def url_site() -> str:
    """Adresse du site public (vitrines), sans « / » final : FRONTEND_ORIGIN."""
    return get_settings().public_site_url.rstrip("/")


def url_api(request: Request) -> str:
    """Adresse publique de l'API (avec /api), sans « / » final.
    API_PUBLIC_URL si elle est réglée, sinon l'adresse de la requête reçue
    (schéma https repris de l'en-tête X-Forwarded-Proto posé par Render)."""
    reglee = (getattr(get_settings(), "api_public_url", None) or "").strip().rstrip("/")
    if reglee:
        return reglee if reglee.endswith("/api") else f"{reglee}/api"
    base = str(request.base_url).rstrip("/")
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    if proto in ("http", "https") and "://" in base:
        base = f"{proto}://{base.split('://', 1)[1]}"
    return f"{base}/api"


def _absolue(url: Optional[str], request: Request) -> str:
    """Rend absolue l'adresse d'une image (les robots exigent une URL complète)."""
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    # Adresse relative (stockage local de développement) : servie par l'API
    return f"{url_api(request).removesuffix('/api')}/{url.lstrip('/')}"


def lien_partage_boutique(request: Request, slug: str) -> str:
    return f"{url_api(request)}/partage/b/{quote(slug, safe='')}"


def lien_partage_produit(request: Request, slug: str, produit_slug: str) -> str:
    return f"{url_api(request)}/partage/b/{quote(slug, safe='')}/p/{quote(produit_slug, safe='')}"


# ---------------------------------------------------------------------------
# Textes (prix, messages préremplis)
# ---------------------------------------------------------------------------
def prix_formate(valeur, devise: Optional[str]) -> str:
    """125000 -> « 125 000 FCFA » (comme le site : séparateur de milliers = espace)."""
    try:
        n = int(round(float(valeur or 0)))
    except (TypeError, ValueError):
        n = 0
    return f"{n:,}".replace(",", " ") + f" {devise or 'FCFA'}"


def prix_affiche(p: dict) -> bool:
    """Le prix est montré sur la vitrine seulement s'il est renseigné (> 0)."""
    try:
        return float(p.get("prix_vente") or 0) > 0
    except (TypeError, ValueError):
        return False


def message_boutique(b: dict, lien: str) -> str:
    return f"Découvrez {b.get('nom', '')} sur adLyn : {lien}"


def message_produit(b: dict, p: dict, lien: str) -> str:
    # « Nom – prix chez Boutique : lien » (le prix seulement s'il est affiché sur la vitrine)
    prix = f" – {prix_formate(p.get('prix_vente'), b.get('devise'))}" if prix_affiche(p) else ""
    return f"{p.get('nom', '')}{prix} chez {b.get('nom', '')} : {lien}"


def _resume(texte: Optional[str], longueur: int = 200) -> str:
    """Description courte sur une ligne (aperçus WhatsApp / Facebook)."""
    texte = re.sub(r"\s+", " ", texte or "").strip()
    return texte if len(texte) <= longueur else texte[: longueur - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Raisons d'un partage impossible (affichées au personnel)
# ---------------------------------------------------------------------------
def raison_boutique(b: dict) -> str:
    if b.get("validee") is False:
        return RAISON_NON_VALIDEE
    if b.get("actif") is False:
        return "Votre boutique est suspendue : sa vitrine n'est pas visible du public."
    return ""


def raison_produit(p: dict) -> str:
    if p.get("actif") is False:
        return "Cet article est inactif : il n'apparaît pas sur la vitrine et ne peut pas être partagé."
    if not p.get("visible_portail"):
        return "Cet article est masqué de la vitrine : rendez-le visible sur le portail pour le partager."
    if not prix_affiche(p):
        return "Cet article n'a pas de prix de vente : il n'apparaît pas sur la vitrine et ne peut pas être partagé."
    if not p.get("slug"):
        return "Cet article n'a pas encore d'adresse sur la vitrine : enregistrez-le de nouveau."
    return ""


# ---------------------------------------------------------------------------
# Statistiques d'ouverture (aucune donnée personnelle)
# ---------------------------------------------------------------------------
def _canal(via: Optional[str]) -> str:
    via = (via or "").strip().lower()
    return via if via in CANAUX else "autre"


async def compter_ouverture(b: dict, produit: Optional[dict], via: Optional[str]) -> None:
    """+1 sur le compteur du produit (ou de la boutique) et sur le cumul du jour.
    Ne bloque jamais l'affichage : une erreur de comptage est ignorée."""
    canal = _canal(via)
    inc = {"partages.ouvertures": 1, f"partages.canaux.{canal}": 1}
    maj = {"$inc": inc, "$set": {"partages.derniere_ouverture": now_iso()}}
    try:
        if produit:
            await TenantDB(b["id"]).produits.update_one({"id": produit["id"]}, maj)
        else:
            await db.boutiques.update_one({"id": b["id"]}, maj)
        # Cumul du jour par boutique / produit / canal (une ligne par combinaison)
        await db.partages_clics.update_one(
            {"boutique_id": b["id"], "produit_id": (produit or {}).get("id", ""), "canal": canal, "jour": now_iso()[:10]},
            {"$inc": {"ouvertures": 1}}, upsert=True)
    except Exception:  # noqa: BLE001 — les statistiques ne doivent jamais casser le lien
        pass


# ---------------------------------------------------------------------------
# Page HTML de partage
# ---------------------------------------------------------------------------
def _page(*, titre: str, description: str, image: str, url_partage: str, url_cible: str,
          type_og: str = "website", robot: bool = False, prix: Optional[tuple[str, str]] = None) -> str:
    """Petite page HTML : balises Open Graph / Twitter puis redirection du visiteur.
    TOUT texte venant de la base (noms, descriptions, adresses) est échappé."""
    e = lambda t: html.escape(t or "", quote=True)  # noqa: E731 — échappement HTML (texte et attributs)
    balises = [
        f'<meta property="og:type" content="{e(type_og)}">',
        '<meta property="og:site_name" content="adLyn">',
        '<meta property="og:locale" content="fr_FR">',
        f'<meta property="og:title" content="{e(titre)}">',
        f'<meta property="og:description" content="{e(description)}">',
        f'<meta property="og:url" content="{e(url_partage)}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}">',
        f'<meta name="twitter:title" content="{e(titre)}">',
        f'<meta name="twitter:description" content="{e(description)}">',
        f'<meta name="description" content="{e(description)}">',
    ]
    if image:
        balises += [f'<meta property="og:image" content="{e(image)}">',
                    f'<meta property="og:image:alt" content="{e(titre)}">',
                    f'<meta name="twitter:image" content="{e(image)}">']
    if prix:  # prix du produit (aperçus enrichis)
        balises += [f'<meta property="product:price:amount" content="{e(prix[0])}">',
                    f'<meta property="product:price:currency" content="{e(prix[1])}">']
    redirection = ""
    if not robot:
        # Visiteur humain : redirection immédiate (meta refresh + JavaScript).
        # json.dumps + « < » échappé : l'adresse ne peut pas fermer la balise <script>.
        cible_js = json.dumps(url_cible).replace("<", "\\u003c")
        redirection = (f'<meta http-equiv="refresh" content="0;url={e(url_cible)}">'
                       f"<script>window.location.replace({cible_js});</script>")
    return (
        "<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{e(titre)}</title>{''.join(balises)}"
        f'<link rel="canonical" href="{e(url_partage)}">{redirection}'
        "<style>body{font-family:system-ui,sans-serif;display:flex;min-height:100vh;align-items:center;"
        "justify-content:center;margin:0;background:#f7f7f4;color:#121a2c;text-align:center;padding:16px}"
        "a{color:#1e90ff;font-weight:600}</style></head><body><main>"
        f"<p>{e(titre)}</p><p><a href=\"{e(url_cible)}\">Ouvrir la page</a></p>"
        "</main></body></html>"
    )


def _reponse_html(contenu: str) -> HTMLResponse:
    return HTMLResponse(contenu, headers={"Cache-Control": f"public, max-age={CACHE_SECONDES}"})


def _redirection(url: str) -> RedirectResponse:
    """Lien qui ne mène plus à rien de partageable : retour vers l'accueil ou la vitrine."""
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": f"public, max-age={CACHE_SECONDES}"})


def _est_robot(request: Request) -> bool:
    return bool(_ROBOTS.search(request.headers.get("user-agent", "")))


async def _boutique_visible(slug: str) -> Optional[dict]:
    """Boutique ACTIVE et VALIDÉE désignée par son adresse (ou son code marchand), sinon None."""
    slug = (slug or "").strip()[:120]
    if not slug:
        return None
    b = await db.boutiques.find_one({"slug": slug, **dict(VISIBLE)}, SANS_ID)
    if not b:
        b = await db.boutiques.find_one({"code_marchand": slug.upper(), **dict(VISIBLE)}, SANS_ID)
    return b


def _image_defaut() -> str:
    """Image adLyn du site public (frontend/public/og-adlyn.png) quand il n'y a ni logo ni photo."""
    return f"{url_site()}/og-adlyn.png"


# ---------------------------------------------------------------------------
# 1. Pages publiques de partage
# ---------------------------------------------------------------------------
@public.get("/b/{slug}", response_class=HTMLResponse)
async def page_boutique(slug: str, request: Request, via: Optional[str] = None):
    """Page de partage de la vitrine d'une boutique (aperçu + redirection)."""
    b = await _boutique_visible(slug)
    if not b:
        return _redirection(f"{url_site()}/")
    robot = _est_robot(request)
    if not robot:
        await compter_ouverture(b, None, via)
    lieu = ", ".join(x for x in (b.get("ville"), b.get("pays")) if x)
    description = _resume(b.get("slogan")) or f"Découvrez {b.get('nom', '')} sur adLyn{f' ({lieu})' if lieu else ''} : produits, prix et commande en ligne."
    return _reponse_html(_page(
        titre=f"{b.get('nom', '')} — adLyn",
        description=description,
        image=_absolue(b.get("logo_url"), request) or _image_defaut(),
        url_partage=lien_partage_boutique(request, b["slug"]),
        url_cible=f"{url_site()}/b/{quote(b['slug'], safe='')}",
        robot=robot))


@public.get("/b/{slug}/p/{produit_slug}", response_class=HTMLResponse)
async def page_produit(slug: str, produit_slug: str, request: Request, via: Optional[str] = None):
    """Page de partage d'un produit (photo, nom, prix) ; produit invisible -> vitrine."""
    b = await _boutique_visible(slug)
    if not b:
        return _redirection(f"{url_site()}/")
    vitrine = f"{url_site()}/b/{quote(b['slug'], safe='')}"
    p = await TenantDB(b["id"]).produits.find_one({"slug": (produit_slug or "")[:200], **EN_VENTE})
    if not p:
        return _redirection(vitrine)
    robot = _est_robot(request)
    if not robot:
        await compter_ouverture(b, p, via)
    devise = b.get("devise") or "FCFA"
    prix = prix_formate(p.get("prix_vente"), devise) if prix_affiche(p) else ""
    titre = f"{p.get('nom', '')}{f' – {prix}' if prix else ''}"
    description = _resume(p.get("description")) or f"{p.get('nom', '')} chez {b.get('nom', '')}, sur adLyn."
    description = f"Chez {b.get('nom', '')} · {description}" if p.get("description") else description
    return _reponse_html(_page(
        titre=titre,
        description=description,
        image=_absolue(p.get("image_url"), request) or _absolue(b.get("logo_url"), request) or _image_defaut(),
        url_partage=lien_partage_produit(request, b["slug"], p["slug"]),
        url_cible=f"{vitrine}/produit/{quote(p['slug'], safe='')}",
        type_og="product", robot=robot,
        prix=(str(int(round(float(p.get("prix_vente") or 0)))), devise) if prix else None))


# ---------------------------------------------------------------------------
# 2. Lien à partager, pour le personnel connecté
# ---------------------------------------------------------------------------
async def _infos_boutique(ctx: Contexte, request: Request) -> dict:
    b = ctx.boutique
    raison = raison_boutique(b)
    lien = lien_partage_boutique(request, b.get("slug", ""))
    stats = b.get("partages") or {}
    return {"type": "boutique", "partageable": not raison, "raison": raison,
            "titre": b.get("nom", ""), "url": "" if raison else lien,
            "url_vitrine": "" if raison else f"{url_site()}/b/{quote(b.get('slug', ''), safe='')}",
            "message": "" if raison else message_boutique(b, lien),
            "ouvertures": int(stats.get("ouvertures", 0)), "canaux": stats.get("canaux", {})}


@boutique.get("/lien")
async def lien_boutique(request: Request, ctx: Contexte = Depends(tout_le_personnel)):
    """Lien de partage de la vitrine : ouvert à TOUT le personnel (même sans accès au catalogue)."""
    return await _infos_boutique(ctx, request)


@boutique.get("/lien/produit/{produit_id}")
async def lien_produit(produit_id: str, request: Request, ctx: Contexte = Depends(permission("catalogue.lecture"))):
    """Lien de partage d'un produit : personnel qui peut voir le catalogue."""
    p = await ctx.tdb.produits.find_one({"id": produit_id})
    if not p:
        raise HTTPException(404, "Produit introuvable")
    b = ctx.boutique
    raison = raison_boutique(b) or raison_produit(p)
    lien = lien_partage_produit(request, b.get("slug", ""), p.get("slug") or "")
    stats = p.get("partages") or {}
    return {"type": "produit", "partageable": not raison, "raison": raison,
            "titre": p.get("nom", ""), "url": "" if raison else lien,
            "url_vitrine": "" if raison else f"{url_site()}/b/{quote(b.get('slug', ''), safe='')}/produit/{quote(p.get('slug') or '', safe='')}",
            "message": "" if raison else message_produit(b, p, lien),
            "ouvertures": int(stats.get("ouvertures", 0)), "canaux": stats.get("canaux", {})}
