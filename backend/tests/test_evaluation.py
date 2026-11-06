"""Citation generation, relevance evaluation and answer verification tests."""
from __future__ import annotations

from app.rag.evaluation import (
    build_context,
    evaluate_relevance,
    generate_citations,
    verify_answer,
)
from app.rag.retrieval import RetrievedChunk


def _chunk(text: str, score: float = 0.8, page: int = 4, name: str = "company_report.pdf"):
    return RetrievedChunk(
        chunk_id=f"{name}:{page}",
        document_id="doc1",
        document_name=name,
        page_number=page,
        content=text,
        score=score,
        chunk_index=0,
        source=name,
    )


def test_citation_format_matches_required_label():
    chunk = _chunk("Total revenue for fiscal year 2024 was 4.2 million dollars.")
    assert chunk.citation == "[Source: company_report.pdf, Page 4]"


def test_generate_citations_structure():
    chunks = [_chunk("revenue is 4.2 million", page=4), _chunk("founded in 2021", page=1)]
    citations = generate_citations(chunks)
    assert len(citations) == 2
    assert citations[0]["document_name"] == "company_report.pdf"
    assert citations[0]["page_number"] == 4
    assert citations[0]["label"].startswith("[Source:")


def test_build_context_includes_headers():
    context = build_context([_chunk("Some evidence text.")])
    assert "Document: company_report.pdf" in context
    assert "Page: 4" in context
    assert "Some evidence text." in context


def test_evaluate_relevance_true_for_high_scores():
    chunks = [_chunk("evidence", score=0.85), _chunk("more evidence", score=0.7)]
    evaluation = evaluate_relevance(chunks, threshold=0.35)
    assert evaluation.relevant is True


def test_evaluate_relevance_false_without_chunks():
    evaluation = evaluate_relevance([], threshold=0.35)
    assert evaluation.relevant is False
    assert evaluation.reason


def test_evaluate_relevance_false_for_low_scores():
    evaluation = evaluate_relevance([_chunk("weak", score=0.1)], threshold=0.35)
    assert evaluation.relevant is False


def test_verify_answer_supports_claims_from_context():
    chunk = _chunk("Total revenue for fiscal year 2024 was 4.2 million dollars for the company.")
    answer = "The company reported total revenue of 4.2 million dollars in fiscal year 2024."
    result = verify_answer(answer, [chunk])
    assert result.verdict in ("verified", "partially_verified")
    assert result.coverage > 0


def test_verify_answer_flags_unsupported_claims():
    chunk = _chunk("The company sells cloud software products.")
    answer = "The company was founded in 1820 by Napoleon Bonaparte in Paris."
    result = verify_answer(answer, [chunk])
    assert result.verdict in ("unverified", "partially_verified")
    assert result.unsupported_claims
    assert result.coverage < 0.8


def test_verify_answer_without_sources():
    result = verify_answer("Anything at all here.", [])
    assert result.verdict == "no_sources"


def test_verification_disclaimer_is_present():
    result = verify_answer("The company reported revenue of 4.2 million dollars.", [_chunk("revenue 4.2 million dollars")])
    assert "not guarantee" in result.disclaimer.lower()
