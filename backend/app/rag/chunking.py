"""Text chunking with configurable size and overlap.

The chunker works on character offsets so every chunk can be traced back to a
page number and an exact location inside the source document.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

from .extraction import ExtractedDocument, ExtractedPage

PAGE_SEPARATOR = "\n\n"


@dataclass
class Chunk:
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    page_number: int
    token_estimate: int

    @property
    def length(self) -> int:
        return len(self.content)


def build_full_text(pages: List[ExtractedPage]) -> Tuple[str, List[Tuple[int, int, int]]]:
    """Join page texts and return the text plus (page_number, start, end) spans."""
    parts: List[str] = []
    spans: List[Tuple[int, int, int]] = []
    cursor = 0
    for page in pages:
        text = page.text or ""
        start = cursor
        parts.append(text)
        cursor += len(text)
        spans.append((page.page_number, start, cursor))
        cursor += len(PAGE_SEPARATOR)
        parts.append(PAGE_SEPARATOR)
    return "".join(parts), spans


def _estimate_tokens(text: str) -> int:
    # Rough heuristic: ~4 characters per token for English prose.
    return max(1, len(text) // 4)


def _best_break(text: str, start: int, hard_end: int) -> int:
    """Find the nicest possible cut point at or before ``hard_end``."""
    window_start = start + int((hard_end - start) * 0.55)
    window = text[window_start:hard_end]
    for pattern in (r"\n\n", r"[.!?]\s", r"\s"):
        matches = list(re.finditer(pattern, window))
        if matches:
            return window_start + matches[-1].end()
    return hard_end


def _page_for_offset(spans: List[Tuple[int, int, int]], offset: int) -> int:
    for page_number, start, end in spans:
        if start <= offset < end:
            return page_number
    return spans[-1][0] if spans else 1


def chunk_document(
    document: ExtractedDocument,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> List[Chunk]:
    """Split an extracted document into overlapping chunks with page metadata.

    A sliding window over the full document text guarantees that every chunk is
    at most ``chunk_size`` characters and that consecutive chunks share roughly
    ``chunk_overlap`` characters.
    """
    from ..config import settings

    chunk_size = int(chunk_size or settings.chunk_size)
    chunk_overlap = int(chunk_overlap if chunk_overlap is not None else settings.chunk_overlap)
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size // 5)

    full_text, spans = build_full_text(document.pages)
    if not full_text.strip():
        return []

    total = len(full_text)
    chunks: List[Chunk] = []
    start = 0
    while start < total:
        hard_end = min(start + chunk_size, total)
        end = total if hard_end >= total else _best_break(full_text, start, hard_end)

        # Trim surrounding whitespace while keeping offsets consistent.
        s, e = start, end
        while s < e and full_text[s].isspace():
            s += 1
        while e > s and full_text[e - 1].isspace():
            e -= 1
        content = full_text[s:e]
        if content.strip():
            chunks.append(
                Chunk(
                    chunk_index=len(chunks),
                    content=content,
                    char_start=s,
                    char_end=e,
                    page_number=_page_for_offset(spans, s),
                    token_estimate=_estimate_tokens(content),
                )
            )

        if end >= total:
            break
        next_start = end - chunk_overlap
        if next_start <= start:
            next_start = start + 1
        start = next_start

    # Deduplicate identical chunks (can happen with heavy overlap).
    deduped: List[Chunk] = []
    seen: set[str] = set()
    for ch in chunks:
        key = ch.content.strip()
        if key in seen:
            continue
        seen.add(key)
        ch.chunk_index = len(deduped)
        deduped.append(ch)
    return deduped
