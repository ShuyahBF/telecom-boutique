"""Options de la barre latérale activées boutique par boutique par le super-admin :
valeurs par défaut à la création, rétrocompatibilité, blocage serveur (403),
options obligatoires, journal des changements, tableau de bord."""
import asyncio

import options_sidebar
from db import db


def _options(client, super_admin, boutique_id):
    r = client.get(f"/api/plateforme/boutiques/{boutique_id}/options-sidebar", headers=super_admin)
    assert r.status_code == 200, r.text
    return r.json()


def _regler(client, super_admin, boutique_id, **options):
    return client.put(f"/api/plateforme/boutiques/{boutique_id}/options-sidebar", headers=super_admin,
                      json={"options": options})


def test_options_par_defaut_a_la_creation(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique(options_par_defaut=True)
    # Seules les deux options obligatoires sont actives
    actives = {o["cle"] for o in _options(client, super_admin, b["id"])["options"] if o["active"]}
    assert actives == {"tableau_de_bord", "caisse_aizenta"}
    # Le site reçoit l'état réel des options avec la boutique (menu)
    me = client.get("/api/boutique", headers=h).json()
    assert me["options_actives"]["caisse_aizenta"] is True and me["options_actives"]["clients"] is False


def test_tous_les_chemins_de_creation_appliquent_les_valeurs_par_defaut():
    """Super-admin, webhook et parrainage passent tous par enregistrer_boutique()."""
    import inspect

    from routes import parrainage, plateforme, webhooks
    assert "options_par_defaut()" in inspect.getsource(plateforme.enregistrer_boutique)
    for module in (parrainage, webhooks):
        assert "enregistrer_boutique(" in inspect.getsource(module)


def test_boutique_existante_sans_champ_tout_active(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique(options_par_defaut=True)
    # Boutique « historique » : créée avant la fonction, sans champ options_sidebar
    asyncio.run(db.boutiques.update_one({"id": b["id"]}, {"$unset": {"options_sidebar": ""}}))
    etat = _options(client, super_admin, b["id"])
    assert etat["historique"] is True
    assert all(o["active"] for o in etat["options"] if o["cle"] != "maintenance_equipements")
    assert client.get("/api/clients", headers=h).status_code == 200
    assert client.get("/api/produits", headers=h).status_code == 200
    # Premier réglage : on part de « tout activé », seule l'option touchée change
    r = _regler(client, super_admin, b["id"], sms=False)
    assert r.status_code == 200 and r.json()["historique"] is False
    assert client.get("/api/clients", headers=h).status_code == 200
    assert client.get("/api/boutique/sms", headers=h).status_code == 403


def test_option_desactivee_bloquee_cote_serveur(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique(options_par_defaut=True)
    for url in ("/api/clients", "/api/produits", "/api/documents", "/api/commandes", "/api/maintenance",
                "/api/stock/mouvements", "/api/fournisseurs", "/api/conversations", "/api/boutique/sms",
                "/api/boutique/carrousel", "/api/catalogue-public", "/api/journal-paiements", "/api/reversements",
                "/api/boutique/equipe", "/api/boutique/parrainage", "/api/maintenance-equipements"):
        r = client.get(url, headers=h)
        assert r.status_code == 403, url
        assert "Option non activée pour cette boutique" in r.json()["detail"], url
    assert client.post("/api/clients", headers=h, json={"nom": "X", "telephone": "70000000"}).status_code == 403
    # Toujours accessibles : tableau de bord, caisse, fiche boutique, abonnement (paiement)
    for url in ("/api/tableau-de-bord", "/api/caisse-aizenta/situation", "/api/boutique", "/api/boutique/abonnement"):
        assert client.get(url, headers=h).status_code == 200, url
    # Activation : la route répond, les données n'ont jamais été supprimées
    assert _regler(client, super_admin, b["id"], clients=True).status_code == 200
    r = client.post("/api/clients", headers=h, json={"nom": "Client conservé", "telephone": "70000001"})
    assert r.status_code == 201, r.text
    _regler(client, super_admin, b["id"], clients=False)
    assert client.get("/api/clients", headers=h).status_code == 403
    _regler(client, super_admin, b["id"], clients=True)
    assert [c["nom"] for c in client.get("/api/clients", headers=h).json()] == ["Client conservé"]


def test_liste_partagee_ouverte_par_une_autre_option(client, super_admin, nouvelle_boutique):
    """La liste des clients sert aussi aux factures : « Factures » active suffit pour la lire,
    mais la fiche Clients (modification) reste fermée."""
    b, h = nouvelle_boutique(options_par_defaut=True)
    _regler(client, super_admin, b["id"], documents=True)
    assert client.get("/api/clients", headers=h).status_code == 200
    assert client.post("/api/clients", headers=h, json={"nom": "Rapide", "telephone": "70000002"}).status_code == 201
    cid = client.get("/api/clients", headers=h).json()[0]["id"]
    assert client.put(f"/api/clients/{cid}", headers=h, json={"nom": "Modifié"}).status_code == 403


def test_droits_par_role_toujours_appliques(client, super_admin, nouvelle_boutique, connecter_membre):
    b, h = nouvelle_boutique(options_par_defaut=True)
    _regler(client, super_admin, b["id"], parametres=True, paiements=True)
    r = client.post("/api/boutique/equipe", headers=h, json={"nom": "Tech", "email": f"tech-{b['id'][:6]}@test.bf",
                                                              "role": "technicien", "mot_de_passe": "motdepasse-123"})
    assert r.status_code == 201, r.text
    ht, _ = connecter_membre(b["code_marchand"], f"tech-{b['id'][:6]}@test.bf")
    # Option active MAIS rôle non autorisé : refus
    assert client.get("/api/journal-paiements", headers=ht).status_code == 403
    assert client.get("/api/journal-paiements", headers=h).status_code == 200
    # Caisse Aizenta : DG / comptable / secrétaire seulement
    assert client.get("/api/caisse-aizenta/situation", headers=ht).status_code == 403


def test_options_obligatoires_non_desactivables(client, super_admin, nouvelle_boutique):
    b, _ = nouvelle_boutique(options_par_defaut=True)
    for cle in ("tableau_de_bord", "caisse_aizenta"):
        r = _regler(client, super_admin, b["id"], **{cle: False})
        assert r.status_code == 400 and "obligatoire" in r.json()["detail"]
    assert _regler(client, super_admin, b["id"], inconnue=True).status_code == 400
    # Réservé au super-admin
    _, h = nouvelle_boutique()
    assert client.put(f"/api/plateforme/boutiques/{b['id']}/options-sidebar", headers=h,
                      json={"options": {"clients": True}}).status_code == 403


def test_journal_des_changements(client, super_admin, nouvelle_boutique):
    b, _ = nouvelle_boutique(options_par_defaut=True)
    _regler(client, super_admin, b["id"], clients=True, stock=True)
    _regler(client, super_admin, b["id"], stock=False)
    _regler(client, super_admin, b["id"], stock=False)  # aucun changement : rien de journalisé
    journal = _options(client, super_admin, b["id"])["journal"]
    assert len(journal) == 2
    dernier, premier = journal
    assert dernier["par"] == "super@plateforme-test.bf" and dernier["date"]
    assert dernier["changements"] == [{"cle": "stock", "libelle": "Stock", "avant": True, "apres": False}]
    assert {c["cle"] for c in premier["changements"]} == {"clients", "stock"}
    assert all(c["avant"] is False and c["apres"] is True for c in premier["changements"])


def test_maintenance_equipements_synchronisee(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique(options_par_defaut=True)
    _regler(client, super_admin, b["id"], maintenance_equipements=True)
    boutique = client.get("/api/boutique", headers=h).json()
    assert boutique["maintenance_equipements"] is True and boutique["options_actives"]["maintenance_equipements"]
    # L'ancien interrupteur garde l'option alignée
    client.patch(f"/api/plateforme/boutiques/{b['id']}", headers=super_admin, json={"maintenance_equipements": False})
    assert client.get("/api/boutique", headers=h).json()["options_actives"]["maintenance_equipements"] is False
    assert client.get("/api/maintenance-equipements", headers=h).status_code == 403


def test_tableau_de_bord_sans_donnees_des_options_desactivees(client, super_admin, nouvelle_boutique):
    b, h = nouvelle_boutique(options_par_defaut=True)
    tdb = client.get("/api/tableau-de-bord", headers=h).json()
    for cle in ("ca_mois_ht", "nb_commandes_a_traiter", "nb_dossiers_en_cours", "nb_produits_alerte",
                "conversations_attente", "nb_nouveautes_catalogue"):
        assert cle not in tdb
    _regler(client, super_admin, b["id"], documents=True, stock=True)
    tdb = client.get("/api/tableau-de-bord", headers=h).json()
    assert "ca_mois_ht" in tdb and "nb_produits_alerte" in tdb and "nb_commandes_a_traiter" not in tdb


def test_regles_de_routes():
    assert options_sidebar.options_requises("GET", "/clients") == (
        "clients", "documents", "maintenance", "maintenance_equipements", "commandes")
    assert options_sidebar.options_requises("PUT", "/clients/{client_id}") == ("clients",)
    assert options_sidebar.options_requises("GET", "/maintenance-equipements/types") == ("maintenance_equipements",)
    assert options_sidebar.options_requises("GET", "/tableau-de-bord") is None
    assert options_sidebar.options_requises("GET", "/boutique/abonnement") is None
    assert options_sidebar.options_requises("GET", "/boutique/sms/factures") is None
    assert options_sidebar.options_requises("GET", "/boutique") is None
    assert options_sidebar.options_requises("PATCH", "/boutique") == ("parametres",)


def test_facture_consultable_depuis_une_commande(client, super_admin, nouvelle_boutique):
    """Le contrôle se fait sur le MODÈLE de la route (/documents/{document_id}) :
    avec seulement « Commandes », une facture se lit mais la liste des factures reste fermée."""
    b, h = nouvelle_boutique(options_par_defaut=True)
    _regler(client, super_admin, b["id"], commandes=True)
    assert client.get("/api/documents", headers=h).status_code == 403
    assert client.get("/api/documents/inexistant", headers=h).status_code == 404  # passé le contrôle d'option
    assert client.post("/api/documents/inexistant/valider", headers=h).status_code == 403
