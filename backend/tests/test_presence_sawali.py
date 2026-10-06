"""Tests du signal de présence SAWALI (règle 4) : aucun accès réseau."""
from datetime import datetime, timezone

import presence_sawali


def test_construire_signal_contient_tous_les_champs():
    # Corps du signal construit à partir de valeurs fixes
    corps = presence_sawali.construire_signal(
        "10", None, "adlyn-backend",
        datetime(2026, 10, 6, 13, 40, 0, tzinfo=timezone.utc), "3.11.10")
    assert corps == {
        "application": "adLyn",
        "version": "10",
        "deploye_le": None,
        "machine": "adlyn-backend",
        "utilisateur": "serveur",
        "site": "adlynservice.com",
        "systeme": "Render · Python 3.11.10",
        "demarre_le": "2026-10-06T13:40:00Z",
    }


def test_lire_version_depuis_la_source_unique(tmp_path, monkeypatch):
    # La constante VERSION du fichier version.js est bien lue
    fichier = tmp_path / "version.js"
    fichier.write_text("export const VERSION = 12;\nexport const LOT = 40;\n", encoding="utf-8")
    assert presence_sawali.lire_version(fichier) == "12"
    # Fichier absent : repli sur le commit court Render
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")
    assert presence_sawali.lire_version(tmp_path / "absent.js") == "abcdef1"


def test_version_du_depot_est_un_nombre():
    # Le vrai fichier frontend/src/version.js est lisible depuis le backend
    assert presence_sawali.lire_version().isdigit()


def test_cle_support_seulement_si_presente(monkeypatch):
    # Sans variable : pas d'en-tête ; avec variable : en-tête ajouté
    monkeypatch.delenv("LOOIS_SUPPORT_CLE", raising=False)
    assert "X-Cle-Loois" not in presence_sawali.entetes()
    monkeypatch.setenv("LOOIS_SUPPORT_CLE", "valeur-factice")
    assert presence_sawali.entetes()["X-Cle-Loois"] == "valeur-factice"


def test_desactivation(monkeypatch):
    # PRESENCE_SAWALI=0 coupe le signal
    monkeypatch.setenv("PRESENCE_SAWALI", "0")
    assert presence_sawali.presence_active() is False
    monkeypatch.delenv("PRESENCE_SAWALI")
    assert presence_sawali.presence_active() is True
