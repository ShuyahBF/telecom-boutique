"""Serveur d'envoi de la plateforme réglable dans l'administration (mot de passe chiffré)."""
import smtplib

import envois_plateforme
from db import db


def test_reglage_smtp(client, super_admin, nouvelle_boutique, monkeypatch):
    _, h = nouvelle_boutique()
    reglages = {"hote": "mail.sawalismartsystems.com", "port": 465, "ssl": True,
                "utilisateur": "messenger@sawalismartsystems.com", "mot_de_passe": "Secret-123",
                "expediteur": "messenger@sawalismartsystems.com", "nom_expediteur": "adLyn"}
    assert client.put("/api/plateforme/parametres/smtp", headers=h, json=reglages).status_code == 403  # super-admin seul
    r = client.put("/api/plateforme/parametres/smtp", headers=super_admin, json=reglages)
    assert r.status_code == 200 and r.json()["a_mot_de_passe"] and "mot_de_passe" not in r.json()
    # En base : mot de passe chiffré, jamais en clair
    doc = client.portal.call(lambda: db.parametres_plateforme.find_one({"_id": "smtp"}))
    assert "Secret-123" not in str(doc) and envois_plateforme.dechiffrer(doc["mot_de_passe_chiffre"]) == "Secret-123"
    # Changer l'adresse sans retaper le mot de passe : il est conservé
    client.put("/api/plateforme/parametres/smtp", headers=super_admin,
               json={**reglages, "mot_de_passe": "", "expediteur": "noreply@adlynservice.com"})
    c = client.portal.call(envois_plateforme.config_smtp)
    assert c["mot_de_passe"] == "Secret-123" and c["expediteur"] == "noreply@adlynservice.com"

    # E-mail d'essai : envoyé avec ces réglages (serveur simulé)
    envoyes = []

    class FauxSmtp:
        def __init__(self, hote, port, timeout=None):
            envoyes.append(("connexion", hote, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, u, m): envoyes.append(("login", u, m))
        def send_message(self, msg): envoyes.append(("envoi", msg["From"], msg["To"]))

    monkeypatch.setattr(smtplib, "SMTP_SSL", FauxSmtp)
    r = client.post("/api/plateforme/parametres/smtp/essai", headers=super_admin, json={"destinataire": "moi@exemple.bf"})
    assert r.status_code == 200, r.text
    assert ("connexion", "mail.sawalismartsystems.com", 465) in envoyes
    assert ("login", "messenger@sawalismartsystems.com", "Secret-123") in envoyes
    assert any(e[0] == "envoi" and "noreply@adlynservice.com" in e[1] and "adLyn" in e[1] for e in envoyes)
    client.portal.call(lambda: db.parametres_plateforme.delete_one({"_id": "smtp"}))
