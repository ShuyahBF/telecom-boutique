"""Envoi de CARROUSELS de produits par WhatsApp (API Cloud de Meta).

Une boutique choisit de 2 à 10 produits en vente (avec photo), écrit un court
message d'introduction et sélectionne ses clients qui ont ACCEPTÉ de recevoir
ses offres par WhatsApp. adLyn envoie à chacun le modèle « carrousel » approuvé
par Meta : une carte par produit (photo, nom, prix, bouton « Voir le produit »
qui ouvre la fiche sur la vitrine adLyn, où se font la commande et le paiement).

- Le service n'est actif que si WhatsApp est branché (jeton + numéro) ET si le
  nom de base des modèles carrousel est réglé (WHATSAPP_CARROUSEL_TEMPLATE).
- Chaque envoi est une « campagne » enregistrée dans la base de la boutique,
  avec le résultat par destinataire (pour le suivi et la facturation future).
- Boutiques de démonstration : rien ne part, les envois sont notés NON_ENVOYE.
- Le carrousel reste RÉSERVÉ au WABA (numéro WhatsApp de la plateforme) : la
  Transmission WA Universelle Liluvine ne sait pas envoyer de modèle carrousel
  (cartes + boutons), il n'y a donc ni envoi ni repli par Liluvine pour ce service.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

import envois_plateforme as envois
from config import get_settings

logger = logging.getLogger(__name__)

CARTES_MIN, CARTES_MAX = 2, 10  # limites imposées par Meta pour un carrousel
DESTINATAIRES_MAX = 200  # par campagne, pour rester raisonnable (coût, qualité du numéro)


def carrousel_configure() -> bool:
    """Vrai si WhatsApp est branché ET si le nom de base des modèles carrousel est réglé."""
    return envois.whatsapp_configure() and bool((get_settings().whatsapp_carrousel_template or "").strip())


def nom_modele(nb_cartes: int) -> str:
    """Nom du modèle Meta à utiliser pour n cartes, ex. « adlyn_carrousel_4 »."""
    return f"{get_settings().whatsapp_carrousel_template.strip()}_{nb_cartes}"


def prix_affiche(valeur: Any, devise: str = "FCFA") -> str:
    """79000 -> « 79 000 FCFA » (espace comme séparateur des milliers)."""
    try:
        return f"{int(round(float(valeur))):,}".replace(",", " ") + f" {devise or 'FCFA'}"
    except (TypeError, ValueError):
        return ""


def carte(produit: dict, boutique: dict) -> dict:
    """Données affichées sur une carte (servent aussi à l'aperçu de l'écran)."""
    return {
        "produit_id": produit["id"],
        "nom": produit["nom"][:60],
        "prix": prix_affiche(produit.get("prix_vente"), boutique.get("devise") or "FCFA"),
        "image_url": produit.get("image_url") or "",
        # Suffixe du bouton URL : https://adlynservice.com/b/{{1}}
        "suffixe_lien": f"{boutique['slug']}/produit/{produit['slug']}",
    }


def corps_message(telephone: str, boutique: dict, message: str, cartes: list[dict]) -> dict:
    """Corps JSON envoyé à l'API WhatsApp pour UN destinataire (modèle carrousel)."""
    s = get_settings()
    return {
        "messaging_product": "whatsapp", "to": telephone, "type": "template",
        "template": {
            "name": nom_modele(len(cartes)), "language": {"code": s.whatsapp_template_langue},
            "components": [
                # Texte au-dessus du carrousel : {{1}} boutique, {{2}} message d'introduction
                {"type": "body", "parameters": [{"type": "text", "text": boutique["nom"][:60]},
                                                {"type": "text", "text": message[:500]}]},
                {"type": "carousel", "cards": [
                    {"card_index": i, "components": [
                        {"type": "header", "parameters": [{"type": "image", "image": {"link": c["image_url"]}}]},
                        {"type": "body", "parameters": [{"type": "text", "text": c["nom"]},
                                                        {"type": "text", "text": c["prix"]}]},
                        {"type": "button", "sub_type": "url", "index": "0",
                         "parameters": [{"type": "text", "text": c["suffixe_lien"]}]},
                    ]} for i, c in enumerate(cartes)
                ]},
            ],
        },
    }


async def envoyer_a(client_http: httpx.AsyncClient, telephone: str, boutique: dict, message: str,
                    cartes: list[dict]) -> tuple[str, Optional[str]]:
    """Envoie le carrousel à un numéro -> (statut, erreur). Statuts : ENVOYE, ECHEC, NON_ENVOYE."""
    numero = envois.msisdn(telephone)
    if not numero:
        return "ECHEC", "Numéro de téléphone invalide"
    if boutique.get("test"):
        # Boutique de démonstration : aucun message réel ne part
        return "NON_ENVOYE", "Envoi désactivé pour cette boutique"
    s = get_settings()
    url = envois.WA_GRAPH_URL.format(phone_number_id=s.whatsapp_phone_number_id)
    try:
        r = await client_http.post(url, json=corps_message(numero, boutique, message, cartes),
                                   headers={"Authorization": f"Bearer {s.whatsapp_access_token}"})
    except httpx.HTTPError as exc:
        return "ECHEC", repr(exc)[:200]
    if r.status_code == 200:
        return "ENVOYE", None
    logger.warning("Carrousel WhatsApp vers %s… refusé : HTTP %s", numero[:5], r.status_code)
    return "ECHEC", f"HTTP {r.status_code} {r.text[:200]}"
