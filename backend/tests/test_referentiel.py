"""Référentiel mondial des appareils (liste Google Play + iPhone)."""
import referentiel

CSV = ("Retail Branding,Marketing Name,Device,Model\n"
       '"samsung","Galaxy A15","a15","SM-A155F"\n'
       '"Samsung","Samsung Galaxy A15","a15","SM-A155M"\n'
       '"TECNO","TECNO Mobile SPARK 20","TECNO-KJ5","TECNO KJ5"\n'
       '"","","inconnu","SANS-MARQUE"\n').encode("utf-16")


def test_import_et_recherche(client, super_admin, boutique_equipee, monkeypatch):
    # Import avec un petit fichier au format Google (UTF-16) au lieu du téléchargement
    importer_reel = referentiel.importer

    async def importer_local():
        return await importer_reel(CSV)
    import routes.referentiel as r_ref
    monkeypatch.setattr(r_ref.referentiel, "importer", importer_local)
    rapport = client.post("/api/plateforme/referentiel/importer", headers=super_admin).json()
    # (un autre test a pu importer avant : on vérifie le total, pas le nombre de nouveaux)
    assert rapport["total"] >= 52
    # Les variantes régionales sont regroupées sur un seul appareil ; noms nettoyés
    h = boutique_equipee["h"]
    a15 = client.get("/api/referentiel", headers=h, params={"q": "galaxy a15"}).json()["appareils"]
    assert len(a15) == 1 and a15[0]["codes_modele"] == ["SM-A155F", "SM-A155M"] and a15[0]["marque"] == "Samsung"
    spark = client.get("/api/referentiel", headers=h, params={"q": "spark"}).json()["appareils"][0]
    assert (spark["marque"], spark["nom"]) == ("Tecno", "SPARK 20")
    # Recherche par code modèle, et liste des marques
    assert client.get("/api/referentiel", headers=h, params={"q": "SM-A155M"}).json()["total"] == 1
    assert "Apple" in client.get("/api/referentiel/marques", headers=h).json()
    # Création de la fiche détaillée (brouillon du catalogue public), une seule fois
    r = client.post(f"/api/plateforme/referentiel/{a15[0]['cle']}/fiche", headers=super_admin, json={}).json()
    assert r["fiche"]["reference"] == "SM-A155F" and r["fiche"]["statut"] == "BROUILLON"
    assert client.post(f"/api/plateforme/referentiel/{a15[0]['cle']}/fiche", headers=super_admin, json={}).status_code == 409
    # Tant qu'elle n'est pas publiée, les boutiques voient « pas encore de fiche »
    assert client.get("/api/referentiel", headers=h, params={"q": "galaxy a15"}).json()["appareils"][0]["fiche_publiee"] is False
    assert client.post("/api/plateforme/referentiel/importer", headers=h).status_code == 403


def test_fiche_existante_reliee(client, super_admin):
    """Si une fiche du catalogue porte déjà un des codes modèle, elle est reliée (pas de doublon)."""
    client.post("/api/plateforme/catalogue", headers=super_admin, json={
        "type_produit": "TEL", "marque": "Tecno", "nom": "Spark 20", "reference": "TECNO KJ5", "statut": "BROUILLON"})
    spark = client.get("/api/plateforme/referentiel", headers=super_admin, params={"q": "spark 20"}).json()["appareils"][0]
    r = client.post(f"/api/plateforme/referentiel/{spark['cle']}/fiche", headers=super_admin, json={}).json()
    assert r["existante"] is True and r["fiche"]["reference"] == "TECNO KJ5"
