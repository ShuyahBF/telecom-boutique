"""Historique des paiements de chaque boutique (rapport d'activité).

Chaque encaissement laisse une trace, qu'il réussisse ou non :
  - paiements Mobile Money en ligne via PawaPay (en attente, réussi, échoué) ;
  - règlements saisis en caisse sur une facture (espèces, Orange Money,
    Moov Money, carte, virement, chèque), et leurs annulations.
Une même opération garde UNE ligne dont le statut évolue (clé unique),
pour que l'historique reste lisible.
"""
from __future__ import annotations

from typing import Optional

from db import TenantDB
from utils import new_id, now_iso

MODES = {"ESP": "Espèces", "OM": "Orange Money", "MOOV": "Moov Money", "MM": "Mobile Money (PawaPay)",
         "CB": "Carte bancaire", "VIR": "Virement", "CHQ": "Chèque", "PISPI": "PI-SPI"}
STATUTS = {"SUCCES": "Réussi", "ECHEC": "Échoué", "EN_ATTENTE": "En attente", "ANNULE": "Annulé"}


async def journaliser(boutique_id: str, cle: str, *, canal: str, mode: str, montant: int, statut: str,
                      objet: str = "", reference: str = "", client_nom: str = "", motif: str = "",
                      saisi_par: str = "", devise: str = "FCFA", liens: Optional[dict] = None) -> None:
    """Crée la ligne `cle` ou met à jour son statut si elle existe déjà."""
    tdb = TenantDB(boutique_id)
    maj = {"statut": statut, "motif": motif, "date_maj": now_iso()}
    if await tdb.journal_paiements.find_one({"cle": cle}, {"_id": 0, "id": 1}):
        await tdb.journal_paiements.update_one({"cle": cle}, {"$set": maj})
        return
    await tdb.journal_paiements.insert_one({
        "id": new_id(), "cle": cle, "date": now_iso(), **maj, "canal": canal, "mode": mode,
        "mode_libelle": MODES.get(mode, mode), "montant": int(montant), "devise": devise, "objet": objet,
        "reference": reference, "client_nom": client_nom, "saisi_par": saisi_par, **(liens or {}),
    })
