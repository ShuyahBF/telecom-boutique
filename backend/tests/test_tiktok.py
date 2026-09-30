"""TikTok : connexion du compte d'une boutique et publication d'une photo produit.
Les appels à l'API TikTok sont simulés (aucun accès réseau)."""
import io
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image

import tiktok
from config import get_settings


def _png(taille=(1600, 1200)):
    sortie = io.BytesIO()
    Image.new("RGBA", taille, (30, 144, 255, 128)).save(sortie, "PNG")
    return sortie.getvalue()


@pytest.fixture
def tiktok_simule(monkeypatch):
    """App TikTok configurée + API TikTok simulée ; renvoie les appels reçus."""
    s = get_settings()
    monkeypatch.setattr(s, "tiktok_client_key", "cle-test")
    monkeypatch.setattr(s, "tiktok_client_secret", "secret-test")
    appels = {"publication": None}

    async def echanger_code(code):
        assert code == "code-ok"
        return {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 86400, "open_id": "oid-1",
                "refresh_expires_in": 31536000, "scope": tiktok.SCOPES}

    async def profil(jeton):
        return {"display_name": "Boutique Test", "avatar_url": "https://p16.tiktokcdn.com/a.jpg"}

    async def infos_createur(jeton):
        assert jeton == "at-1"  # le jeton est bien déchiffré avant usage
        return {"creator_nickname": "Boutique Test", "privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"],
                "comment_disabled": False}

    async def publier_photos(jeton, **kw):
        appels["publication"] = kw
        return "pub-123"

    async def statut_publication(jeton, publish_id):
        return {"status": "PUBLISH_COMPLETE"}

    async def telecharger(url):
        return _png()

    async def revoquer(jeton):
        appels["revoque"] = jeton

    for nom, f in [("echanger_code", echanger_code), ("profil", profil), ("infos_createur", infos_createur),
                   ("publier_photos", publier_photos), ("statut_publication", statut_publication),
                   ("telecharger", telecharger), ("revoquer", revoquer)]:
        monkeypatch.setattr(tiktok, nom, f)
    return appels


def _connecter(client, h):
    r = client.get("/api/tiktok/connexion", headers=h)
    assert r.status_code == 200, r.text
    url = urlparse(r.json()["url"])
    params = parse_qs(url.query)
    assert url.netloc == "www.tiktok.com" and params["scope"] == ["user.info.basic,video.publish"]
    retour = client.get("/api/tiktok/callback", params={"code": "code-ok", "state": params["state"][0]},
                        follow_redirects=False)
    assert retour.status_code in (302, 307) and retour.headers["location"].endswith("&tiktok=connecte")


def test_non_configure(client, nouvelle_boutique):
    _, h = nouvelle_boutique()
    assert client.get("/api/tiktok/etat", headers=h).json()["configure"] is False
    assert client.get("/api/tiktok/connexion", headers=h).status_code == 503


def test_connexion_publication_et_statut(client, boutique_equipee, tiktok_simule):
    h, produit = boutique_equipee["h"], boutique_equipee["tel"]
    _connecter(client, h)
    etat = client.get("/api/tiktok/etat", headers=h).json()
    assert etat["connecte"] and etat["compte"]["display_name"] == "Boutique Test"

    # Photo du produit (PNG transparent 1600 px)
    r = client.post(f"/api/produits/{produit['id']}/image", headers=h,
                    files={"fichier": ("photo.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    corps = {"produit_id": produit["id"], "titre": "Téléphone test", "visibilite": "PUBLIC_TO_EVERYONE",
             "autoriser_commentaires": True, "contenu_commercial": True, "ma_marque": True, "accord": True}
    # Sans accord : refus
    assert client.post("/api/tiktok/publications", headers=h, json={**corps, "accord": False}).status_code == 400
    # Contenu commercial sans case cochée : refus
    assert client.post("/api/tiktok/publications", headers=h,
                       json={**corps, "ma_marque": False}).status_code == 400
    # Contenu sponsorisé en « Moi uniquement » : refus
    assert client.post("/api/tiktok/publications", headers=h,
                       json={**corps, "contenu_sponsorise": True, "visibilite": "SELF_ONLY"}).status_code == 400
    # Visibilité non proposée par TikTok pour ce compte : refus
    assert client.post("/api/tiktok/publications", headers=h,
                       json={**corps, "visibilite": "FOLLOWER_OF_CREATOR"}).status_code == 400

    r = client.post("/api/tiktok/publications", headers=h, json=corps)
    assert r.status_code == 201, r.text
    envoye = tiktok_simule["publication"]
    assert envoye["visibilite"] == "PUBLIC_TO_EVERYONE" and envoye["ma_marque"] is True
    assert envoye["desactiver_commentaires"] is False and envoye["contenu_sponsorise"] is False
    assert envoye["urls"][0].endswith(".jpg")  # copie JPEG générée pour TikTok
    pub = r.json()
    assert client.get(f"/api/tiktok/publications/{pub['id']}/statut", headers=h).json()["statut"] == "PUBLISH_COMPLETE"
    assert client.get("/api/tiktok/publications", headers=h).json()[0]["id"] == pub["id"]

    # Déconnexion : compte et jetons supprimés
    assert client.post("/api/tiktok/deconnexion", headers=h).status_code == 200
    assert tiktok_simule["revoque"] == "at-1"
    assert client.get("/api/tiktok/etat", headers=h).json()["connecte"] is False


def test_etat_falsifie_refuse(client, tiktok_simule):
    r = client.get("/api/tiktok/callback", params={"code": "code-ok", "state": "faux"}, follow_redirects=False)
    assert r.headers["location"].endswith("&tiktok=erreur")


def test_cloisonnement_entre_boutiques(client, nouvelle_boutique, tiktok_simule):
    _, h1 = nouvelle_boutique()
    _, h2 = nouvelle_boutique()
    _connecter(client, h1)
    assert client.get("/api/tiktok/etat", headers=h1).json()["connecte"] is True
    assert client.get("/api/tiktok/etat", headers=h2).json()["connecte"] is False


def test_photo_convertie_en_jpeg_1080():
    jpeg = tiktok.photo_pour_tiktok(_png((2400, 1200)))
    image = Image.open(io.BytesIO(jpeg))
    assert image.format == "JPEG" and max(image.size) == 1080
