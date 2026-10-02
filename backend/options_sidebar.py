"""Options de la barre latérale (menu du back-office), activées BOUTIQUE PAR BOUTIQUE
par l'administrateur de la plateforme (super-admin).

Principe :
  - « Tableau de bord » et « Caisse Aizenta » sont TOUJOURS actives : on ne peut
    pas les désactiver (OPTIONS_OBLIGATOIRES).
  - Toutes les autres options sont DÉSACTIVÉES à la création d'une boutique
    (champ `options_sidebar` de la boutique, voir options_par_defaut()).
    Pour les autoriser, le super-admin ouvre la boutique dans son panneau
    « Plateforme » -> « Barre latérale & Caisse Aizenta » et coche les options.
  - RÉTROCOMPATIBILITÉ : une boutique créée AVANT cette fonction n'a pas le champ
    `options_sidebar`. Elle est traitée comme « tout activé », pour ne couper
    l'accès de personne du jour au lendemain. Dès que le super-admin enregistre
    ses options une première fois, le champ est créé et c'est lui qui fait foi.
  - Une option désactivée MASQUE l'entrée du menu ET bloque côté serveur les
    routes de l'API correspondantes (403 « Option non activée pour cette
    boutique »). Les données ne sont jamais supprimées : réactiver l'option
    les fait réapparaître telles quelles.
  - Les droits par rôle (table PERMISSIONS de auth.py) restent appliqués EN PLUS :
    il faut que l'option soit activée ET que le rôle soit autorisé.

Le contrôle serveur est fait dans auth._resoudre_contexte(), c'est-à-dire pour
TOUTE route métier d'une boutique : on cherche dans la table REGLES ci-dessous
la première règle qui correspond à la requête (méthode + chemin), et il faut
qu'au moins UNE des options listées soit active.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Liste des options (même ordre que le menu de frontend/src/components/GestionLayout.jsx)
# (clé, libellé affiché)
# ---------------------------------------------------------------------------
OPTIONS: list[tuple[str, str]] = [
    ("tableau_de_bord", "Tableau de bord"),
    ("caisse_aizenta", "Caisse Aizenta"),
    ("documents", "Factures & proformas"),
    ("paiements", "Historique des paiements"),
    ("reversements", "Reversements PawaPay"),
    ("commandes", "Commandes en ligne"),
    ("maintenance", "Maintenance (SAV)"),
    ("maintenance_equipements", "Maintenance équipements"),
    ("produits", "Catalogue"),
    ("catalogue_public", "Catalogue public"),
    ("stock", "Stock"),
    ("clients", "Clients"),
    ("fournisseurs", "Fournisseurs"),
    ("messagerie", "Messagerie"),
    ("sms", "SMS"),
    ("carrousel", "Carrousel WhatsApp"),
    ("parametres", "Paramètres"),
    ("abonnement", "Abonnement adLyn"),
    ("parrainage", "Parrainage"),
]
LIBELLES = dict(OPTIONS)
CLES = [cle for cle, _ in OPTIONS]

# Toujours actives, impossibles à désactiver
OPTIONS_OBLIGATOIRES = ("tableau_de_bord", "caisse_aizenta")


def options_par_defaut() -> dict[str, bool]:
    """Options d'une NOUVELLE boutique : seules les deux obligatoires sont actives."""
    return {cle: cle in OPTIONS_OBLIGATOIRES for cle in CLES}


def options_effectives(boutique: Optional[dict]) -> dict[str, bool]:
    """État réel de chaque option pour cette boutique (clé -> vrai / faux).

    - Boutique SANS champ `options_sidebar` (créée avant cette fonction) : tout activé.
    - Les options obligatoires sont toujours vraies.
    - « Maintenance équipements » dépend AUSSI de l'ancien interrupteur
      `maintenance_equipements` de la boutique (fonction historique), qui est
      tenu synchronisé quand le super-admin change l'option.
    """
    boutique = boutique or {}
    enregistrees = boutique.get("options_sidebar")
    historique = not isinstance(enregistrees, dict)
    resultat = {}
    for cle in CLES:
        if cle in OPTIONS_OBLIGATOIRES or historique:
            resultat[cle] = True
        else:
            # Option ajoutée après l'enregistrement : désactivée tant que l'admin ne l'a pas cochée
            resultat[cle] = bool(enregistrees.get(cle, False))
    resultat["maintenance_equipements"] = resultat["maintenance_equipements"] and bool(boutique.get("maintenance_equipements"))
    return resultat


def option_active(boutique: Optional[dict], cle: str) -> bool:
    return options_effectives(boutique).get(cle, False)


# ---------------------------------------------------------------------------
# Routes de l'API protégées par chaque option
# ---------------------------------------------------------------------------
# Chaque règle : (méthodes concernées, motif du chemin SANS le préfixe /api,
# options dont AU MOINS UNE doit être active). La PREMIÈRE règle qui correspond
# s'applique. Un chemin sans règle (tableau de bord, abonnement, connexion…)
# n'est soumis à aucune option.
#
# Pourquoi « au moins une » : certaines listes servent à plusieurs écrans. Exemple :
# la liste des clients sert aussi à choisir le client d'une facture ou d'un dépôt
# SAV ; elle reste donc lisible si « Factures » ou « Maintenance » est active,
# même quand l'écran « Clients » est désactivé.
LECTURE = ("GET", "HEAD")
TOUTES = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE")

