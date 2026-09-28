"""Crée une vingtaine de boutiques INTERNES de présentation sur une plateforme adLyn.

Boutiques réalistes (villes du Burkina Faso et des pays voisins, adresses,
géolocalisation, DG, IFU/RCCM/CNSS, catalogue aux prix du marché, stock,
clients, dossiers de réparation), marquées « internes » : invisibles des
visiteurs du portail, visibles des seuls super-administrateurs, et aucun
e-mail/SMS/WhatsApp ne part de chez elles (coordonnées imaginaires).

Relançable sans risque : une boutique déjà présente (même nom) est ignorée.

Usage :
    ADLYN_API=https://adlyn-backend.onrender.com/api \\
    ADLYN_ADMIN_EMAIL=... ADLYN_ADMIN_MDP=... ADLYN_MDP_DG=... \\
    python outils/creer_boutiques_internes.py
"""
from __future__ import annotations

import os
import random
import sys
import unicodedata
from datetime import date, timedelta

import httpx

API = os.environ.get("ADLYN_API", "http://localhost:8000/api").rstrip("/")
MDP_DG = os.environ.get("ADLYN_MDP_DG", "")

# ---------------------------------------------------------------------------
# Boutiques : nom, pays, ville, quartier/adresse, lat, lng, DG, indicatif, préfixe RCCM
# ---------------------------------------------------------------------------
BOUTIQUES = [
    ("Wend-Panga Télécom", "Burkina Faso", "Ouagadougou", "Avenue Kwame Nkrumah, près du rond-point des Nations Unies", 12.3703, -1.5247, "Issouf Ouédraogo", "226", "BF OUA"),
    ("Faso Mobile Center", "Burkina Faso", "Ouagadougou", "Rue de la Chance, marché de Rood-Woko", 12.3668, -1.5261, "Aminata Sawadogo", "226", "BF OUA"),
    ("Kadiogo Phone Services", "Burkina Faso", "Ouagadougou", "Boulevard Charles de Gaulle, Ouaga 2000", 12.3216, -1.5098, "Boureima Kaboré", "226", "BF OUA"),
    ("Naaba Smartphones", "Burkina Faso", "Ouagadougou", "Avenue de la Liberté, Zogona", 12.3802, -1.4969, "Salif Compaoré", "226", "BF OUA"),
    ("Tampouy Tech & Réparation", "Burkina Faso", "Ouagadougou", "Route de Kongoussi, Tampouy", 12.4025, -1.5463, "Mariam Zongo", "226", "BF OUA"),
    ("Sya Connect", "Burkina Faso", "Bobo-Dioulasso", "Avenue de la République, près du Grand Marché", 11.1771, -4.2979, "Moussa Traoré", "226", "BF BBD"),
    ("Dafra Téléphonie", "Burkina Faso", "Bobo-Dioulasso", "Rue Guillaume Ouédraogo, Accart-Ville", 11.1823, -4.2905, "Fatoumata Sanou", "226", "BF BBD"),
    ("Kou Mobile Shop", "Burkina Faso", "Bobo-Dioulasso", "Boulevard de la Révolution, Sarfalao", 11.1612, -4.3117, "Adama Barro", "226", "BF BBD"),
    ("Koudougou Phone Plus", "Burkina Faso", "Koudougou", "Avenue Maurice Yaméogo, face à la gare", 12.2526, -2.3627, "Rasmata Bationo", "226", "BF KDG"),
    ("Yatenga Cell", "Burkina Faso", "Ouahigouya", "Rue du Marché central, secteur 2", 13.5828, -2.4216, "Hamidou Sawadogo", "226", "BF OHG"),
    ("Comoé Mobile", "Burkina Faso", "Banfora", "Avenue de la Cascade, quartier Commerce", 10.6333, -4.7614, "Ali Ouattara", "226", "BF BFR"),
    ("Kaya Smart Phone", "Burkina Faso", "Kaya", "Rue du Marché, secteur 1", 13.0917, -1.0844, "Pascal Ouédraogo", "226", "BF KYA"),
    ("Gulmu Télécom", "Burkina Faso", "Fada N'Gourma", "Route de Niamey, secteur 3", 12.0616, 0.3591, "Idrissa Lompo", "226", "BF FDG"),
    ("Adjamé Phone Market", "Côte d'Ivoire", "Abidjan", "Adjamé, boulevard Nangui Abrogoua, Forum des marchés", 5.3570, -4.0231, "Kouassi Konan", "225", "CI-ABJ"),
    ("Gbêkê Mobile", "Côte d'Ivoire", "Bouaké", "Avenue de la Paix, quartier Commerce", 7.6906, -5.0301, "Aya Kouamé", "225", "CI-BKE"),
    ("Bamako Tél Services", "Mali", "Bamako", "Grand Marché, rue Bagadadji", 12.6392, -8.0029, "Mamadou Keïta", "223", "MA.BKO"),
    ("Sandaga Mobile", "Sénégal", "Dakar", "Avenue Lamine Guèye, marché Sandaga", 14.6690, -17.4351, "Cheikh Ndiaye", "221", "SN.DKR"),
    ("Lomé Gsm Center", "Togo", "Lomé", "Grand Marché d'Adawlato, rue du Commerce", 6.1297, 1.2226, "Kodjo Mensah", "228", "TG-LOM"),
    ("Dantokpa Phone", "Bénin", "Cotonou", "Marché Dantokpa, boulevard Saint-Michel", 6.3703, 2.4344, "Rodrigue Houngbédji", "229", "RB/COT"),
    ("Sahel Mobile Niamey", "Niger", "Niamey", "Grand Marché, avenue de la Mairie", 13.5137, 2.1098, "Abdoulaye Issoufou", "227", "NI-NIA"),
]

