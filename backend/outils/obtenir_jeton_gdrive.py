"""Outil à lancer UNE FOIS sur votre ordinateur pour autoriser la plateforme
à déposer les sauvegardes sur VOTRE Google Drive.

Prérequis (Google Cloud Console, même projet que pour gmail_pdf_reader) :
  1. Activer l'API « Google Drive API ».
  2. Créer des identifiants OAuth 2.0 de type « Application de bureau ».
  3. pip install google-auth-oauthlib

Lancement :
  python obtenir_jeton_gdrive.py --client-id XXX --client-secret YYY

Une page Google s'ouvre : connectez-vous avec le compte dont le Drive doit
recevoir les sauvegardes et acceptez. Le script affiche alors les trois
valeurs à copier dans Render (GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET,
GDRIVE_REFRESH_TOKEN). Le jeton est un secret : ne le partagez pas et ne le
mettez jamais dans le code.
"""
import argparse

from google_auth_oauthlib.flow import InstalledAppFlow

# Accès limité aux fichiers créés par l'application (pas au reste du Drive)
PORTEE = ["https://www.googleapis.com/auth/drive.file"]

if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--client-id", required=True)
    arguments.add_argument("--client-secret", required=True)
    a = arguments.parse_args()
    config = {"installed": {"client_id": a.client_id, "client_secret": a.client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "redirect_uris": ["http://localhost"]}}
    flux = InstalledAppFlow.from_client_config(config, PORTEE)
    # prompt="consent" garantit l'obtention d'un jeton de rafraîchissement
    identifiants = flux.run_local_server(port=0, access_type="offline", prompt="consent")
    print("\nÀ recopier dans les variables d'environnement Render :")
    print(f"GDRIVE_CLIENT_ID={a.client_id}")
    print(f"GDRIVE_CLIENT_SECRET={a.client_secret}")
    print(f"GDRIVE_REFRESH_TOKEN={identifiants.refresh_token}")