REGLES: list[tuple[tuple[str, ...], re.Pattern, tuple[str, ...]]] = [(m, re.compile(motif), opts) for m, motif, opts in [
    # Caisse Aizenta (toujours active, listée pour mémoire)
    (TOUTES, r"^/caisse-aizenta(/|$)", ("caisse_aizenta",)),
    # Maintenance des équipements (avant « maintenance » : même début de chemin)
    (TOUTES, r"^/maintenance-equipements(/|$)", ("maintenance_equipements",)),
    (TOUTES, r"^/maintenance(/|$)", ("maintenance",)),
    # Factures & proformas : une facture créée depuis une commande ou un dépôt SAV reste consultable
    (LECTURE, r"^/documents/\{[a-z_]+\}$", ("documents", "commandes", "maintenance", "maintenance_equipements")),
    (TOUTES, r"^/documents(/|$)", ("documents",)),
    (TOUTES, r"^/journal-paiements(/|$)", ("paiements",)),
    (TOUTES, r"^/reversements(/|$)", ("reversements",)),
    (TOUTES, r"^/commandes(/|$)", ("commandes",)),
    # Clients : liste et création rapide aussi utilisées par Factures, SAV, Maintenance équipements
    (LECTURE, r"^/clients(/|$)", ("clients", "documents", "maintenance", "maintenance_equipements", "commandes")),
    (("POST",), r"^/clients$", ("clients", "documents", "maintenance", "maintenance_equipements")),
    (TOUTES, r"^/clients(/|$)", ("clients",)),
    # Catalogue : la liste des produits sert aussi aux factures, au stock, au SAV (pièces), au carrousel
    (LECTURE, r"^/(produits|categories)(/|$)", ("produits", "documents", "stock", "maintenance", "carrousel")),
    (TOUTES, r"^/(produits|categories|produits-fiche-technique|produits-types-documents)(/|$)", ("produits",)),
    # Stock : la fiche produit affiche et corrige aussi le stock
    (TOUTES, r"^/stock/(motifs|mouvements)(/|$)", ("stock", "produits")),
    (TOUTES, r"^/stock(/|$)", ("stock",)),
    # Fournisseurs : liste aussi utilisée par les bons d'entrée en stock
    (LECTURE, r"^/fournisseurs(/|$)", ("fournisseurs", "stock")),
    (TOUTES, r"^/fournisseurs(/|$)", ("fournisseurs",)),
    (TOUTES, r"^/conversations(/|$)", ("messagerie",)),
    # Factures SMS : réglées depuis la page Abonnement (jamais bloquées, voir plus bas)
    (TOUTES, r"^/boutique/sms/factures(/|$)", ()),
    (TOUTES, r"^/boutique/sms(/|$)", ("sms",)),
    (TOUTES, r"^/boutique/carrousel(/|$)", ("carrousel",)),
    (TOUTES, r"^/catalogue-public(/|$)", ("catalogue_public",)),
    (LECTURE, r"^/referentiel(/|$)", ("catalogue_public", "produits")),
    (TOUTES, r"^/boutique/parrainage(/|$)", ("parrainage",)),
    # Paramètres : l'équipe (liste des techniciens) sert aussi aux dossiers SAV
    (LECTURE, r"^/boutique/equipe$", ("parametres", "maintenance")),
    (TOUTES, r"^/boutique/(equipe|kyc|messagerie|acces|logo)(/|$)", ("parametres",)),
    (("PATCH",), r"^/boutique$", ("parametres",)),
    # TikTok : connexion du compte dans les Paramètres, publication depuis le Catalogue
    (LECTURE, r"^/tiktok/(etat|createur|publications)(/|$)", ("parametres", "produits")),
    (("POST",), r"^/tiktok/publications$", ("produits",)),
    (TOUTES, r"^/tiktok(/|$)", ("parametres",)),
    # ABONNEMENT : volontairement JAMAIS bloqué côté serveur (/boutique/abonnement,
    # /paiements/...) : une boutique doit toujours pouvoir payer son abonnement,
    # même si l'entrée « Abonnement adLyn » est masquée du menu (le bandeau
    # d'échéance et l'écran de suspension y mènent toujours).
]]


def options_requises(methode: str, chemin: str) -> Optional[tuple[str, ...]]:
    """Options exigées par une requête (au moins une doit être active), ou None si aucune.
    `chemin` : modèle de la route SANS /api, ex. « /clients/{client_id} »."""
    for methodes, motif, options in REGLES:
        if methode.upper() in methodes and motif.search(chemin):
            return options or None
    return None


def verifier_requete(boutique: dict, methode: str, chemin: str) -> None:
    """Lève une erreur 403 si la requête touche une option désactivée pour la boutique."""
    if chemin.startswith("/api/"):
        chemin = chemin[4:]
    requises = options_requises(methode, chemin)
    if not requises:
        return
    actives = options_effectives(boutique)
    if not any(actives.get(cle) for cle in requises):
        raise HTTPException(403, f"Option non activée pour cette boutique : {LIBELLES.get(requises[0], requises[0])} "
                                 "(activation par l'administrateur adLyn)")
