"""Runtime settings, status and analytics endpoints.

Never returns secrets: the OpenRouter API key is only ever reported as
configured / not configured.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import database as db
from ..config import settings
from ..rag.embeddings import embedding_service
from ..rag.vector_store import vector_store
from ..services.openrouter import OpenRouterError, openrouter_client

router = APIRouter(prefix="/api", tags=["settings"])

PERSISTED_KEYS = {
    "openrouter_model": "openrouter_model",
    "temperature": "openrouter_temperature",
    "max_tokens": "openrouter_max_tokens",
    "top_k": "top_k",
    "similarity_threshold": "similarity_threshold",
    "chunk_size": "chunk_size",
    "chunk_overlap": "chunk_overlap",
    "max_file_size_mb": "max_file_size_mb",
    "embedding_model": "embedding_model",
}


class RuntimeSettings(BaseModel):
    openrouter_model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=16, le=8000)
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    similarity_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    chunk_size: Optional[int] = Field(default=None, ge=200, le=4000)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=2000)
    max_file_size_mb: Optional[int] = Field(default=None, ge=1, le=200)
    embedding_model: Optional[str] = None


def apply_persisted_settings() -> None:
    """Load runtime overrides saved in SQLite onto the live settings object."""
    stored = db.all_settings()
    for key, attr in PERSISTED_KEYS.items():
        if key not in stored:
            continue
        raw = stored[key]
        current = getattr(settings, attr)
        try:
            if isinstance(current, bool):
                value: Any = raw.lower() in ("1", "true", "yes")
            elif isinstance(current, int):
                value = int(raw)
            elif isinstance(current, float):
                value = float(raw)
            else:
                value = raw
            setattr(settings, attr, value)
        except (TypeError, ValueError):
            continue
    openrouter_client.model = settings.openrouter_model


def _current_values() -> Dict[str, Any]:
    return {
        "openrouter_model": settings.openrouter_model,
        "temperature": settings.openrouter_temperature,
        "max_tokens": settings.openrouter_max_tokens,
        "top_k": settings.top_k,
        "similarity_threshold": settings.similarity_threshold,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "max_file_size_mb": settings.max_file_size_mb,
        "embedding_model": settings.embedding_model,
    }


@router.get("/settings")
async def get_settings_endpoint() -> Dict[str, Any]:
    vector_health = vector_store.health()
    return {
        "values": _current_values(),
        "openrouter": {
            "configured": openrouter_client.configured,
            "model": settings.openrouter_model,
            "base_url": settings.openrouter_base_url,
        },
        "embeddings": embedding_service.status(),
        "vector_store": {"backend": settings.vector_db, **vector_health},
        "uploads": {
            "allowed_extensions": settings.allowed_extensions,
            "max_file_size_mb": settings.max_file_size_mb,
        },
    }


@router.put("/settings")
async def update_settings(payload: RuntimeSettings) -> Dict[str, Any]:
    updates = payload.model_dump(exclude_none=True)
    for key, value in updates.items():
        attr = PERSISTED_KEYS.get(key)
        if not attr:
            continue
        setattr(settings, attr, value)
        db.set_setting(key, str(value))
    openrouter_client.model = settings.openrouter_model
    return {"updated": True, "values": _current_values()}


@router.get("/settings/models")
async def list_models() -> Dict[str, Any]:
    try:
        models = await openrouter_client.list_models()
    except OpenRouterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {"models": models}


@router.get("/settings/diagnostics")
async def diagnostics() -> Dict[str, Any]:
    return {
        "openrouter": await openrouter_client.health_check(),
        "embeddings": embedding_service.status(),
        "vector_store": vector_store.health(),
        "database": {"path": str(settings.db_path), "available": True},
    }


@router.get("/stats")
async def stats() -> Dict[str, Any]:
    data = db.stats()
    return {
        **data,
        "embeddings": embedding_service.status(),
        "vector_store": vector_store.health(),
        "openrouter": {
            "configured": openrouter_client.configured,
            "model": settings.openrouter_model,
        },
    }
