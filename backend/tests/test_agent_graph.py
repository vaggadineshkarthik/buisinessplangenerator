"""LangGraph workflow tests (with a mocked OpenRouter client)."""
from __future__ import annotations

import uuid

from app import database as db
from app.agents.graph import _route_after_evaluate, _route_after_generate, _route_after_verify, run_rag_graph
from app.rag.vector_store import vector_store
from app.services.openrouter import OpenRouterError

SAMPLE = (
    "Total revenue for fiscal year 2024 was 4.2 million dollars. "
    "The company was founded in 2021 in Bengaluru, India. "
    "Employees receive twenty vacation days per calendar year."
)


def _seed_document(fake_embeddings, text: str = SAMPLE, name: str = "company_report.pdf") -> str:
    doc_id = uuid.uuid4().hex
    now = db.utcnow()
    db.insert_document(
        {
            "id": doc_id,
            "name": name,
            "filename": name,
            "file_type": "pdf",
            "file_path": "memory",
            "file_size": len(text),
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        }
    )
    ids = [f"{doc_id}:0"]
    contents = [text]
    metadatas = [
        {
            "document_id": doc_id,
            "document_name": name,
            "chunk_index": 0,
            "page_number": 4,
            "char_start": 0,
            "char_end": len(text),
            "source": name,
        }
    ]
    vector_store.add_documents(
        ids=ids,
        embeddings=fake_embeddings.embed_documents(contents),
        documents=contents,
        metadatas=metadatas,
    )
    db.insert_chunks(
        [
            {
                "id": ids[0],
                "document_id": doc_id,
                "chunk_index": 0,
                "page_number": 4,
                "char_start": 0,
                "char_end": len(text),
                "content": text,
                "token_estimate": len(text) // 4,
            }
        ]
    )
    return doc_id


async def test_graph_produces_answer_with_citations(fake_embeddings, mock_openrouter):
    _seed_document(fake_embeddings)
    state = await run_rag_graph(
        question="What was the total revenue in fiscal year 2024?",
        document_ids=None,
    )
    assert state["status"] == "complete"
    assert "4.2 million" in state["answer"]
    assert state["citations"]
    assert state["citations"][0]["document_name"] == "company_report.pdf"
    assert state["verification"]["verdict"] in ("verified", "partially_verified", "unverified")
    assert state["retrieval_stats"]["returned"] >= 1


async def test_graph_reports_insufficient_context(fake_embeddings, mock_openrouter):
    state = await run_rag_graph(
        question="What is the airspeed velocity of an unladen swallow?",
        document_ids=None,
    )
    assert state["status"] == "no_context"
    assert "could not find sufficient information" in state["answer"].lower()
    assert state["citations"] == []


async def test_graph_emits_workflow_events(fake_embeddings, mock_openrouter):
    _seed_document(fake_embeddings)
    events = []

    async def emit(event, **data):
        events.append((event, data))

    await run_rag_graph(
        question="How much revenue was reported in 2024?",
        emit=emit,
    )
    stage_names = [d["name"] for e, d in events if e == "stage" and "name" in d]
    for expected in ("analyzing", "embedding", "searching", "evaluating", "reranking", "generating", "verifying", "citations"):
        assert expected in stage_names
    assert any(e == "token" for e, _ in events)
    assert any(e == "done" for e, _ in events)


async def test_graph_retries_when_answer_unsupported(fake_embeddings, monkeypatch):
    from app.services.openrouter import openrouter_client

    _seed_document(fake_embeddings)
    monkeypatch.setattr(openrouter_client, "_api_key", "test-key", raising=False)

    async def chat_completion(messages, **kwargs):
        return {"content": "{}", "model": "mock", "usage": {}, "raw_finish_reason": "stop"}

    async def stream_chat(messages, **kwargs):
        yield "Unverifiable claim about Napoleon conquering the moon in 1700."

    monkeypatch.setattr(openrouter_client, "chat_completion", chat_completion, raising=False)
    monkeypatch.setattr(openrouter_client, "stream_chat", stream_chat, raising=False)

    state = await run_rag_graph(question="What was the revenue in 2024?")
    assert state["retry_count"] >= 1
    assert state["verification"]["unsupported_claims"]


async def test_graph_handles_openrouter_failure(fake_embeddings, monkeypatch):
    from app.services.openrouter import openrouter_client

    _seed_document(fake_embeddings)
    monkeypatch.setattr(openrouter_client, "_api_key", "test-key", raising=False)

    async def chat_completion(messages, **kwargs):
        return {"content": "{}", "model": "mock", "usage": {}, "raw_finish_reason": "stop"}

    async def stream_chat(messages, **kwargs):
        raise OpenRouterError("Insufficient credits", status_code=402, code="payment_required")
        yield  # pragma: no cover

    monkeypatch.setattr(openrouter_client, "chat_completion", chat_completion, raising=False)
    monkeypatch.setattr(openrouter_client, "stream_chat", stream_chat, raising=False)

    state = await run_rag_graph(question="What was the revenue in 2024?")
    assert state["status"] == "error"
    assert state["errors"]


def test_conditional_routes():
    assert _route_after_evaluate({"route": "rerank"}) == "rerank"
    assert _route_after_evaluate({"route": "insufficient"}) == "insufficient"
    assert _route_after_generate({"status": "error"}) == "finalize"
    assert _route_after_generate({"status": "generated"}) == "verify"
    assert _route_after_verify({"route": "retry"}) == "retry"
    assert _route_after_verify({"route": "finalize"}) == "finalize"
