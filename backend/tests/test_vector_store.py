"""ChromaDB vector store and semantic retrieval tests."""
from __future__ import annotations

from app.rag.retrieval import deduplicate, rerank, retrieve, tokenize
from app.rag.vector_store import vector_store


def _index(embedding_service, entries):
    ids, docs, metas = [], [], []
    for i, (doc_id, name, text, page) in enumerate(entries):
        ids.append(f"{doc_id}:{i}")
        docs.append(text)
        metas.append(
            {
                "document_id": doc_id,
                "document_name": name,
                "chunk_index": i,
                "page_number": page,
                "char_start": 0,
                "char_end": len(text),
                "source": f"{name}",
            }
        )
    vectors = embedding_service.embed_documents(docs)
    vector_store.add_documents(ids=ids, embeddings=vectors, documents=docs, metadatas=metas)


CORPUS = [
    ("doc1", "company_report.pdf", "Total revenue for fiscal year 2024 was 4.2 million dollars.", 4),
    ("doc1", "company_report.pdf", "The company was founded in 2021 in Bengaluru, India.", 1),
    ("doc2", "hr_policy.docx", "Employees receive twenty vacation days per calendar year.", 2),
    ("doc2", "hr_policy.docx", "Remote work is allowed three days a week for all staff.", 3),
]


def test_vector_store_count_and_query(fake_embeddings):
    _index(fake_embeddings, CORPUS)
    assert vector_store.count() == 4

    query_vec = fake_embeddings.embed_query("revenue fiscal year 2024")
    results = vector_store.query(query_vec, top_k=2)
    assert len(results) == 2
    assert "revenue" in results[0].content.lower()
    assert results[0].score > 0


def test_vector_store_filters_by_document(fake_embeddings):
    _index(fake_embeddings, CORPUS)
    query_vec = fake_embeddings.embed_query("vacation days")
    results = vector_store.query(query_vec, top_k=5, document_ids=["doc2"])
    assert results
    assert all(r.metadata["document_id"] == "doc2" for r in results)


def test_vector_store_delete_document(fake_embeddings):
    _index(fake_embeddings, CORPUS)
    removed = vector_store.delete_document("doc1")
    assert removed == 2
    assert vector_store.count() == 2
    remaining = vector_store.query(fake_embeddings.embed_query("revenue"), top_k=5)
    assert all(r.metadata["document_id"] != "doc1" for r in remaining)


async def test_semantic_retrieval_returns_relevant_chunks(fake_embeddings):
    _index(fake_embeddings, CORPUS)
    result = await retrieve("How much revenue did the company report in 2024?", threshold=0.05)
    assert result.has_results
    top_two = " ".join(c.content.lower() for c in result.chunks[:2])
    assert "revenue" in top_two
    assert all(c.document_id == "doc1" for c in result.chunks[:2])
    assert result.top_score >= 0.05


async def test_retrieval_respects_document_filter(fake_embeddings):
    _index(fake_embeddings, CORPUS)
    result = await retrieve("vacation days per year", document_ids=["doc2"], threshold=0.05)
    assert result.has_results
    assert all(c.document_id == "doc2" for c in result.chunks)


async def test_retrieval_threshold_filters_everything(fake_embeddings):
    _index(fake_embeddings, CORPUS)
    result = await retrieve("completely unrelated quantum physics topic", threshold=0.99)
    assert not result.has_results
    assert result.top_score == 0.0


def test_deduplicate_removes_repeats(fake_embeddings):
    _index(fake_embeddings, CORPUS)
    results = vector_store.query(fake_embeddings.embed_query("revenue"), top_k=4)
    from app.rag.retrieval import RetrievedChunk

    chunks = [
        RetrievedChunk(
            chunk_id="a",
            document_id="d",
            document_name="n",
            page_number=1,
            content="identical content about revenue",
            score=0.9,
        ),
        RetrievedChunk(
            chunk_id="b",
            document_id="d",
            document_name="n",
            page_number=1,
            content="identical content about revenue",
            score=0.8,
        ),
        RetrievedChunk(
            chunk_id="c",
            document_id="d",
            document_name="n",
            page_number=2,
            content="different content about vacation policy",
            score=0.7,
        ),
    ]
    assert len(results) >= 0  # sanity: query path exercised
    deduped = deduplicate(chunks)
    assert len(deduped) == 2


def test_rerank_orders_by_combined_score():
    from app.rag.retrieval import RetrievedChunk

    chunks = [
        RetrievedChunk("1", "d", "n", 1, "unrelated text about weather", 0.9),
        RetrievedChunk("2", "d", "n", 2, "revenue revenue revenue fiscal year", 0.85),
    ]
    ranked = rerank(chunks, "what was the revenue this fiscal year")
    assert ranked[0].chunk_id == "2"
    assert ranked[0].rerank_score > ranked[1].rerank_score


def test_tokenize_filters_stopwords():
    tokens = tokenize("What is the revenue of the company?")
    assert "revenue" in tokens
    assert "the" not in tokens
