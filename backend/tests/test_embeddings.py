"""Embedding service tests (deterministic test embedder + dimension validation)."""
from __future__ import annotations

import math
import os

import pytest

from app.rag.embeddings import EmbeddingError, EmbeddingService


def test_embed_documents_returns_one_vector_per_text(fake_embeddings):
    vectors = fake_embeddings.embed_documents(["alpha beta", "gamma delta", "epsilon"])
    assert len(vectors) == 3
    assert all(len(v) == 384 for v in vectors)


def test_embeddings_are_normalised(fake_embeddings):
    (vector,) = fake_embeddings.embed_documents(["normalisation check"])
    norm = math.sqrt(sum(v * v for v in vector))
    assert abs(norm - 1.0) < 1e-6


def test_empty_input_returns_empty_list(fake_embeddings):
    assert fake_embeddings.embed_documents([]) == []


def test_query_embedding_has_expected_dimension(fake_embeddings):
    vector = fake_embeddings.embed_query("how much revenue in 2024")
    assert len(vector) == 384


def test_similar_text_scores_higher_than_unrelated(fake_embeddings):
    a = fake_embeddings.embed_query("revenue in 2024 fiscal year")
    b = fake_embeddings.embed_query("revenue 2024 fiscal year")
    c = fake_embeddings.embed_query("vacation days policy")
    sim_ab = sum(x * y for x, y in zip(a, b))
    sim_ac = sum(x * y for x, y in zip(a, c))
    assert sim_ab > sim_ac


def test_validate_dimensions_rejects_mismatch():
    service = EmbeddingService(model_name="dummy")
    service._dimension = 3
    with pytest.raises(EmbeddingError):
        service.validate_dimensions([[1.0, 2.0, 3.0], [1.0, 2.0]])


def test_validate_dimensions_accepts_matching():
    service = EmbeddingService(model_name="dummy")
    service._dimension = 2
    service.validate_dimensions([[1.0, 2.0], [3.0, 4.0]])


def test_status_reports_configuration():
    service = EmbeddingService(model_name="BAAI/bge-small-en-v1.5")
    status = service.status()
    assert status["model"] == "BAAI/bge-small-en-v1.5"
    assert status["loaded"] is False


@pytest.mark.skipif(
    os.environ.get("RAGIFY_RUN_SLOW") != "1",
    reason="Set RAGIFY_RUN_SLOW=1 to download and test the real embedding model.",
)
def test_real_model_produces_384_dimension_vectors():
    service = EmbeddingService()
    service.ensure_loaded()
    vectors = service.embed_documents(["retrieval augmented generation", "unrelated sentence"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384