SLOGANS = ["Téléphones neufs, accessoires et réparation rapide", "Vos smartphones au meilleur prix, garantis",
           "Vente, réparation et accessoires pour tous vos téléphones", "Le spécialiste du téléphone dans votre quartier",
           "Smartphones, pièces d'origine et service après-vente", "Réparation express et smartphones garantis"]
COULEURS = ["#0b5ed7", "#0f766e", "#b91c1c", "#7c3aed", "#c2410c", "#15803d", "#1d4ed8", "#be185d"]

# ---------------------------------------------------------------------------
# Catalogue : (référence, nom, type, catégorie, marque, prix FCFA, fiche technique, garantie mois)
# ---------------------------------------------------------------------------
def ft(fab, modele, systeme, ver, bat, ecran, sto, ram, photo, reseau, options, annee, etat="NEUF"):
    return {"fabricant": fab, "modele": modele, "systeme": systeme, "version_systeme": ver, "batterie_mah": bat,
            "ecran_pouces": ecran, "stockage_go": sto, "ram_go": ram, "appareil_photo": photo, "reseau": reseau,
            "options": options, "etat": etat, "annee_sortie": annee}


TELEPHONES = [
    ("TEC-SPK20", "Tecno Spark 20 (8 Go / 128 Go)", "Tecno", 79000, ft("Tecno", "KJ5", "Android", "13", 5000, 6.56, 128, 8, "50 Mpx", "4G", ["Double SIM", "Lecteur d'empreintes", "Charge rapide"], 2024)),
    ("TEC-CAM30", "Tecno Camon 30 (8 Go / 256 Go)", "Tecno", 165000, ft("Tecno", "CL6", "Android", "14", 5000, 6.78, 256, 8, "50 Mpx + 2 Mpx", "4G", ["Double SIM", "NFC", "Charge rapide"], 2024)),
    ("TEC-POP8", "Tecno Pop 8 (4 Go / 64 Go)", "Tecno", 49000, ft("Tecno", "BG6", "Android", "13 Go", 5000, 6.6, 64, 4, "13 Mpx", "4G", ["Double SIM", "Radio FM"], 2023)),
    ("INF-HOT40I", "Infinix Hot 40i (8 Go / 256 Go)", "Infinix", 72000, ft("Infinix", "X6528", "Android", "13", 5000, 6.56, 256, 8, "50 Mpx", "4G", ["Double SIM", "Charge rapide"], 2023)),
    ("INF-NOTE40", "Infinix Note 40 (8 Go / 256 Go)", "Infinix", 135000, ft("Infinix", "X6853", "Android", "14", 5000, 6.78, 256, 8, "108 Mpx", "4G", ["Double SIM", "NFC", "Charge sans fil"], 2024)),
    ("INF-SMART8", "Infinix Smart 8 (4 Go / 128 Go)", "Infinix", 55000, ft("Infinix", "X6525", "Android", "13 Go", 5000, 6.6, 128, 4, "13 Mpx", "4G", ["Double SIM", "Lecteur d'empreintes"], 2023)),
    ("ITL-A70", "itel A70 (3 Go / 64 Go)", "itel", 45000, ft("itel", "A665L", "Android", "13 Go", 5000, 6.6, 64, 3, "13 Mpx", "4G", ["Double SIM", "Radio FM", "Torche"], 2023)),
    ("ITL-P55", "itel P55 (8 Go / 128 Go)", "itel", 69000, ft("itel", "P662L", "Android", "13", 5000, 6.6, 128, 8, "50 Mpx", "4G", ["Double SIM", "Charge rapide"], 2023)),
    ("SAM-A15", "Samsung Galaxy A15 (4 Go / 128 Go)", "Samsung", 105000, ft("Samsung", "SM-A155F", "Android", "14", 5000, 6.5, 128, 4, "50 Mpx + 5 Mpx + 2 Mpx", "4G", ["Double SIM", "Carte mémoire"], 2023)),
    ("SAM-A25", "Samsung Galaxy A25 5G (6 Go / 128 Go)", "Samsung", 145000, ft("Samsung", "SM-A256B", "Android", "14", 5000, 6.5, 128, 6, "50 Mpx", "5G", ["Double SIM", "NFC", "Charge rapide"], 2023)),
    ("SAM-A55", "Samsung Galaxy A55 5G (8 Go / 256 Go)", "Samsung", 285000, ft("Samsung", "SM-A556B", "Android", "14", 5000, 6.6, 256, 8, "50 Mpx + 12 Mpx + 5 Mpx", "5G", ["Double SIM", "NFC", "Résistant à l'eau", "eSIM"], 2024)),
    ("XIA-R13C", "Xiaomi Redmi 13C (4 Go / 128 Go)", "Xiaomi", 75000, ft("Xiaomi", "23108RN04Y", "Android", "13", 5000, 6.74, 128, 4, "50 Mpx", "4G", ["Double SIM", "Lecteur d'empreintes"], 2023)),
    ("XIA-RN13", "Xiaomi Redmi Note 13 (8 Go / 256 Go)", "Xiaomi", 125000, ft("Xiaomi", "23129RAA4G", "Android", "13", 5000, 6.67, 256, 8, "108 Mpx", "4G", ["Double SIM", "NFC", "Prise jack 3,5 mm"], 2024)),
    ("APL-IP11R", "iPhone 11 64 Go reconditionné", "Apple", 210000, ft("Apple", "A2221", "iOS", "17", 3110, 6.1, 64, 4, "12 Mpx + 12 Mpx", "4G", ["Reconnaissance faciale", "Résistant à l'eau", "eSIM"], 2019, "RECONDITIONNE")),
    ("APL-IP13", "iPhone 13 128 Go", "Apple", 395000, ft("Apple", "A2633", "iOS", "17", 3240, 6.1, 128, 4, "12 Mpx + 12 Mpx", "5G", ["Reconnaissance faciale", "NFC", "Résistant à l'eau", "eSIM"], 2021)),
    ("APL-IP15", "iPhone 15 128 Go", "Apple", 620000, ft("Apple", "A3090", "iOS", "18", 3349, 6.1, 128, 6, "48 Mpx + 12 Mpx", "5G", ["Reconnaissance faciale", "NFC", "Charge sans fil", "eSIM"], 2023)),
]
SIMPLES = [
    ("NOK-105", "Nokia 105 (2023)", "Nokia", 12500, ft("Nokia", "TA-1557", "Autre", "", 1000, 1.8, 0, 0, "", "2G", ["Double SIM", "Radio FM", "Torche"], 2023)),
    ("ITL-2163", "itel it2163", "itel", 9500, ft("itel", "it2163", "Autre", "", 1000, 1.77, 0, 0, "", "2G", ["Double SIM", "Radio FM", "Torche"], 2022)),
    ("TEC-T301", "Tecno T301", "Tecno", 11000, ft("Tecno", "T301", "Autre", "", 1150, 1.77, 0, 0, "", "2G", ["Double SIM", "Radio FM", "Torche"], 2021)),
]
ACCESSOIRES = [
    ("ACC-CH25", "Chargeur rapide 25 W USB-C", "Samsung", 7500), ("ACC-CABC", "Câble USB-C 1 m renforcé", "Oraimo", 2000),
    ("ACC-FPOD", "Écouteurs Bluetooth Oraimo FreePods", "Oraimo", 12000), ("ACC-PB20", "Batterie externe 20 000 mAh", "Oraimo", 15000),
    ("ACC-COQ", "Coque silicone (tous modèles courants)", "", 2500), ("ACC-VERRE", "Verre trempé 9H", "", 1500),
    ("ACC-SD64", "Carte mémoire microSD 64 Go", "SanDisk", 6000), ("ACC-SUPV", "Support téléphone voiture", "", 4000),
    ("ACC-CH10", "Chargeur secteur 10 W + câble micro-USB", "itel", 3000),
]
PIECES = [
    ("PIE-ECSPK20", "Écran complet Tecno Spark 20", "Tecno", 25000), ("PIE-BATA15", "Batterie Samsung Galaxy A15", "Samsung", 12000),
    ("PIE-ECIP11", "Écran iPhone 11 (qualité d'origine)", "Apple", 45000), ("PIE-BATIP11", "Batterie iPhone 11", "Apple", 20000),
    ("PIE-CONUSBC", "Connecteur de charge USB-C", "", 3500), ("PIE-ECHOT40", "Écran complet Infinix Hot 40i", "Infinix", 23000),
]
SERVICES = [
    ("SER-ECRAN", "Main d'œuvre remplacement d'écran", 5000), ("SER-FLASH", "Réinstallation du logiciel (flash)", 5000),
    ("SER-DIAG", "Diagnostic complet", 2000), ("SER-BATT", "Main d'œuvre remplacement de batterie", 3000),
]

