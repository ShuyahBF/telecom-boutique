"""Période de grâce après une échéance d'abonnement impayée, puis coupure automatique.

Règles (validées par le propriétaire de la plateforme le 02/10/2026) :
  - l'échéance est le DERNIER jour payé ; sans paiement, la boutique garde un
    accès normal pendant un délai de grâce de 3 jours par défaut, réglable
    boutique par boutique par le super-administrateur (0 à 30 jours,
    champ `grace_jours` de la fiche boutique) ;
  - le super-administrateur peut « Renouveler la grâce (+3 j) » au plus 3 fois
    pour une même échéance impayée (champ `grace_prolongations` =
    {"echeance": <échéance concernée>, "nb": n}). Le compteur est attaché à
    l'échéance : dès qu'un paiement repousse l'échéance, il repart de zéro ;
  - à la fin de la grâce (minuit, heure locale, après le dernier jour de grâce),
    l'accès est coupé CÔTÉ SERVEUR à chaque requête (auth._resoudre_contexte)
    pour tous les comptes de la boutique, sauf le super-administrateur ; seules
    restent ouvertes la page Abonnement / paiement (contexte_abonnement), la
    déconnexion et le profil (/auth/me, Mon compte) ;
  - les boutiques internes de test (`test: True`) ne sont jamais coupées ;
  - la suspension manuelle existante (motif IMPAYE ou MANUEL) reste disponible
    et prioritaire.
Aucune écriture n'est nécessaire à l'échéance : l'état est recalculé à chaque
requête à partir de la fiche boutique (déjà lue par _resoudre_contexte), un
utilisateur connecté est donc coupé à l'heure exacte.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from config import get_settings

GRACE_DEFAUT = 3  # jours
GRACE_MAX = 30
PROLONGATION_JOURS = 3  # bouton « Renouveler la grâce (+3 j) »
PROLONGATIONS_MAX = 3  # par échéance impayée
CODE_EXPIRE = "ABONNEMENT_EXPIRE"
MESSAGE_EXPIRE = ("Abonnement expiré : la période de grâce est terminée. "
                  "Le DG peut renouveler l'abonnement depuis la page Abonnement.")


def _fuseau() -> ZoneInfo:
    return ZoneInfo(get_settings().fuseau_horaire)


def _maintenant() -> datetime:
    """Heure courante dans le fuseau de la plateforme (remplacée dans les tests)."""
    return datetime.now(_fuseau())


def jours_grace(boutique: dict) -> int:
    valeur = boutique.get("grace_jours")
    return GRACE_DEFAUT if valeur is None else int(valeur)


def prolongations(boutique: dict, echeance: str) -> int:
    """Renouvellements de grâce déjà accordés pour CETTE échéance (0 si elle a changé)."""
    p = boutique.get("grace_prolongations") or {}
    return int(p.get("nb") or 0) if p.get("echeance") == echeance else 0


def _echeance(boutique: dict) -> str:
    from abonnements import abonnement_initial  # import local : abonnements importe ce module

    ab = boutique.get("abonnement") or abonnement_initial(boutique.get("created_at"))
    return ab["echeance"]


def resume(boutique: dict, maintenant: Optional[datetime] = None) -> dict:
    """Situation de grâce de la boutique (renvoyée au site et à l'administration)."""
    maintenant = maintenant or _maintenant()
    echeance_txt = _echeance(boutique)
    echeance = date.fromisoformat(echeance_txt)
    nb = prolongations(boutique, echeance_txt)
    total = jours_grace(boutique) + nb * PROLONGATION_JOURS
    dernier_jour = echeance + timedelta(days=total)
    coupure = datetime.combine(dernier_jour + timedelta(days=1), time(0), _fuseau())
    test = bool(boutique.get("test"))
    expire = maintenant.date() > echeance
    en_grace = expire and maintenant < coupure
    return {
        "applicable": not test,  # boutique interne de test : jamais coupée
        "jours_grace": jours_grace(boutique), "prolongations": nb, "prolongations_max": PROLONGATIONS_MAX,
        "prolongation_possible": expire and nb < PROLONGATIONS_MAX,
        "expire": expire, "en_grace": en_grace and not test,
        "jours_grace_restants": (dernier_jour - maintenant.date()).days + 1 if en_grace else 0,
        "dernier_jour_grace": dernier_jour.isoformat(), "coupure_le": coupure.isoformat(),
        "coupe": expire and not en_grace and not test,
    }


def est_coupee(boutique: dict) -> bool:
    return resume(boutique)["coupe"]


def controler(boutique: dict, user: dict) -> None:
    """Appelé à chaque requête métier (auth._resoudre_contexte) : 403 « Abonnement expiré »
    après la grâce, pour tout compte de la boutique sauf le super-administrateur."""
    if user.get("role") == "super_admin":
        return
    if est_coupee(boutique):
        raise HTTPException(403, MESSAGE_EXPIRE, headers={"X-Adlyn-Code": CODE_EXPIRE})


def valider_jours(jours: Optional[int]) -> Optional[int]:
    """0 à 30 jours ; None = valeur par défaut (3 jours)."""
    if jours is None:
        return None
    if not 0 <= int(jours) <= GRACE_MAX:
        raise HTTPException(400, f"Délai de grâce invalide : entre 0 et {GRACE_MAX} jours")
    return int(jours)
