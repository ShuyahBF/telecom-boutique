"""Envoi des sauvegardes sur le Google Drive du propriétaire de la plateforme.

Autorisation OAuth « drive.file » : l'application ne voit et ne modifie QUE
les fichiers qu'elle a elle-même créés (jamais le reste du Drive).
Rangement : <dossier principal>/<CODE MARCHAND - Nom de la boutique>/fichier
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from config import get_settings

TYPE_DOSSIER = "application/vnd.google-apps.folder"
API = "https://www.googleapis.com/drive/v3/files"
API_ENVOI = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,size"


def configure() -> bool:
    s = get_settings()
    return bool(s.gdrive_client_id and s.gdrive_client_secret and s.gdrive_refresh_token)


class GoogleDrive:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.jeton: Optional[str] = None

    async def connecter(self) -> None:
        """Échange le jeton de rafraîchissement contre un jeton d'accès (valable 1 h)."""
        s = get_settings()
        r = await self.client.post("https://oauth2.googleapis.com/token", data={
            "client_id": s.gdrive_client_id, "client_secret": s.gdrive_client_secret,
            "refresh_token": s.gdrive_refresh_token, "grant_type": "refresh_token"})
        if r.status_code != 200:
            raise RuntimeError(f"Connexion Google Drive refusée : {r.text[:200]}")
        self.jeton = r.json()["access_token"]

    @property
    def _entetes(self) -> dict:
        return {"Authorization": f"Bearer {self.jeton}"}

    async def dossier(self, nom: str, parent: Optional[str] = None) -> str:
        """Identifiant du dossier `nom` (créé s'il n'existe pas)."""
        nom_echappe = nom.replace("\\", "\\\\").replace("'", "\\'")
        requete = f"name = '{nom_echappe}' and mimeType = '{TYPE_DOSSIER}' and trashed = false"
        if parent:
            requete += f" and '{parent}' in parents"
        r = await self.client.get(API, headers=self._entetes, params={"q": requete, "fields": "files(id)"})
        r.raise_for_status()
        trouves = r.json().get("files", [])
        if trouves:
            return trouves[0]["id"]
        meta = {"name": nom, "mimeType": TYPE_DOSSIER, **({"parents": [parent]} if parent else {})}
        r = await self.client.post(API, headers=self._entetes, json=meta, params={"fields": "id"})
        r.raise_for_status()
        return r.json()["id"]

    async def envoyer(self, dossier_id: str, nom: str, contenu: bytes) -> dict:
        """Envoi d'un fichier (requête multipart : description JSON + contenu)."""
        limite = "limite-telecom-boutique"
        meta = json.dumps({"name": nom, "parents": [dossier_id]})
        corps = (f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
                 f"--{limite}\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + contenu + f"\r\n--{limite}--".encode()
        r = await self.client.post(API_ENVOI, content=corps,
                                   headers={**self._entetes, "Content-Type": f"multipart/related; boundary={limite}"})
        r.raise_for_status()
        return r.json()

    async def purger(self, dossier_id: str, jours: int) -> int:
        """Supprime du dossier les sauvegardes plus anciennes que `jours`."""
        limite = (datetime.now(timezone.utc) - timedelta(days=jours)).strftime("%Y-%m-%dT%H:%M:%S")
        r = await self.client.get(API, headers=self._entetes, params={
            "q": f"'{dossier_id}' in parents and createdTime < '{limite}' and trashed = false", "fields": "files(id)"})
        r.raise_for_status()
        n = 0
        for f in r.json().get("files", []):
            if (await self.client.delete(f"{API}/{f['id']}", headers=self._entetes)).status_code in (200, 204):
                n += 1
        return n
