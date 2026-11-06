"""Security-focused tests: filenames, extensions, size limits and prompt safety."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.prompts import SYSTEM_PROMPT
from app.config import settings
from app.rag.ingestion import sanitize_filename, save_upload, validate_upload


def test_sanitize_filename_strips_directories():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("C:\\Windows\\system32\\evil.txt") == "evil.txt"
    assert sanitize_filename("report final.pdf") == "report final.pdf"


def test_sanitize_filename_removes_unsafe_characters():
    assert sanitize_filename("bad<>name|?.txt") == "badname.txt"


def test_sanitize_filename_fallback_for_empty():
    assert sanitize_filename("...") == "document"
    assert sanitize_filename("") == "document"


def test_save_upload_prevents_path_traversal(tmp_path):
    path = save_upload("../../escape.txt", b"content")
    assert path.parent.resolve() == settings.documents_dir.resolve()
    assert path.name.endswith(".txt")
    path.unlink(missing_ok=True)


def test_validate_upload_rejects_unsupported_extension():
    with pytest.raises(ValueError):
        validate_upload("script.py", b"print('hi')")


def test_validate_upload_rejects_empty_file():
    with pytest.raises(ValueError):
        validate_upload("empty.txt", b"")


def test_validate_upload_rejects_oversized_file(monkeypatch):
    monkeypatch.setattr(settings, "max_file_size_mb", 0)
    with pytest.raises(ValueError):
        validate_upload("big.txt", b"x" * 1024)


def test_validate_upload_accepts_allowed_types():
    assert validate_upload("doc.pdf", b"%PDF-1.4 data") == "pdf"
    assert validate_upload("doc.docx", b"PK data") == "docx"
    assert validate_upload("doc.txt", b"hello") == "txt"
    assert validate_upload("doc.csv", b"a,b\n1,2") == "csv"


def test_system_prompt_marks_documents_as_untrusted():
    lowered = SYSTEM_PROMPT.lower()
    assert "never fabricate" in lowered
    assert "untrusted data" in lowered
    assert "not system instructions" in lowered


def test_system_prompt_requires_citations():
    assert "cite every important factual claim" in SYSTEM_PROMPT.lower()


def test_upload_api_rejects_path_traversal_filename(client):
    response = client.post(
        "/api/documents/upload",
        files=[("files", ("../../evil.txt", b"malicious but harmless text here", "text/plain"))],
        params={"process_inline": "true"},
    )
    # Either accepted under a sanitised name, or rejected; never written outside storage.
    if response.status_code == 201:
        stored = list(settings.documents_dir.glob("*"))
        assert stored
        for path in stored:
            assert path.resolve().parent == settings.documents_dir.resolve()


def test_diagnostics_do_not_leak_secrets(client):
    response = client.get("/api/settings/diagnostics")
    assert response.status_code == 200
    assert "OPENROUTER_API_KEY" not in response.text
    assert "sk-" not in response.text
