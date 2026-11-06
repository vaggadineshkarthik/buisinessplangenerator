"""Conversation listing, creation, detail and deletion endpoints."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .. import database as db

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=120)
    document_ids: Optional[List[str]] = None


@router.get("")
async def list_conversations() -> List[Dict[str, Any]]:
    return db.list_conversations()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(payload: ConversationCreate) -> Dict[str, Any]:
    import json

    now = db.utcnow()
    conv_id = uuid.uuid4().hex
    db.insert_conversation(
        {
            "id": conv_id,
            "title": (payload.title or "New conversation").strip()[:120] or "New conversation",
            "document_ids": json.dumps(payload.document_ids or []),
            "created_at": now,
            "updated_at": now,
        }
    )
    return db.get_conversation(conv_id)  # type: ignore[return-value]


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str) -> Dict[str, Any]:
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {**conv, "messages": db.get_messages(conversation_id)}


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str) -> Dict[str, Any]:
    if not db.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"deleted": True, "conversation_id": conversation_id}
