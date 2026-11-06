"""Shared pytest fixtures.

The suite runs against an isolated temporary storage directory and replaces the
sentence-transformers model with a deterministic hashing embedder so that tests
are fast and never download a model from the internet.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

# --- Must be configured before the application package is imported ---
_TMP_STORAGE = Path(tempfile.mkdtemp(prefix="ragify-tests-"))
os.environ["RAGIFY_STORAGE_DIR"] = str(_TMP_STORAGE)
os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("OPENROUTER_MODEL", "openai/gpt-oss-120b")

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

EMBED_DIM = 384

MUTABLE_SETTINGS = [
    "openrouter_model",
    "openrouter_temperature",
    "openrouter_max_tokens",
    "top_k",
    "similarity_threshold",
    "chunk_size",
    "chunk_overlap",
    "max_file_size_mb",
    "embedding_model",
]


def _expand(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def fake_vector(text: str) -> list[float]:
    """Deterministic bag-of-words hashing embedding (cosine friendly)."""
    vec = [0.0] * EMBED_DIM
    for token in _expand(text):
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        h = int(digest, 16)
        idx = h % EMBED_DIM
        sign = 1.0 if (h >> 12) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        vec[0] = 1.0
        return vec
    return [v / norm for v in vec]


@pytest.fixture(scope="session", autouse=True)
def _cleanup_storage():
    yield
    shutil.rmtree(_TMP_STORAGE, ignore_errors=True)


@pytest.fixture
def fake_embeddings(monkeypatch):
    """Replace the real embedding model with the deterministic test embedder."""
    from app.rag.embeddings import embedding_service

    def embed_documents(texts):
        return [fake_vector(t) for t in texts]

    def embed_query(text):
        return fake_vector(text)

    async def aembed_documents(texts):
        return embed_documents(texts)

    async def aembed_query(text):
        return embed_query(text)

    async def aensure_loaded():
        return None

    monkeypatch.setattr(embedding_service, "embed_documents", embed_documents, raising=False)
    monkeypatch.setattr(embedding_service, "embed_query", embed_query, raising=False)
    monkeypatch.setattr(embedding_service, "aembed_documents", aembed_documents, raising=False)
    monkeypatch.setattr(embedding_service, "aembed_query", aembed_query, raising=False)
    monkeypatch.setattr(embedding_service, "aensure_loaded", aensure_loaded, raising=False)
    monkeypatch.setattr(embedding_service, "validate_dimensions", lambda vectors: None, raising=False)
    monkeypatch.setattr(embedding_service, "_dimension", EMBED_DIM, raising=False)
    return embedding_service


@pytest.fixture(autouse=True)
def reset_state(fake_embeddings):
    """Wipe the database and the vector store before every test."""
    from app import database as db
    from app.config import settings
    from app.rag.vector_store import vector_store

    db.init_db()
    conn = db.get_conn()
    for table in (
        "messages",
        "conversations",
        "chunks",
        "documents",
        "plan_sections",
        "plans",
        "app_settings",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()

    if vector_store._collection is not None and vector_store._client is not None:
        try:
            vector_store._client.delete_collection(vector_store._collection.name)
        except Exception:  # noqa: BLE001
            pass
        vector_store._collection = None

    # Restore runtime-mutable settings so tests never leak into each other.
    if not hasattr(reset_state, "_baseline"):
        reset_state._baseline = {attr: getattr(settings, attr) for attr in MUTABLE_SETTINGS}
    for attr, value in reset_state._baseline.items():
        setattr(settings, attr, value)
    yield


@pytest.fixture
def mock_openrouter(monkeypatch):
    """Configure OpenRouter with a fake key and deterministic mocked responses."""
    from app.services.openrouter import openrouter_client

    monkeypatch.setattr(openrouter_client, "_api_key", "test-key", raising=False)

    async def chat_completion(messages, **kwargs):
        return {
            "content": '{"rewritten_query": "revenue fiscal year 2024", '
            '"keywords": ["revenue", "2024"], "question_type": "factual"}',
            "model": "mock-model",
            "usage": {},
            "raw_finish_reason": "stop",
        }

    async def stream_chat(messages, **kwargs):
        for token in [
            "The company reported total revenue of 4.2 million dollars ",
            "in fiscal year 2024 ",
            "[Source: company_report.pdf, Page 4].",
        ]:
            yield token

    monkeypatch.setattr(openrouter_client, "chat_completion", chat_completion, raising=False)
    monkeypatch.setattr(openrouter_client, "stream_chat", stream_chat, raising=False)
    return openrouter_client


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_text() -> str:
    return (
        "RAGify AI is a retrieval augmented generation platform. "
        "It ingests documents and stores chunk embeddings in a vector database. "
        "The company reported revenue of 4.2 million dollars in the 2024 fiscal year. "
        "It was founded in 2021 and is headquartered in Bengaluru, India. "
        "Employees receive twenty vacation days per year."
    )


@pytest.fixture
def make_pdf(tmp_path):
    """Create a minimal, valid single-page PDF containing the given text."""

    def _make(text: str, filename: str = "sample.pdf") -> Path:
        content_stream = f"BT /F1 12 Tf 72 700 Td ({text}) Tj ET".encode("latin-1")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(content_stream)).encode() + b" >>\nstream\n"
            + content_stream
            + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for i, obj in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
        xref_offset = len(out)
        out += f"xref\n0 {len(objects) + 1}\n".encode()
        out += b"0000000000 65535 f \n"
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
        path = tmp_path / filename
        path.write_bytes(bytes(out))
        return path

    return _make


@pytest.fixture
def make_docx(tmp_path):
    def _make(text: str, filename: str = "sample.docx") -> Path:
        import docx

        document = docx.Document()
        for line in text.split(". "):
            if line.strip():
                document.add_paragraph(line.strip())
        path = tmp_path / filename
        document.save(str(path))
        return path

    return _make
