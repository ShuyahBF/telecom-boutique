"""Paiement PI-SPI (Plateforme Interopérable du Système de Paiement Instantané, BCEAO / UEMOA).

ÉTAT AU 04/10/2026 — aucun appel d'API bancaire réel :
  - le QR code PI-SPI est STANDARDISÉ et fourni par la banque (ou l'EME) de la boutique ;
    il contient son « adresse de paiement » (alias), jamais un numéro de téléphone. Son
    format interne n'est pas public : adLyn ne le fabrique PAS, il imprime tel quel le QR
    donné par la banque (texte décodé -> image régénérée sans modification, ou image) ;
  - UBA, BSIC (participants PI-SPI au Burkina) n'ont pas d'API « Business » homologuée,
    IB Bank : statut à confirmer ; seule Ecobank en a une, accès non obtenu.
Donc seul le connecteur MANUEL est actif : le gérant constate le virement reçu sur son
relevé, puis saisit le règlement (mode « PISPI » + référence bancaire) sur la facture ;
une ligne est ajoutée dans la collection `pispi_transactions` (statut « rapproche »).

Emplacements prêts pour les futurs connecteurs (Ecobank, UBA, BSIC, IB Bank) : chacun
répond « non disponible » tant que l'API n'est pas homologuée / l'accès pas obtenu.
AUCUNE URL ni aucun format d'API n'est inventé ici. Variables prévues (facultatives,
saisies dans Render) : PISPI_FOURNISSEUR, PISPI_API_URL, PISPI_CLIENT_ID, PISPI_CLIENT_SECRET.
"""
from __future__ import annotations

from typing import Optional

from config import get_settings

# Statuts d'une transaction PI-SPI (collection pispi_transactions)
STATUTS = ("attendu", "recu", "rapproche", "rejete")
# Banques proposées dans les paramètres « Encaissement PI-SPI » de la boutique
BANQUES = ("UBA", "BSIC", "IB Bank", "Ecobank", "Autre")
CONSIGNE_DEFAUT = ("Payez avec l'application de votre banque ou de votre mobile money (PI-SPI). "
                   "Indiquez la référence ci-dessous.")


class ConnecteurIndisponible(Exception):
    """Le connecteur de cette banque n'est pas utilisable (API non homologuée / accès non obtenu)."""


# ---------------------------------------------------------------------------
# Interface commune (« classe abstraite ») de tous les connecteurs
# ---------------------------------------------------------------------------
class Connecteur:
    code = "abstrait"
    libelle = "Connecteur PI-SPI"
    automatique = False  # vrai seulement pour un connecteur qui parle à une vraie API

    async def demander_paiement(self, reference: str, montant: int, devise: str = "XOF") -> dict:
        """Demande de paiement (« request to pay ») pour une facture."""
        raise NotImplementedError

    async def statut(self, reference: str) -> dict:
        """Statut d'un paiement auprès de la banque."""
        raise NotImplementedError

    async def notification(self, entetes: dict, corps: bytes) -> dict:
        """Lecture et vérification d'une notification de paiement envoyée par la banque."""
        raise NotImplementedError


class ConnecteurManuel(Connecteur):
    """SEUL connecteur actif : rien n'est envoyé à la banque. Le paiement est constaté par
    le gérant puis saisi comme règlement « PISPI » (avec la référence bancaire)."""
    code = "manuel"
    libelle = "Saisie manuelle des encaissements"

    async def demander_paiement(self, reference: str, montant: int, devise: str = "XOF") -> dict:
        # Le client paie en scannant le QR imprimé (montant et référence écrits à côté)
        return {"statut": "attendu", "source": "manuel", "reference": reference, "montant": montant}

    async def statut(self, reference: str) -> dict:
        return {"statut": "inconnu", "source": "manuel", "reference": reference,
                "message": "Vérifiez le relevé de votre banque, puis saisissez le règlement PI-SPI."}

    async def notification(self, entetes: dict, corps: bytes) -> dict:
        raise ConnecteurIndisponible("Aucune notification automatique : connecteur manuel")


class _ConnecteurBancaireFutur(Connecteur):
    """Emplacement d'un futur connecteur bancaire : NON DISPONIBLE aujourd'hui.
    Le jour où l'accès à l'API Business est obtenu, implémenter les trois méthodes
    d'après la documentation OFFICIELLE de la banque (rien n'est supposé ici)."""
    raison = "API Business non homologuée / accès non obtenu"

    def _refus(self):
        raise ConnecteurIndisponible(f"{self.libelle} : non disponible ({self.raison})")

    async def demander_paiement(self, reference: str, montant: int, devise: str = "XOF") -> dict:
        self._refus()

    async def statut(self, reference: str) -> dict:
        self._refus()

    async def notification(self, entetes: dict, corps: bytes) -> dict:
        self._refus()


class ConnecteurEcobank(_ConnecteurBancaireFutur):
    code, libelle = "ecobank", "Ecobank (API Business)"
    raison = "API Business homologuée au Burkina, mais accès non obtenu"


class ConnecteurUBA(_ConnecteurBancaireFutur):
    code, libelle = "uba", "UBA"


class ConnecteurBSIC(_ConnecteurBancaireFutur):
    code, libelle = "bsic", "BSIC"


class ConnecteurIBBank(_ConnecteurBancaireFutur):
    code, libelle = "ibbank", "IB Bank"
    raison = "participation PI-SPI et API Business à confirmer"


CONNECTEURS = {c.code: c for c in (ConnecteurManuel, ConnecteurEcobank, ConnecteurUBA, ConnecteurBSIC, ConnecteurIBBank)}


def connecteur_actif() -> Connecteur:
    """Connecteur choisi par PISPI_FOURNISSEUR (manuel par défaut ou si inconnu)."""
    code = (get_settings().pispi_fournisseur or "manuel").strip().lower()
    return CONNECTEURS.get(code, ConnecteurManuel)()


def notifications_actives() -> bool:
    """La route de notification de paiement n'est ouverte qu'avec un connecteur automatique
    configuré (URL + identifiants). Aujourd'hui : toujours fausse."""
    s = get_settings()
    return bool(connecteur_actif().automatique and s.pispi_api_url and s.pispi_client_id and s.pispi_client_secret)


def bloc_impression(boutique: Optional[dict]) -> Optional[dict]:
    """Paramètres PI-SPI de la boutique à imprimer, ou None si l'encaissement n'est pas
    actif ou s'il n'y a pas de QR (texte ou image)."""
    p = (boutique or {}).get("pispi") or {}
    if not p.get("actif") or not (p.get("qr_contenu") or p.get("qr_image_url")):
        return None
    return {k: p.get(k) for k in ("banque", "banque_libelle", "titulaire", "adresse_paiement", "qr_contenu",
                                  "qr_image_url")} | {"consigne": p.get("consigne") or CONSIGNE_DEFAUT}
