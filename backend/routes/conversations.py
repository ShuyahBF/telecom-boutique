"""Centre de messagerie (côté personnel) : demandes de conseil des clients
et réponses de l'équipe."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import Contexte, ventes
from messagerie import lien_suivi, notifier_en_fond
from utils import new_id, now_iso

router = APIRouter(prefix="/conversations", tags=["Messagerie"])


def resume(c: dict) -> dict:
    messages = c.get("messages", [])
    return {**{k: v for k, v in c.items() if k != "messages"},
            "nb_messages": len(messages),
            "non_lus": sum(1 for m in messages if m["auteur_type"] == "CLIENT" and not m.get("lu")),
            "dernier_message": messages[-1]["texte"][:120] if messages else ""}


@router.get("")
async def lister(statut: str = "", ctx: Contexte = Depends(ventes)):
    filtre = {"statut": statut} if statut else {}
    return [resume(c) for c in await ctx.tdb.conversations.find(filtre).sort("date_maj", -1).to_list(500)]


@router.get("/non-lues")
async def compteur(ctx: Contexte = Depends(ventes)):
    return {"non_lues": await ctx.tdb.conversations.count_documents({"statut": "ATTENTE"})}


@router.get("/{conversation_id}")
async def lire(conversation_id: str, ctx: Contexte = Depends(ventes)):
    conv = await ctx.tdb.conversations.find_one({"id": conversation_id})
    if not conv:
        raise HTTPException(404, "Conversation introuvable")
    # Ouvrir la conversation = marquer comme lus les messages du client
    for m in conv["messages"]:
        if m["auteur_type"] == "CLIENT":
            m["lu"] = True
    await ctx.tdb.conversations.update_one({"id": conversation_id}, {"$set": {"messages": conv["messages"]}})
    return conv


class Reponse(BaseModel):
    texte: str = Field(..., min_length=1, max_length=5000)


@router.post("/{conversation_id}/repondre")
async def repondre(conversation_id: str, payload: Reponse, ctx: Contexte = Depends(ventes)):
    message = {"id": new_id(), "auteur_type": "EQUIPE", "auteur_nom": ctx.user.get("nom", ""),
               "texte": payload.texte.strip(), "date": now_iso(), "lu": True}
    conv = await ctx.tdb.conversations.find_one_and_update(
        {"id": conversation_id},
        {"$push": {"messages": message}, "$set": {"statut": "REPONDU", "date_maj": now_iso()}})
    if not conv:
        raise HTTPException(404, "Conversation introuvable")
    if conv.get("email"):
        notifier_en_fond(ctx.boutique, "CONSEIL_REPONSE", conv["email"],
                         {"conversation": conv, "message": message}, lien_suivi(ctx.boutique, "conversation", conv))
    return conv


class StatutConversation(BaseModel):
    statut: Literal["ATTENTE", "REPONDU", "CLOS"]


@router.post("/{conversation_id}/statut")
async def changer_statut(conversation_id: str, payload: StatutConversation, ctx: Contexte = Depends(ventes)):
    conv = await ctx.tdb.conversations.find_one_and_update({"id": conversation_id}, {"$set": {"statut": payload.statut}})
    if not conv:
        raise HTTPException(404, "Conversation introuvable")
    return conv