PRENOMS = ["Awa", "Adama", "Salimata", "Ousmane", "Aïcha", "Boukary", "Fatimata", "Seydou", "Mariam", "Karim", "Rokia",
           "Abdoul", "Habibou", "Clarisse", "Serge", "Nafissatou", "Lassina", "Pauline", "Drissa", "Sandrine"]
NOMS = ["Ouédraogo", "Kaboré", "Sawadogo", "Traoré", "Zongo", "Compaoré", "Kiemtoré", "Ilboudo", "Nikiéma", "Bamogo",
        "Coulibaly", "Diallo", "Sanou", "Tapsoba", "Yaméogo", "Konaté", "Zida", "Ouattara", "Dabiré", "Somé"]
PANNES = [("Écran cassé après une chute, tactile ne répond plus", "Samsung", "Galaxy A15"),
          ("Ne charge plus, connecteur abîmé", "Tecno", "Spark 20"),
          ("Batterie se décharge en quelques heures", "Apple", "iPhone 11"),
          ("Téléphone bloqué sur le logo au démarrage", "Infinix", "Hot 40i"),
          ("Pas de son pendant les appels", "itel", "A70")]


def ascii_min(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower().replace(" ", "").replace("'", "")


def telephone(ind: str, rnd: random.Random) -> str:
    """Numéro au format du pays (numéros imaginaires : aucun envoi n'est fait)."""
    if ind == "226":
        return f"+226 {rnd.choice(['70', '71', '72', '76', '77', '78', '64', '65', '66', '57'])} {rnd.randint(10, 99)} {rnd.randint(10, 99)} {rnd.randint(10, 99)}"
    if ind == "225":
        return f"+225 07 {rnd.randint(10, 99)} {rnd.randint(10, 99)} {rnd.randint(10, 99)} {rnd.randint(10, 99)}"
    if ind == "229":
        return f"+229 01 9{rnd.randint(0, 9)} {rnd.randint(10, 99)} {rnd.randint(10, 99)} {rnd.randint(10, 99)}"
    if ind == "221":
        return f"+221 77 {rnd.randint(100, 999)} {rnd.randint(10, 99)} {rnd.randint(10, 99)}"
    debut = {"223": "7", "228": "9", "227": "9"}[ind]
    return f"+{ind} {debut}{rnd.randint(0, 9)} {rnd.randint(10, 99)} {rnd.randint(10, 99)} {rnd.randint(10, 99)}"


def prix(base: int, rnd: random.Random) -> int:
    """Prix de la boutique : ± 6 % autour du prix du marché, arrondi à 500 FCFA."""
    return int(round(base * rnd.uniform(0.94, 1.06) / 500) * 500)


class Api:
    def __init__(self):
        self.client = httpx.Client(timeout=90)

    def appel(self, methode: str, chemin: str, jeton: str = "", **kw):
        r = self.client.request(methode, API + chemin, headers={"Authorization": f"Bearer {jeton}"} if jeton else {}, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{methode} {chemin} -> {r.status_code} {r.text[:300]}")
        return r.json()


def creer(api: Api, admin: str, i: int, donnees: tuple, existantes: dict) -> None:
    nom, pays, ville, adresse, lat, lng, dg_nom, ind, rccm = donnees
    rnd = random.Random(nom)  # mêmes « hasards » à chaque exécution
    prenom, nom_dg = dg_nom.split(" ", 1)
    dg_email = f"{ascii_min(prenom)}.{ascii_min(nom_dg)}@adlyn.bf"
    annee = rnd.randint(2015, 2023)
    if nom in existantes:
        # Déjà créée (ex. exécution interrompue) : on complète seulement ce qui manque
        remplir(api, existantes[nom], dg_email, rnd, ind)
        return
    creation = api.appel("POST", "/plateforme/boutiques", admin, json={
        "nom": nom, "pays": pays, "ville": ville, "adresse": adresse,
        "latitude": round(lat + rnd.uniform(-0.003, 0.003), 5), "longitude": round(lng + rnd.uniform(-0.003, 0.003), 5),
        "telephone": telephone(ind, rnd), "dg_nom": dg_nom, "dg_telephone": telephone(ind, rnd),
        "ifu": f"{rnd.randint(10000000, 99999999):08d}{rnd.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}",
        "cnss": f"{rnd.randint(100000, 999999)}", "rccm": f"{rccm} {annee} B {rnd.randint(1000, 19999)}",
        "dg_email": dg_email, "dg_mot_de_passe": MDP_DG, "test": True})
    b = creation["boutique"]
    # Abonnement réglé pour un an : pas de retard ni de rappel pour ces boutiques
    api.appel("PATCH", f"/plateforme/abonnements/boutiques/{b['id']}", admin,
              json={"echeance": (date.today() + timedelta(days=365)).isoformat(), "formule": "ANNUEL"})
    if i < 6:
        api.appel("PATCH", f"/plateforme/boutiques/{b['id']}", admin, json={"mise_en_avant": True, "ordre": i})
    remplir(api, b, dg_email, rnd, ind)


def remplir(api: Api, b: dict, dg_email: str, rnd: random.Random, ind: str) -> None:
    """Fiche, catalogue, clients et réparations d'une boutique (sans doublon si relancé)."""
    nom, ville = b["nom"], b.get("ville", "")
    session = api.appel("POST", "/auth/login", json={"code_boutique": b["code_marchand"], "email": dg_email, "password": MDP_DG})
    h = session["access_token"]
    api.appel("PATCH", "/boutique", h, json={"slogan": rnd.choice(SLOGANS), "couleur": rnd.choice(COULEURS)})

    # Catalogue : rayons + une sélection de produits aux prix de la boutique
    # (les rayons déjà créés, par exemple par la copie du catalogue public, sont réutilisés)
    rayons = {c["nom"]: c["id"] for c in api.appel("GET", "/categories", h)}
    for n in ("Smartphones", "Téléphones simples", "Accessoires", "Pièces détachées", "Services"):
        if n not in rayons:
            rayons[n] = api.appel("POST", "/categories", h, json={"nom": n})["id"]
    produits = []
    for ref, nom_p, marque, base, fiche in rnd.sample(TELEPHONES, rnd.randint(8, 12)):
        produits.append({"reference": ref, "nom": nom_p, "type_produit": "TEL", "categorie_id": rayons["Smartphones"],
                         "marque": marque, "prix_vente": prix(base, rnd), "prix_achat": int(base * 0.82 / 500) * 500,
                         "garantie_mois": 3 if fiche["etat"] == "RECONDITIONNE" else 12, "fiche_technique": fiche,
                         "stock_initial": rnd.randint(0, 9), "stock_alerte": 2})
    for ref, nom_p, marque, base, fiche in rnd.sample(SIMPLES, 2):
        produits.append({"reference": ref, "nom": nom_p, "type_produit": "TEL", "categorie_id": rayons["Téléphones simples"],
                         "marque": marque, "prix_vente": prix(base, rnd), "prix_achat": int(base * 0.8 / 500) * 500,
                         "garantie_mois": 6, "fiche_technique": fiche, "stock_initial": rnd.randint(3, 20), "stock_alerte": 3})
    for ref, nom_p, marque, base in rnd.sample(ACCESSOIRES, rnd.randint(5, 8)):
        produits.append({"reference": ref, "nom": nom_p, "type_produit": "ACC", "categorie_id": rayons["Accessoires"],
                         "marque": marque, "prix_vente": prix(base, rnd), "prix_achat": int(base * 0.6 / 100) * 100,
                         "stock_initial": rnd.randint(4, 40), "stock_alerte": 5})
    for ref, nom_p, marque, base in rnd.sample(PIECES, rnd.randint(3, 5)):
        produits.append({"reference": ref, "nom": nom_p, "type_produit": "PIE", "categorie_id": rayons["Pièces détachées"],
                         "marque": marque, "prix_vente": prix(base, rnd), "prix_achat": int(base * 0.65 / 500) * 500,
                         "garantie_mois": 3, "stock_initial": rnd.randint(1, 8), "stock_alerte": 1})
    for ref, nom_p, base in SERVICES:
        produits.append({"reference": ref, "nom": nom_p, "type_produit": "SER", "categorie_id": rayons["Services"],
                         "prix_vente": base, "visible_portail": False})
    crees = 0
    for p in produits:
        try:
            api.appel("POST", "/produits", h, json=p)
            crees += 1
        except RuntimeError as exc:
            if "409" not in str(exc):  # 409 : référence déjà présente (relance)
                raise
    if not crees:
        print(f"= {nom} déjà complète")
        return

    # Clients et quelques réparations en cours
    clients = []
    for _ in range(rnd.randint(5, 9)):
        clients.append(api.appel("POST", "/clients", h, json={
            "nom": f"{rnd.choice(PRENOMS)} {rnd.choice(NOMS)}", "telephone": telephone(ind, rnd)}))
    for panne, marque, modele in rnd.sample(PANNES, rnd.randint(2, 4)):
        d = api.appel("POST", "/maintenance", h, json={
            "client_id": rnd.choice(clients)["id"], "marque": marque, "modele": modele, "panne_declaree": panne,
            "couleur": rnd.choice(["Noir", "Bleu", "Blanc", "Vert"]), "accessoires_deposes": rnd.choice(["Aucun", "Coque", "Chargeur"]),
            "date_prevue": (date.today() + timedelta(days=rnd.randint(1, 5))).isoformat()})
        statut = rnd.choice(["DIAGNOSTIC", "REPARATION", "ATTENTE_PIECE", "PRET"])
        api.appel("POST", f"/maintenance/{d['id']}/statut", h, json={"statut": statut})
    print(f"+ {nom} ({ville}) — ID boutique {b['code_marchand']}, {len(produits)} produits, DG {dg_email}")


def main() -> None:
    if len(MDP_DG) < 8 or not os.environ.get("ADLYN_ADMIN_EMAIL"):
        sys.exit("Définissez ADLYN_API, ADLYN_ADMIN_EMAIL, ADLYN_ADMIN_MDP et ADLYN_MDP_DG (8 caractères minimum)")
    api = Api()
    admin = api.appel("POST", "/auth/login", json={"email": os.environ["ADLYN_ADMIN_EMAIL"],
                                                    "password": os.environ["ADLYN_ADMIN_MDP"]})["access_token"]
    existantes = {b["nom"]: b for b in api.appel("GET", "/plateforme/boutiques", admin)}
    for i, donnees in enumerate(BOUTIQUES):
        creer(api, admin, i, donnees, existantes)


if __name__ == "__main__":
    main()
