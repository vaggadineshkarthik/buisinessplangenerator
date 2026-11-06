"""Chunking behaviour: size limits, overlap and page mapping."""
from __future__ import annotations

from app.rag.chunking import build_full_text, chunk_document
from app.rag.extraction import ExtractedDocument, ExtractedPage


def _doc(text: str) -> ExtractedDocument:
    return ExtractedDocument(pages=[ExtractedPage(page_number=1, text=text)], file_type="txt")


def test_chunk_size_is_respected():
    text = " ".join(f"sentence{i} about retrieval augmented generation." for i in range(200))
    chunks = chunk_document(_doc(text), chunk_size=300, chunk_overlap=50)
    assert len(chunks) > 1
    assert all(len(c.content) <= 300 for c in chunks)


def test_chunk_overlap_produces_shared_content():
    text = " ".join(f"word{i}" for i in range(400))
    chunks = chunk_document(_doc(text), chunk_size=200, chunk_overlap=80)
    assert len(chunks) >= 2
    first_tail = chunks[0].content[-40:]
    assert any(tok in chunks[1].content for tok in first_tail.split() if len(tok) > 3)


def test_chunk_indices_are_sequential():
    text = " ".join(f"token{i}" for i in range(300))
    chunks = chunk_document(_doc(text), chunk_size=150, chunk_overlap=20)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_page_numbers_are_mapped():
    doc = ExtractedDocument(
        pages=[
            ExtractedPage(page_number=1, text="Page one content about apples and oranges." * 5),
            ExtractedPage(page_number=2, text="Page two content about bananas and grapes." * 5),
        ],
        file_type="pdf",
    )
    chunks = chunk_document(doc, chunk_size=200, chunk_overlap=20)
    pages = {c.page_number for c in chunks}
    assert 1 in pages and 2 in pages


def test_empty_document_yields_no_chunks():
    assert chunk_document(_doc("   "), chunk_size=100, chunk_overlap=10) == []


def test_build_full_text_tracks_offsets():
    doc = ExtractedDocument(
        pages=[
            ExtractedPage(page_number=1, text="alpha"),
            ExtractedPage(page_number=2, text="beta"),
        ],
        file_type="pdf",
    )
    text, spans = build_full_text(doc.pages)
    assert spans[0][:2] == (1, 0)
    assert text[spans[1][1] : spans[1][1] + 4] == "beta"
