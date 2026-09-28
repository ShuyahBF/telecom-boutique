"""Stockage des images (photos produits, logos des boutiques).

Deux modes, comme sur beauthentik :
  - "local" : disque du serveur, servi via /api/files/<clé>. Développement
              et tests UNIQUEMENT (Render efface le disque à chaque déploiement).
  - "r2"    : Cloudflare R2 (compatible S3, via boto3), bucket PUBLIC.

Cloisonnement : chaque fichier est rangé sous `boutiques/<boutique_id>/...`,
une boutique n'écrit donc jamais dans le dossier d'une autre.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from config import get_settings

TYPES_IMAGES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _r2_client():
    import boto3

    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{s.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=s.r2_access_key_id,
        aws_secret_access_key=s.r2_secret_access_key,
        region_name="auto",
    )


async def lire_image(fichier: UploadFile) -> tuple[bytes, str]:
    """Contrôle le type et la taille d'une image envoyée par le navigateur."""
    s = get_settings()
    if fichier.content_type not in TYPES_IMAGES:
        raise HTTPException(400, "Format d'image non accepté (JPEG, PNG ou WebP)")
    contenu = await fichier.read()
    if len(contenu) > s.max_upload_bytes:
        raise HTTPException(400, f"Image trop lourde (maximum {s.max_upload_bytes // (1024 * 1024)} Mo)")
    return contenu, fichier.content_type


async def enregistrer_image(boutique_id: str, dossier: str, contenu: bytes, content_type: str) -> str:
    """Enregistre l'image et renvoie son URL publique."""
    s = get_settings()
    cle = f"boutiques/{boutique_id}/{dossier}/{uuid.uuid4().hex}{TYPES_IMAGES[content_type]}"
    if s.storage_backend == "r2":
        def _put():
            _r2_client().put_object(Bucket=s.r2_bucket_public, Key=cle, Body=contenu, ContentType=content_type)

        await asyncio.to_thread(_put)
        return f"{(s.r2_public_base_url or '').rstrip('/')}/{cle}"
    chemin = Path(s.uploads_dir) / cle
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    return f"{s.public_base_url}/api/files/{cle}"


async def supprimer_image(boutique_id: str, url: str | None) -> None:
    """Supprime une ancienne image (uniquement si elle appartient à cette boutique)."""
    if not url:
        return
    marqueur = f"boutiques/{boutique_id}/"
    if marqueur not in url:
        return  # jamais de suppression hors du dossier de la boutique
    cle = url[url.index(marqueur):]
    s = get_settings()
    if s.storage_backend == "r2":
        def _delete():
            _r2_client().delete_object(Bucket=s.r2_bucket_public, Key=cle)

        await asyncio.to_thread(_delete)
        return
    (Path(s.uploads_dir) / cle).unlink(missing_ok=True)
