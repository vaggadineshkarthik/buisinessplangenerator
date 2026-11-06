"""Semantic retrieval: query embedding, vector search, filtering, reranking."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import settings
from .embeddings import embedding_service
from .vector_store import vector_store

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "of", "to", "in", "on",
    "for", "with", "is", "are", "was", "were", "be", "been", "being", "what",
    "which", "who", "whom", "this", "that", "these", "those", "it", "its", "as",
    "at", "by", "from", "how", "why", "when", "where", "does", "do", "did",
    "can", "could", "should", "would", "will", "about", "into", "than", "there",
}


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS]


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_name: str
    page_number: int
    content: str
    score: float
    char_start: int = 0
    char_end: int = 0
    chunk_index: int = 0
    source: str = ""
    rerank_score: float = 0.0

    @property
    def similarity(self) -> float:
        return round(self.score, 4)

    @property
    def citation(self) -> str:
        return f"[Source: {self.document_name}, Page {self.page_number}]"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "page_number": self.page_number,
            "content": self.content,
            "score": round(self.score, 4),
            "similarity": self.similarity,
            "rerank_score": round(self.rerank_score, 4),
            "char_start": self.char_start,
            "char_end": self.char_end,
            "chunk_index": self.chunk_index,
            "source": self.source,
            "citation": self.citation,
        }


@dataclass
class RetrievalResult:
    query: str
    chunks: List[RetrievedChunk] = field(default_factory=list)
    candidates: int = 0
    threshold: float = 0.0
    top_k: int = 0
    embedding_dimension: Optional[int] = None

    @property
    def has_results(self) -> bool:
        return len(self.chunks) > 0

    @property
    def top_score(self) -> float:
        return round(self.chunks[0].score, 4) if self.chunks else 0.0

    @property
    def avg_score(self) -> float:
        if not self.chunks:
            return 0.0
        return round(sum(c.score for c in self.chunks) / len(self.chunks), 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "candidates": self.candidates,
            "returned": len(self.chunks),
            "threshold": self.threshold,
            "top_k": self.top_k,
            "top_score": self.top_score,
            "avg_score": self.avg_score,
            "chunks": [c.to_dict() for c in self.chunks],
        }


def deduplicate(chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
    """Remove near-identical chunks keeping the highest scoring copy."""
    kept: List[RetrievedChunk] = []
    seen_ids = set()
    seen_texts: List[str] = []
    for chunk in chunks:
        if chunk.chunk_id in seen_ids:
            continue
        norm = re.sub(r"\s+", " ", chunk.content.lower()).strip()
        fingerprint = norm[:240]
        duplicate = False
        for existing in seen_texts:
            if fingerprint and (fingerprint == existing or fingerprint in existing or existing in fingerprint):
                duplicate = True
                break
        if duplicate:
            continue
        seen_ids.add(chunk.chunk_id)
        seen_texts.append(fingerprint)
        kept.append(chunk)
    return kept


def keyword_overlap(query: str, content: str) -> float:
    q_tokens = set(tokenize(query))
    if not q_tokens:
        return 0.0
    c_tokens = set(tokenize(content))
    if not c_tokens:
        return 0.0
    return len(q_tokens & c_tokens) / len(q_tokens)


def rerank(chunks: List[RetrievedChunk], query: str, top_n: Optional[int] = None) -> List[RetrievedChunk]:
    """Blend vector similarity with lexical overlap and sort by the blend."""
    for chunk in chunks:
        overlap = keyword_overlap(query, chunk.content)
        chunk.rerank_score = round(0.75 * chunk.score + 0.25 * overlap, 6)
    ranked = sorted(chunks, key=lambda c: c.rerank_score, reverse=True)
    if top_n:
        ranked = ranked[:top_n]
    return ranked


def _record_to_chunk(record) -> RetrievedChunk:
    meta = record.metadata or {}
    return RetrievedChunk(
        chunk_id=str(record.id),
        document_id=str(meta.get("document_id", "")),
        document_name=str(meta.get("document_name", "unknown")),
        page_number=int(meta.get("page_number", 0) or 0),
        content=record.content or "",
        score=float(record.score),
        char_start=int(meta.get("char_start", 0) or 0),
        char_end=int(meta.get("char_end", 0) or 0),
        chunk_index=int(meta.get("chunk_index", 0) or 0),
        source=str(meta.get("source", "")),
    )


async def retrieve(
    question: str,
    document_ids: Optional[List[str]] = None,
    top_k: Optional[int] = None,
    threshold: Optional[float] = None,
) -> RetrievalResult:
    """Embed the query and return the most relevant, filtered chunks."""
    top_k = int(top_k or settings.top_k)
    threshold = float(threshold if threshold is not None else settings.similarity_threshold)

    query_embedding = await embedding_service.aembed_query(question)
    # Over-fetch so deduplication/reranking still leave enough candidates.
    fetch_k = max(top_k * 4, top_k + 5)
    records = vector_store.query(
        query_embedding=query_embedding,
        top_k=fetch_k,
        document_ids=document_ids,
    )
    chunks = [_record_to_chunk(r) for r in records]
    candidates = len(chunks)

    chunks = [c for c in chunks if c.score >= threshold]
    chunks = deduplicate(chunks)
    chunks = rerank(chunks, question, top_n=top_k)

    return RetrievalResult(
        query=question,
        chunks=chunks,
        candidates=candidates,
        threshold=threshold,
        top_k=top_k,
        embedding_dimension=embedding_service.dimension,
    )
