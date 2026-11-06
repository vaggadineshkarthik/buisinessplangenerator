"""Business plan generator tests (mocked OpenRouter, deterministic embeddings)."""
from __future__ import annotations

import uuid

from app import database as db
from app.agents.plan_graph import _route_after_write, run_plan_graph
from app.agents.plan_prompts import DEFAULT_SECTION_KEYS, resolve_sections
from app.rag.vector_store import vector_store
from app.services.plan_service import (
    create_plan,
    export_plan_markdown,
    export_plan_text,
    get_plan_payload,
    list_plans,
    section_catalog,
)

SAMPLE = (
    "The Indian pet-care market grew to 4.2 billion dollars in 2024. "
    "Premium pet food accounts for 38 percent of spending."
)

INPUTS = {
    "product": "Subscription-based premium pet food delivery",
    "target_market": "Urban pet owners in India",
    "problem": "Pet owners struggle to find trustworthy premium food",
    "revenue_year_1": "1200000",
    "funding_need": "500000",
}


def _seed_document(fake_embeddings, text: str = SAMPLE, name: str = "market_research.pdf") -> str:
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
            "page_number": 2,
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
                "page_number": 2,
                "char_start": 0,
                "char_end": len(text),
                "content": text,
                "token_estimate": len(text) // 4,
            }
        ]
    )
    return doc_id


# ---------------------------------------------------------------------------
# Catalog & persistence
# ---------------------------------------------------------------------------
def test_section_catalog_has_defaults():
    catalog = section_catalog()
    assert len(catalog) >= 8
    keys = {s["key"] for s in catalog}
    assert "executive_summary" in keys
    assert "financial_projections" in keys
    assert DEFAULT_SECTION_KEYS
    assert all(s["key"] in keys for s in catalog)


def test_resolve_sections_orders_and_falls_back():
    resolved = resolve_sections(["market_analysis", "executive_summary"])
    assert [s["key"] for s in resolved] == ["market_analysis", "executive_summary"]
    # Unknown keys fall back to the defaults rather than producing an empty plan.
    assert resolve_sections(["does_not_exist"])[0]["key"] in DEFAULT_SECTION_KEYS


def test_create_plan_builds_skeleton():
    plan = create_plan(
        business_name="PetPal",
        industry="Pet care",
        notes="Focus on metro cities",
        inputs=INPUTS,
        section_keys=["executive_summary", "market_analysis"],
    )
    assert plan["business_name"] == "PetPal"
    assert plan["status"] == "generating"
    assert plan["section_count"] == 2
    assert [s["key"] for s in plan["sections"]] == ["executive_summary", "market_analysis"]
    assert all(s["status"] == "pending" and s["content"] == "" for s in plan["sections"])
    assert plan["inputs"]["notes"] == "Focus on metro cities"


# ---------------------------------------------------------------------------
# LangGraph workflow
# ---------------------------------------------------------------------------
async def test_graph_writes_every_section(fake_embeddings, mock_openrouter):
    state = await run_plan_graph(
        business_name="PetPal",
        industry="Pet care",
        inputs=INPUTS,
        sections=resolve_sections(["executive_summary", "market_analysis"]),
    )
    assert state["status"] == "ready"
    assert len(state["written"]) == 2
    assert all(s["content"] for s in state["written"])
    assert state["overview"]


async def test_graph_emits_plan_events(fake_embeddings, mock_openrouter):
    events = []

    async def emit(event, **data):
        events.append((event, data))

    await run_plan_graph(
        business_name="PetPal",
        inputs=INPUTS,
        sections=resolve_sections(["executive_summary"]),
        emit=emit,
    )
    names = [e for e, _ in events]
    assert "stage" in names
    assert "token" in names
    assert "section" in names
    assert "done" in names
    stage_names = [d["name"] for e, d in events if e == "stage" and "name" in d]
    for expected in ("analyzing", "generating", "citations"):
        assert expected in stage_names
    # Tokens are tagged with the section they belong to.
    token_events = [d for e, d in events if e == "token"]
    assert all(d.get("section_key") == "executive_summary" for d in token_events)


async def test_graph_grounds_on_selected_documents(fake_embeddings, mock_openrouter):
    doc_id = _seed_document(fake_embeddings)
    state = await run_plan_graph(
        business_name="PetPal",
        industry="Pet care",
        inputs=INPUTS,
        document_ids=[doc_id],
        sections=resolve_sections(["market_analysis"]),
    )
    assert state["citations"]
    assert state["citations"][0]["document_name"] == "market_research.pdf"
    assert state["retrieval_stats"]["returned"] >= 1
    assert "market_research.pdf" in state["context"]


async def test_graph_without_documents_has_no_citations(fake_embeddings, mock_openrouter):
    state = await run_plan_graph(
        business_name="PetPal",
        inputs=INPUTS,
        document_ids=[],
        sections=resolve_sections(["executive_summary"]),
    )
    assert state["citations"] == []
    assert state["written"][0]["content"]


