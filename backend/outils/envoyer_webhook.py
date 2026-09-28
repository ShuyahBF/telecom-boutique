"""Envoie une demande SIGNÉE au webhook de création des boutiques (tests, intégration).

Usage :
    python outils/envoyer_webhook.py https://adlyn-backend.onrender.com demande.json
avec la variable WEBHOOK_BOUTIQUES_SECRET = le même secret que sur le serveur.

demande.json (exemple) :
    {"evenement_id": "insc-2026-000123", "nom": "Boutique Étoile", "pays": "Burkina Faso",
     "ville": "Ouagadougou", "telephone": "+22625000000", "dg_nom": "Awa Ouédraogo",
     "dg_email": "awa@exemple.bf", "dg_telephone": "+22670000000"}

Le système appelant doit faire exactement la même chose, dans son langage :
    horodatage = secondes Unix actuelles
    signature  = "sha256=" + HMAC_SHA256_hex(secret, horodatage + "." + corps_JSON_brut)
et envoyer les en-têtes X-Adlyn-Horodatage et X-Adlyn-Signature avec ce corps EXACT.
"""
import hashlib
import hmac
import json
import os
import sys
import time

import httpx


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    url, fichier = sys.argv[1].rstrip("/"), sys.argv[2]
    secret = os.environ.get("WEBHOOK_BOUTIQUES_SECRET")
    if not secret:
        sys.exit("Définissez la variable WEBHOOK_BOUTIQUES_SECRET")
    # Corps envoyé tel quel : la signature porte sur ces octets précis
    with open(fichier, encoding="utf-8") as f:
        corps = json.dumps(json.load(f), ensure_ascii=False).encode()
    horodatage = str(int(time.time()))
    signature = "sha256=" + hmac.new(secret.encode(), horodatage.encode() + b"." + corps, hashlib.sha256).hexdigest()
    r = httpx.post(f"{url}/api/webhooks/boutiques", content=corps, timeout=60, headers={
        "Content-Type": "application/json", "X-Adlyn-Horodatage": horodatage, "X-Adlyn-Signature": signature})
    print(r.status_code, r.text)


if __name__ == "__main__":
    main()
