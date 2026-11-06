"""Chat orchestration: conversations, message persistence and graph execution."""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from .. import database as db
from ..agents.graph import run_rag_graph
from ..config import settings
from ..services.openrouter import OpenRouterError, openrouter_client


def _new_id() -> str:
    return uuid.uuid4().hex


def _title_from_question(question: str) -> str:
    title = " ".join((question or "").split())
    if not title:
        return "New conversation"
    return title[:60] + ("..." if len(title) > 60 else "")


def resolve_document_ids(
    conversation: Optional[Dict[str, Any]],
    document_ids: Optional[List[str]],
) -> List[str]:
    """Pick the document scope: explicit request > conversation scope > all documents."""
    if document_ids:
        return document_ids
    if conversation and conversation.get("document_ids"):
        return conversation["document_ids"]
    return [d["id"] for d in db.list_documents() if d["status"] == "ready"]


def ensure_conversation(
    conversation_id: Optional[str],
    question: str,
    document_ids: Optional[List[str]],
) -> Dict[str, Any]:
    if conversation_id:
        conv = db.get_conversation(conversation_id)
        if conv:
            return conv
    now = db.utcnow()
    conv = {
        "id": _new_id(),
        "title": _title_from_question(question),
        "document_ids": json.dumps(document_ids or []),
        "created_at": now,
        "updated_at": now,
    }
    db.insert_conversation(conv)
    return db.get_conversation(conv["id"])  # type: ignore[return-value]


def _history_for(conversation_id: str, limit: int = 6) -> List[Dict[str, str]]:
    messages = db.get_messages(conversation_id)
    history = [{"role": m["role"], "content": m["content"]} for m in messages]
    return history[-limit:]


def _save_user_message(conversation_id: str, question: str) -> str:
    message_id = _new_id()
    db.insert_message(
        {
            "id": message_id,
            "conversation_id": conversation_id,
            "role": "user",
            "content": question,
            "citations": "[]",
            "contexts": "[]",
            "created_at": db.utcnow(),
        }
    )
    return message_id


def _save_assistant_message(
    conversation_id: str,
    answer: str,
    citations: List[Dict[str, Any]],
    contexts: List[Dict[str, Any]],
) -> str:
    message_id = _new_id()
    db.insert_message(
        {
            "id": message_id,
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": answer,
            "citations": json.dumps(citations),
            "contexts": json.dumps(contexts),
            "created_at": db.utcnow(),
        }
    )
    return message_id


def _finalize_conversation(conversation_id: str, document_ids: List[str], title: Optional[str] = None) -> None:
    fields: Dict[str, Any] = {"document_ids": json.dumps(document_ids)}
    if title:
        fields["title"] = title
    db.update_conversation(conversation_id, **fields)


def _result_payload(state: Dict[str, Any], conversation_id: str) -> Dict[str, Any]:
    return {
        "conversation_id": conversation_id,
        "answer": state.get("answer", ""),
        "citations": state.get("citations", []),
        "contexts": state.get("retrieved_chunks", []),
        "retrieval": state.get("retrieval_stats", {}),
        "relevance": state.get("relevance", {}),
        "verification": state.get("verification", {}),
        "analysis": state.get("analysis", {}),
        "status": state.get("status", ""),
        "errors": state.get("errors", []),
    }


def require_openrouter() -> None:
    if not openrouter_client.configured:
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not configured. Add it to your .env file and restart the backend.",
            status_code=503,
            code="not_configured",
        )


async def run_chat(
    question: str,
    conversation_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Non-streaming chat: runs the graph and persists the exchange."""
    require_openrouter()
    conv = ensure_conversation(conversation_id, question, document_ids)
    history = _history_for(conv["id"])
    scope = resolve_document_ids(conv, document_ids)

    _save_user_message(conv["id"], question)

    state = await run_rag_graph(
        question=question,
        conversation_history=history,
        document_ids=scope,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        emit=None,
    )

    _save_assistant_message(
        conv["id"],
        state.get("answer", ""),
        state.get("citations", []),
        state.get("retrieved_chunks", []),
    )
    _finalize_conversation(conv["id"], scope, conv["title"])
    return _result_payload(state, conv["id"])


async def stream_chat(
    question: str,
    conversation_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    persist_user_message: bool = True,
) -> AsyncIterator[Dict[str, Any]]:
    """Streaming chat: yields workflow events, tokens and the final payload."""
    try:
        require_openrouter()
    except OpenRouterError as exc:
        yield {"event": "error", "data": {"message": exc.message, "code": exc.code}}
        return

    conv = ensure_conversation(conversation_id, question, document_ids)
    history = _history_for(conv["id"])
    scope = resolve_document_ids(conv, document_ids)
    if persist_user_message:
        _save_user_message(conv["id"], question)

    yield {"event": "conversation", "data": {"conversation_id": conv["id"], "title": conv["title"]}}
    yield {"event": "stage", "data": {"name": "question", "status": "completed"}}

    queue: asyncio.Queue = asyncio.Queue()
    SENTINEL = object()

    async def emit(event: str, **data: Any) -> None:
        await queue.put({"event": event, "data": data})

    async def runner() -> None:
        try:
            state = await run_rag_graph(
                question=question,
                conversation_history=history,
                document_ids=scope,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                emit=emit,
            )
            await queue.put({"event": "_final", "data": state})
        except Exception as exc:  # noqa: BLE001
            await queue.put({"event": "_error", "data": {"message": str(exc)}})
        finally:
            await queue.put(SENTINEL)

    task = asyncio.create_task(runner())
    final_state: Optional[Dict[str, Any]] = None
    try:
        while True:
            item = await queue.get()
            if item is SENTINEL:
                break
            if item["event"] == "_final":
                final_state = item["data"]
                continue
            if item["event"] == "_error":
                yield {"event": "error", "data": item["data"]}
                continue
            yield item
    except asyncio.CancelledError:
        task.cancel()
        raise
    finally:
        if not task.done():
            task.cancel()

    if final_state is not None:
        _save_assistant_message(
            conv["id"],
            final_state.get("answer", ""),
            final_state.get("citations", []),
            final_state.get("retrieved_chunks", []),
        )
        _finalize_conversation(conv["id"], scope)
        yield {"event": "result", "data": _result_payload(final_state, conv["id"])}


def validate_regeneration(conversation_id: str) -> None:
    """Raise ValueError before streaming starts if regeneration is not possible."""
    if not db.get_conversation(conversation_id):
        raise ValueError("Conversation not found.")
    if not any(m["role"] == "user" for m in db.get_messages(conversation_id)):
        raise ValueError("No previous question to regenerate.")


async def regenerate(
    conversation_id: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Re-run the last user question and replace the assistant answer."""
    validate_regeneration(conversation_id)

    messages = db.get_messages(conversation_id)
    last_question = None
    for message in reversed(messages):
        if message["role"] == "user":
            last_question = message["content"]
            break

    # Drop the previous assistant reply so history stays coherent.
    if messages and messages[-1]["role"] == "assistant":
        db.delete_message(messages[-1]["id"])

    async for event in stream_chat(
        question=last_question,  # type: ignore[arg-type]
        conversation_id=conversation_id,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        persist_user_message=False,
    ):
        yield event
