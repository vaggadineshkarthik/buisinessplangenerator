"""Chat, streaming chat, regeneration and semantic search endpoints."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..rag.retrieval import retrieve
from ..services.chat_service import regenerate, run_chat, stream_chat, validate_regeneration
from ..services.openrouter import OpenRouterError

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=16, le=8000)


class RegenerateRequest(BaseModel):
    conversation_id: str
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=16, le=8000)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    document_ids: Optional[List[str]] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    similarity_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _sse_stream(request: Request, generator: AsyncIterator[Dict[str, Any]]) -> AsyncIterator[str]:
    try:
        async for item in generator:
            if await request.is_disconnected():
                break
            yield _sse(item.get("event", "message"), item.get("data", {}))
    except OpenRouterError as exc:
        yield _sse("error", {"message": exc.message, "code": exc.code})
    except Exception as exc:  # noqa: BLE001
        yield _sse("error", {"message": f"Unexpected error: {exc}", "code": "internal_error"})


@router.post("/chat")
async def chat(request: ChatRequest) -> Dict[str, Any]:
    try:
        return await run_chat(
            question=request.question,
            conversation_id=request.conversation_id,
            document_ids=request.document_ids,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except OpenRouterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request) -> StreamingResponse:
    generator = stream_chat(
        question=request.question,
        conversation_id=request.conversation_id,
        document_ids=request.document_ids,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    return StreamingResponse(
        _sse_stream(http_request, generator),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/regenerate")
async def chat_regenerate(request: RegenerateRequest, http_request: Request) -> StreamingResponse:
    try:
        validate_regeneration(request.conversation_id)
    except ValueError as exc:
        code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    generator = regenerate(
        conversation_id=request.conversation_id,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    return StreamingResponse(
        _sse_stream(http_request, generator),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/search")
async def search(request: SearchRequest) -> Dict[str, Any]:
    try:
        result = await retrieve(
            question=request.query,
            document_ids=request.document_ids,
            top_k=request.top_k,
            threshold=request.similarity_threshold,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}") from exc
    return result.to_dict()
