"""Resend réglé par les variables d'environnement (repli quand rien n'est choisi dans l'écran) :
plateforme (essai, rapports) et boutiques (au nom de la boutique, réponses vers elle)."""
import httpx
import pytest

import envois_plateforme
from config import get_settings
from db import db


class FausseReponse:
    """Réponse simulée de l'API Resend."""
    def __init__(self, code=200, corps=None):
        self.status_code, self._corps = code, corps or {"id": "e-1"}
        self.text = str(self._corps)

    def json(self):
        return self._corps


@pytest.fixture
def resend(monkeypatch):
    """Active Resend (clé et adresse fictives) et capture chaque appel à l'API."""
    s = get_settings()
    monkeypatch.setattr(s, "resend_api_key", "re_test_cle")
    monkeypatch.setattr(s, "resend_expediteur", "noreply@exemple-valide.com")
    appels = {"liste": [], "reponse": FausseReponse()}

    async def faux_post(self, url, json=None, headers=None, **kw):
        appels["liste"].append({"url": url, "json": json, "headers": headers})
        return appels["reponse"]

    monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)
    return appels


def test_resend_non_configure_par_defaut(client, super_admin):
    # Sans les variables Render, l'écran l'indique et le SMTP reste le seul moyen
    r = client.get("/api/plateforme/parametres/smtp", headers=super_admin)
    assert r.status_code == 200 and r.json()["resend_actif"] is False


def test_essai_plateforme_par_resend(client, super_admin, resend):
    r = client.get("/api/plateforme/parametres/smtp", headers=super_admin)
    assert r.json()["resend_actif"] is True and r.json()["resend_expediteur"] == "noreply@exemple-valide.com"
    assert "re_test_cle" not in r.text  # la clé n'est jamais renvoyée au navigateur

    r = client.post("/api/plateforme/parametres/smtp/essai", headers=super_admin, json={"destinataire": "moi@exemple.bf"})
    assert r.status_code == 200, r.text
    appel = resend["liste"][-1]
    assert appel["url"] == envois_plateforme.RESEND_URL
    assert appel["headers"]["Authorization"] == "Bearer re_test_cle"
    assert appel["json"]["from"] == "adLyn <noreply@exemple-valide.com>" and appel["json"]["to"] == ["moi@exemple.bf"]


def test_echec_resend_rapporte(client, super_admin, resend):
    # Domaine non validé : l'erreur de Resend est remontée telle quelle, sans planter
    resend["reponse"] = FausseReponse(403, {"message": "The domain is not verified"})
    r = client.post("/api/plateforme/parametres/smtp/essai", headers=super_admin, json={"destinataire": "moi@exemple.bf"})
    assert r.status_code == 400 and "not verified" in r.json()["detail"]


def test_email_boutique_par_resend(client, nouvelle_boutique, resend):
    boutique, h = nouvelle_boutique(nom="Phone Store")
    assert client.get("/api/boutique/messagerie/fournisseur", headers=h).json()["resend_actif"] is True
    # Le gérant coche seulement « envoyer des e-mails » : aucun serveur SMTP à saisir
    r = client.put("/api/boutique/messagerie", headers=h, json={
        "email_actif": True, "expediteur_nom": "Phone Store", "expediteur_email": "contact@phonestore.bf"})
    assert r.status_code == 200, r.text
    r = client.post("/api/boutique/messagerie/test", headers=h, json={"destinataire": "client@exemple.bf"})
    assert r.json() == {"statut": "ENVOYE", "erreur": ""}
    charge = resend["liste"][-1]["json"]
    # Adresse du domaine validé, au nom de la boutique ; réponses vers la boutique
    assert charge["from"] == "Phone Store <noreply@exemple-valide.com>"
    assert charge["reply_to"] == "contact@phonestore.bf" and charge["to"] == ["client@exemple.bf"]


def test_email_boutique_desactive(client, nouvelle_boutique, resend):
    # Case décochée : rien ne part, même avec Resend
    _, h = nouvelle_boutique()
    client.put("/api/boutique/messagerie", headers=h, json={"email_actif": False})
    r = client.post("/api/boutique/messagerie/test", headers=h, json={"destinataire": "client@exemple.bf"})
    assert r.json()["statut"] == "NON_ENVOYE" and resend["liste"] == []
