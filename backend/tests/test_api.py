"""End-to-end API tests for documents, chat, conversations and settings."""
from __future__ import annotations

import json

DOC_TEXT = (
    "RAGify AI is a retrieval augmented generation platform. "
    "Total revenue for fiscal year 2024 was 4.2 million dollars. "
    "The company was founded in 2021 and is headquartered in Bengaluru, India. "
    "Employees receive twenty vacation days per calendar year."
)


def _upload(client, name: str = "company_report.txt", content: str = DOC_TEXT):
    return client.post(
        "/api/documents/upload",
        files=[("files", (name, content.encode("utf-8"), "text/plain"))],
        params={"process_inline": "true"},
    )


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "vector_store" in body


def test_upload_and_list_documents(client):
    response = _upload(client)
    assert response.status_code == 201
    body = response.json()
    assert len(body["accepted"]) == 1
    doc = body["accepted"][0]
    assert doc["status"] == "ready"
    assert doc["num_chunks"] >= 1

    listing = client.get("/api/documents")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_upload_rejects_unsupported_extension(client):
    response = client.post(
        "/api/documents/upload",
        files=[("files", ("malware.exe", b"MZ\x90\x00", "application/octet-stream"))],
        params={"process_inline": "true"},
    )
    assert response.status_code == 400


def test_upload_rejects_duplicate(client):
    _upload(client)
    second = _upload(client, name="copy.txt")
    assert second.status_code == 400
    assert "Duplicate" in json.dumps(second.json())


def test_get_document_and_chunks(client):
    doc_id = _upload(client).json()["accepted"][0]["id"]
    detail = client.get(f"/api/documents/{doc_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == doc_id

    chunks = client.get(f"/api/documents/{doc_id}/chunks")
    assert chunks.status_code == 200
    assert chunks.json()["total_chunks"] >= 1


def test_get_missing_document_returns_404(client):
    assert client.get("/api/documents/does-not-exist").status_code == 404


def test_delete_document_removes_embeddings(client, fake_embeddings):
    from app.rag.vector_store import vector_store

    doc_id = _upload(client).json()["accepted"][0]["id"]
    assert vector_store.count() >= 1

    deleted = client.delete(f"/api/documents/{doc_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert vector_store.count() == 0
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_reprocess_document(client):
    doc_id = _upload(client).json()["accepted"][0]["id"]
    response = client.post(f"/api/documents/{doc_id}/reprocess")
    assert response.status_code == 200
    assert response.json()["status"] in ("processing", "ready")


def test_search_endpoint(client):
    _upload(client)
    response = client.post("/api/search", json={"query": "revenue fiscal year 2024", "top_k": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["returned"] >= 1
    assert "revenue" in body["chunks"][0]["content"].lower()


def test_chat_without_api_key_returns_503(client):
    _upload(client)
    response = client.post("/api/chat", json={"question": "What was the revenue?"})
    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in json.dumps(response.json())


def test_chat_endpoint_with_mocked_llm(client, mock_openrouter):
    _upload(client)
    response = client.post("/api/chat", json={"question": "What was the revenue in 2024?"})
    assert response.status_code == 200
    body = response.json()
    assert "4.2 million" in body["answer"]
    assert body["citations"]
    assert body["conversation_id"]

    convs = client.get("/api/conversations").json()
    assert len(convs) == 1
    detail = client.get(f"/api/conversations/{body['conversation_id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]


def test_chat_stream_emits_sse_events(client, mock_openrouter):
    _upload(client)
    events = []
    with client.stream(
        "POST", "/api/chat/stream", json={"question": "What was the revenue in 2024?"}
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())

    assert "conversation" in events
    assert "token" in events
    assert "result" in events
    assert "done" in events


def test_chat_stream_without_key_emits_error(client):
    response = client.post(
        "/api/chat/stream", json={"question": "anything"}
    )
    body = response.text
    assert "event: error" in body
    assert "OPENROUTER_API_KEY" in body


def test_regenerate_endpoint(client, mock_openrouter):
    _upload(client)
    chat = client.post("/api/chat", json={"question": "What was the revenue in 2024?"}).json()
    conv_id = chat["conversation_id"]

    with client.stream("POST", "/api/chat/regenerate", json={"conversation_id": conv_id}) as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())
    assert "event: result" in text

    detail = client.get(f"/api/conversations/{conv_id}").json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]


def test_regenerate_missing_conversation_returns_404(client, mock_openrouter):
    response = client.post("/api/chat/regenerate", json={"conversation_id": "nope"})
    assert response.status_code == 404


def test_conversation_crud(client):
    created = client.post("/api/conversations", json={"title": "My research"})
    assert created.status_code == 201
    conv_id = created.json()["id"]

    assert client.get("/api/conversations").status_code == 200
    assert client.get(f"/api/conversations/{conv_id}").json()["title"] == "My research"
    assert client.delete(f"/api/conversations/{conv_id}").status_code == 200
    assert client.get(f"/api/conversations/{conv_id}").status_code == 404


def test_settings_endpoint_never_exposes_api_key(client):
    response = client.get("/api/settings")
    assert response.status_code == 200
    body = response.json()
    assert "openrouter" in body
    assert body["openrouter"]["configured"] is False
    assert "api_key" not in json.dumps(body).lower() or "OPENROUTER_API_KEY" not in json.dumps(body)
    assert "OPENROUTER_API_KEY" not in response.text


def test_update_settings(client):
    response = client.put("/api/settings", json={"top_k": 3, "similarity_threshold": 0.4})
    assert response.status_code == 200
    values = response.json()["values"]
    assert values["top_k"] == 3
    assert values["similarity_threshold"] == 0.4

    from app.config import settings

    assert settings.top_k == 3


def test_update_settings_validates_ranges(client):
    assert client.put("/api/settings", json={"top_k": 0}).status_code == 422
    assert client.put("/api/settings", json={"temperature": 5}).status_code == 422


def test_stats_endpoint(client):
    _upload(client)
    response = client.get("/api/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == 1
    assert body["total_chunks"] >= 1


def test_chat_validates_empty_question(client, mock_openrouter):
    assert client.post("/api/chat", json={"question": ""}).status_code == 422
