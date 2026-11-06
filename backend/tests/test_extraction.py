"""Document extraction and cleaning tests."""
from __future__ import annotations

import pytest

from app.rag.extraction import (
    ExtractionError,
    clean_text,
    extract_document,
    is_meaningful,
)


def test_extract_txt(tmp_path, sample_text):
    path = tmp_path / "notes.txt"
    path.write_text(sample_text, encoding="utf-8")
    doc = extract_document(path)
    assert doc.file_type == "txt"
    assert "RAGify AI" in doc.full_text
    assert doc.num_pages == 1
    assert doc.char_count > 50


def test_extract_txt_utf16(tmp_path):
    path = tmp_path / "wide.txt"
    path.write_text("Unicode content: caf\u00e9 na\u00efve", encoding="utf-16")
    doc = extract_document(path)
    assert "caf\u00e9" in doc.full_text.lower() or "caf" in doc.full_text.lower()


def test_extract_csv(tmp_path):
    path = tmp_path / "revenue.csv"
    path.write_text(
        "quarter,revenue,region\nQ1,1200000,North\nQ2,1400000,South\n",
        encoding="utf-8",
    )
    doc = extract_document(path)
    assert doc.file_type == "csv"
    assert "revenue: 1200000" in doc.full_text
    assert "Q1" in doc.full_text


def test_extract_pdf(make_pdf):
    path = make_pdf("RAGify AI revenue was 4.2 million dollars.")
    doc = extract_document(path)
    assert doc.file_type == "pdf"
    assert doc.num_pages == 1
    assert "RAGify" in doc.full_text


def test_extract_docx(make_docx):
    path = make_docx("RAGify AI is a platform. It stores embeddings.")
    doc = extract_document(path)
    assert doc.file_type == "docx"
    assert "platform" in doc.full_text


def test_extract_unsupported_type(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG\r\n")
    with pytest.raises(ExtractionError):
        extract_document(path)


def test_extract_empty_file_raises(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("   \n  ", encoding="utf-8")
    with pytest.raises(ExtractionError):
        extract_document(path)


def test_extract_missing_file_raises(tmp_path):
    with pytest.raises(ExtractionError):
        extract_document(tmp_path / "nope.txt")


def test_clean_text_normalises_whitespace_and_controls():
    dirty = "Hello\u0000   world\r\n\r\n\r\n\r\nSecond   paragraph\u00a0here"
    cleaned = clean_text(dirty)
    assert "\u0000" not in cleaned
    assert "\u00a0" not in cleaned
    assert "\r" not in cleaned
    assert "Hello world" in cleaned
    assert "\n\n\n" not in cleaned


def test_is_meaningful():
    assert not is_meaningful("short")
    assert is_meaningful("this is definitely long enough to matter")