def test_conditional_route_loops_until_done():
    state = {"sections": [{}, {}], "current_index": 0}
    assert _route_after_write(state) == "write_section"
    state["current_index"] = 2
    assert _route_after_write(state) == "finalize"


# ---------------------------------------------------------------------------
# Service: non-streaming generation
# ---------------------------------------------------------------------------
async def test_generate_plan_persists_sections(fake_embeddings, mock_openrouter):
    from app.services.plan_service import generate_plan

    plan = create_plan(
        business_name="PetPal",
        industry="Pet care",
        inputs=INPUTS,
        section_keys=["executive_summary", "market_analysis"],
    )
    result = await generate_plan(plan["id"])
    assert result["status"] == "ready"
    assert all(s["content"] for s in result["sections"])
    assert result["word_count"] > 0
    assert result["overview"]
    stored = get_plan_payload(plan["id"])
    assert stored["sections"][0]["status"] == "ready"


def test_list_and_delete_plan(fake_embeddings):
    plan = create_plan(business_name="PetPal", section_keys=["executive_summary"])
    assert any(p["id"] == plan["id"] for p in list_plans())
    from app.services.plan_service import delete_plan

    assert delete_plan(plan["id"]) is True
    assert get_plan_payload(plan["id"]) is None


def test_export_markdown_includes_sections():
    plan = create_plan(
        business_name="PetPal",
        industry="Pet care",
        section_keys=["executive_summary"],
    )
    db.update_plan(plan["id"], status="ready", overview="A pet food subscription.")
    section = db.get_plan_sections(plan["id"])[0]
    db.update_plan_section(
        section["id"], content="PetPal delivers premium pet food.", status="ready", word_count=5
    )
    markdown = export_plan_markdown(plan["id"])
    assert "# PetPal — Business Plan" in markdown
    assert "## Executive Summary" in markdown
    assert "PetPal delivers premium pet food." in markdown
    text = export_plan_text(plan["id"])
    assert "EXECUTIVE SUMMARY" in text


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
def test_catalog_endpoint(client):
    response = client.get("/api/plans/catalog")
    assert response.status_code == 200
    assert response.json()["sections"]


def test_plans_list_empty(client):
    response = client.get("/api/plans")
    assert response.status_code == 200
    assert response.json() == []


def test_get_unknown_plan_returns_404(client):
    assert client.get("/api/plans/deadbeef").status_code == 404


def test_delete_unknown_plan_returns_404(client):
    assert client.delete("/api/plans/deadbeef").status_code == 404


def test_export_unknown_plan_returns_404(client):
    assert client.get("/api/plans/deadbeef/export").status_code == 404


def test_generate_endpoint_requires_configuration(client, fake_embeddings):
    """Without an OpenRouter key the API must fail clearly, not fake a plan."""
    response = client.post(
        "/api/plans/generate",
        json={"business_name": "PetPal", "sections": ["executive_summary"]},
    )
    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]


def test_generate_endpoint_rejects_empty_business_name(client):
    response = client.post("/api/plans/generate", json={"business_name": "", "sections": []})
    assert response.status_code == 422


def test_stream_endpoint_reports_missing_key(client, fake_embeddings):
    response = client.post(
        "/api/plans/generate/stream",
        json={"business_name": "PetPal", "sections": ["executive_summary"]},
    )
    assert response.status_code == 200
    assert "not_configured" in response.text


def test_stream_endpoint_emits_events(client, fake_embeddings, mock_openrouter):
    with client.stream(
        "POST",
        "/api/plans/generate/stream",
        json={
            "business_name": "PetPal",
            "industry": "Pet care",
            "inputs": INPUTS,
            "sections": ["executive_summary", "market_analysis"],
        },
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: plan" in body
    assert "event: section" in body
    assert "event: token" in body
    assert "event: result" in body

    plans = client.get("/api/plans").json()
    assert len(plans) == 1
    plan_id = plans[0]["id"]
    detail = client.get(f"/api/plans/{plan_id}").json()
    assert detail["status"] == "ready"
    assert detail["word_count"] > 0
    assert all(s["content"] for s in detail["sections"])


def test_stream_then_export_and_delete(client, fake_embeddings, mock_openrouter):
    with client.stream(
        "POST",
        "/api/plans/generate/stream",
        json={"business_name": "PetPal", "sections": ["executive_summary"]},
    ) as response:
        response.read()

    plan_id = client.get("/api/plans").json()[0]["id"]
    export = client.get(f"/api/plans/{plan_id}/export")
    assert export.status_code == 200
    assert "Executive Summary" in export.text

    deleted = client.delete(f"/api/plans/{plan_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/plans/{plan_id}").status_code == 404
