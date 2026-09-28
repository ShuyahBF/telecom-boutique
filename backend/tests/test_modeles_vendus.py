"""Téléphones créés par les boutiques (fiche technique structurée) et liste des
modèles vendus, point de départ du catalogue public."""
import referentiel

CSV = ("Retail Branding,Marketing Name,Device,Model\n"
       '"TECNO","TECNO Mobile CAMON 30","CL6","TECNO CL6"\n').encode("utf-16")



def test_fiche_technique_et_modeles_vendus(client, super_admin, nouvelle_boutique):
    client.portal.call(lambda: referentiel.importer(CSV))
    camon = client.get("/api/plateforme/referentiel", headers=super_admin, params={"q": "camon 30"}).json()["appareils"][0]
    boutiques = []
    for i in range(2):
        b, h = nouvelle_boutique()
        cat = client.post("/api/categories", headers=h, json={"nom": f"Téléphones {i}"}).json()
        r = client.post("/api/produits", headers=h, json={
            "reference": f"CAM30-{i}", "nom": "Camon 30 256 Go", "type_produit": "TEL", "categorie_id": cat["id"],
            "prix_vente": 150000 + i, "garantie_mois": 12, "referentiel_cle": camon["cle"],
            "fiche_technique": {"fabricant": "Tecno", "modele": "CL6", "systeme": "Android", "version_systeme": "14",
                                "batterie_mah": 5000, "ecran_pouces": 6.78, "stockage_go": 256, "ram_go": 8,
                                "reseau": "4G", "options": ["Double SIM", "NFC"], "couleur": "Noir"}})
        assert r.status_code == 201, r.text
        assert r.json()["marque"] == "Tecno"  # repris du fabricant
        boutiques.append((b, h, r.json()))
    # Vitrine : fiche technique en lignes lisibles
    b0, h0, p0 = boutiques[0]
    fiche = client.get(f"/api/public/b/{b0['slug']}/produits/{p0['slug']}").json()["fiche_technique"]
    assert "Batterie : 5000 mAh" in fiche and "Écran : 6,78 pouces" in fiche and "Garantie : 12 mois" in fiche
    # Fiche produit du back-office : l'appareil relié du référentiel est fourni pour l'affichage
    relie = client.get(f"/api/produits/{p0['id']}", headers=h0).json()["referentiel"]
    assert relie["cle"] == camon["cle"] and relie["marque"] == "Tecno"
    # Liste des modèles vendus : un seul groupe, 2 boutiques, sans aucun prix
    vendus = client.get("/api/plateforme/referentiel/demande", headers=super_admin).json()
    groupe = next(g for g in vendus if g["referentiel_cle"] == camon["cle"])
    assert groupe["nb_boutiques"] == 2 and groupe["fiche"] is None and "prix_vente" not in groupe
    # Création de la fiche publique depuis cette liste, publication
    r = client.post("/api/plateforme/referentiel/demande/fiche", headers=super_admin, json={
        "marque": groupe["marque"], "nom": groupe["nom"], "codes_modele": groupe["codes_modele"],
        "referentiel_cle": groupe["referentiel_cle"]}).json()
    fiche_id = r["fiche"]["id"]
    client.put(f"/api/plateforme/catalogue/{fiche_id}", headers=super_admin, json={
        "type_produit": "TEL", "marque": "Tecno", "nom": "CAMON 30", "reference": r["fiche"]["reference"],
        "caracteristiques": ["Écran : 6,78 pouces"], "statut": "PRET"})
    client.post("/api/plateforme/catalogue/publier", headers=super_admin)
    # Les boutiques qui le vendent déjà n'ont PAS de doublon : leur produit est relié
    for _, h, p in boutiques:
        produits = client.get("/api/produits", headers=h, params={"q": "camon"}).json()
        assert len(produits) == 1 and produits[0]["fiche_publique_id"] == fiche_id
        assert produits[0]["prix_vente"] == p["prix_vente"]  # rien de privé n'est touché
    # Une autre boutique, elle, reçoit le modèle (sans prix, badge Nouveau)
    _, h3 = nouvelle_boutique()
    recu = client.get("/api/produits", headers=h3, params={"q": "camon"}).json()
    assert len(recu) == 1 and recu[0]["catalogue_id"] == fiche_id
    assert client.get("/api/plateforme/referentiel/demande", headers=super_admin).json()[-1]["fiche"] is not None
    # Réservé au super-admin
    assert client.get("/api/plateforme/referentiel/demande", headers=h3).status_code == 403
