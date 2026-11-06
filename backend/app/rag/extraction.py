"""Document text extraction and cleaning.

Supports PDF, DOCX, TXT and CSV. Returns a page-aware representation of the
document so that chunk metadata can carry a real page number where available.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from ..config import settings


class ExtractionError(Exception):
    """Raised when a document cannot be read or contains no usable text."""


@dataclass
class ExtractedPage:
    page_number: int
    text: str


@dataclass
class ExtractedDocument:
    pages: List[ExtractedPage] = field(default_factory=list)
    file_type: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)

    @property
    def num_pages(self) -> int:
        return len(self.pages)

    @property
    def char_count(self) -> int:
        return sum(len(p.text) for p in self.pages)


# --------------------------------------------------------------------------
# Cleaning
# --------------------------------------------------------------------------
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    """Normalise unicode, strip control characters and collapse whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\ufeff", "")
    text = _CONTROL_CHARS.sub(" ", text)
    # Collapse runs of spaces/tabs but keep paragraph breaks.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def is_meaningful(text: str, min_chars: int = 20) -> bool:
    return len(re.sub(r"\s", "", text or "")) >= min_chars


# --------------------------------------------------------------------------
# Extractors
# --------------------------------------------------------------------------
def _extract_pdf(path: Path) -> ExtractedDocument:
    from pypdf import PdfReader

    doc = ExtractedDocument(file_type="pdf")
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"Unable to open PDF: {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:  # noqa: BLE001
            raise ExtractionError("PDF is password protected and cannot be read.")

    for idx, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            doc.warnings.append(f"Page {idx} could not be parsed: {exc}")
            raw = ""
        doc.pages.append(ExtractedPage(page_number=idx, text=clean_text(raw)))

    if not doc.pages:
        raise ExtractionError("PDF contains no pages.")
    return doc


def _extract_docx(path: Path) -> ExtractedDocument:
    import docx  # python-docx

    doc = ExtractedDocument(file_type="docx")
    try:
        document = docx.Document(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"Unable to open DOCX: {exc}") from exc

    blocks: List[str] = []
    for para in document.paragraphs:
        if para.text and para.text.strip():
            blocks.append(para.text)
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
            if cells:
                blocks.append(" | ".join(cells))

    text = clean_text("\n\n".join(blocks))
    if not is_meaningful(text):
        raise ExtractionError("DOCX contains no extractable text.")
    doc.pages.append(ExtractedPage(page_number=1, text=text))
    return doc


def _extract_txt(path: Path) -> ExtractedDocument:
    doc = ExtractedDocument(file_type="txt")
    raw_bytes = path.read_bytes()
    if not raw_bytes.strip():
        raise ExtractionError("Text file is empty.")

    text = ""
    for encoding in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        raise ExtractionError("Unable to decode text file with a supported encoding.")

    text = clean_text(text)
    if not is_meaningful(text):
        raise ExtractionError("Text file contains no usable content.")
    doc.pages.append(ExtractedPage(page_number=1, text=text))
    return doc


def _extract_csv(path: Path) -> ExtractedDocument:
    doc = ExtractedDocument(file_type="csv")
    raw_bytes = path.read_bytes()
    if not raw_bytes.strip():
        raise ExtractionError("CSV file is empty.")

    text = ""
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader]
    if not rows:
        raise ExtractionError("CSV file contains no rows.")

    header = rows[0]
    rendered: List[str] = ["# Columns: " + ", ".join(h.strip() for h in header if h.strip())]
    for i, row in enumerate(rows[1:], start=2):
        pairs = []
        for col_idx, value in enumerate(row):
            col_name = header[col_idx].strip() if col_idx < len(header) else f"col_{col_idx + 1}"
            if value and value.strip():
                pairs.append(f"{col_name}: {value.strip()}")
        if pairs:
            rendered.append(f"Row {i}: " + "; ".join(pairs))

    content = clean_text("\n".join(rendered))
    if not is_meaningful(content):
        raise ExtractionError("CSV file contains no usable data rows.")
    doc.pages.append(ExtractedPage(page_number=1, text=content))
    return doc


_EXTRACTORS = {
    "pdf": _extract_pdf,
    "docx": _extract_docx,
    "txt": _extract_txt,
    "csv": _extract_csv,
}


def supported_extensions() -> List[str]:
    return list(settings.allowed_extensions)


def extract_document(file_path: str | Path, file_type: str | None = None) -> ExtractedDocument:
    """Extract and clean text from a supported document."""
    path = Path(file_path)
    if not path.exists():
        raise ExtractionError(f"File not found: {path.name}")

    ext = (file_type or path.suffix.lstrip(".")).lower().lstrip(".")
    if ext not in _EXTRACTORS:
        raise ExtractionError(f"Unsupported file type: .{ext}")

    document = _EXTRACTORS[ext](path)
    if document.char_count == 0:
        raise ExtractionError("No text could be extracted from the document.")
    return document
