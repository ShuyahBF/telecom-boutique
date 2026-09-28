"""Conformité PawaPay : paiement en ligne des commandes réservé aux boutiques dont le
dossier KYC est validé, et identification de la boutique dans les métadonnées de chaque dépôt."""
import httpx

from config import get_settings


class _ReponsePawaPay:
    """Réponse simulée de l'API Payment Page de PawaPay."""
    status_code = 200
    text = ""

    def json(self):
        return {"redirectUrl": "https://pay.exemple/page"}


def test_paiement_en_ligne_reserve_aux_boutiques_verifiees(client, super_admin, boutique_equipee, monkeypatch):
    # Clé PawaPay « sandbox » fictive : le paiement en ligne est disponible sur la plateforme
    monkeypatch.setattr(get_settings(), "pawapay_api_token_sandbox", "cle-test")
    monkeypatch.setattr(get_settings(), "pawapay_environment", "sandbox")
    envois = []

    async def faux_post(self, url, json=None, headers=None):
        envois.append(json)  # on garde le corps envoyé à PawaPay pour le contrôler
        return _ReponsePawaPay()

    monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)

    b = boutique_equipee["boutique"]
    commande = {"nom": "Client Portail", "telephone": "70000000", "mode_paiement": "MOBILE_MONEY",
                "lignes": [{"produit_id": boutique_equipee["tel"]["id"], "quantite": 1}]}

    # 1) Dossier KYC non validé : option masquée sur la vitrine et commande refusée
    assert client.get(f"/api/public/b/{b['slug']}").json()["paiement_mobile_money"] is False
    assert client.post(f"/api/public/b/{b['slug']}/commandes", json=commande).status_code == 400
    assert envois == []  # rien n'a été envoyé à PawaPay

    # 2) Le super-admin valide le dossier : le paiement en ligne s'ouvre
    r = client.post(f"/api/plateforme/boutiques/{b['id']}/kyc/decision", headers=super_admin, json={"statut": "VERIFIE"})
    assert r.status_code == 200
    client.cookies.clear()
    assert client.get(f"/api/public/b/{b['slug']}").json()["paiement_mobile_money"] is True
    r = client.post(f"/api/public/b/{b['slug']}/commandes", json=commande)
    assert r.status_code == 201, r.text

    # 3) Le dépôt envoyé à PawaPay identifie la boutique (sans donnée personnelle du client)
    assert len(envois) == 1
    meta = {k: v for m in envois[0]["metadata"] for k, v in m.items()}
    assert meta["typePaiement"] == "commande"
    assert meta["boutiqueId"] == b["id"]
    assert meta["codeMarchand"] == b["code_marchand"]
    assert meta["commandeNumero"].startswith("CMD-")
    assert "Client Portail" not in str(envois[0]["metadata"])
