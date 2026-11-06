"""Relevance evaluation, context building, citations and answer verification.

Verification here is a lightweight, deterministic *support check*: it measures
how well each factual claim in an answer is backed by the retrieved chunks.
It is a signal, not a guarantee of correctness.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .retrieval import RetrievedChunk, keyword_overlap

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

DISCLAIMER = (
    "Automated verification is a heuristic support check. It does not guarantee "
    "that the answer is factually correct."
)


@dataclass
class ClaimCheck:
    claim: str
    supported: bool
    best_overlap: float
    source: str = ""


@dataclass
class VerificationResult:
    verdict: str  # verified | partially_verified | unverified | no_sources
    coverage: float
    claims: List[ClaimCheck] = field(default_factory=list)
    unsupported_claims: List[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "coverage": round(self.coverage, 4),
            "claims": [
                {
                    "claim": c.claim,
                    "supported": c.supported,
                    "best_overlap": round(c.best_overlap, 4),
                    "source": c.source,
                }
                for c in self.claims
            ],
            "unsupported_claims": self.unsupported_claims,
            "disclaimer": self.disclaimer,
        }


@dataclass
class RelevanceEvaluation:
    relevant: bool
    top_score: float
    avg_score: float
    chunk_count: int
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relevant": self.relevant,
            "top_score": round(self.top_score, 4),
            "avg_score": round(self.avg_score, 4),
            "chunk_count": self.chunk_count,
            "reason": self.reason,
        }


def evaluate_relevance(
    chunks: List[RetrievedChunk],
    threshold: float = 0.35,
) -> RelevanceEvaluation:
    """Decide whether retrieved chunks are good enough to answer the question."""
    if not chunks:
        return RelevanceEvaluation(
            relevant=False,
            top_score=0.0,
            avg_score=0.0,
            chunk_count=0,
            reason="No chunks passed the similarity threshold.",
        )
    top = max(c.score for c in chunks)
    avg = sum(c.score for c in chunks) / len(chunks)
    relevant = top >= threshold and avg >= threshold * 0.7
    reason = (
        f"Top similarity {top:.2f} with {len(chunks)} chunk(s) at or above the "
        f"{threshold:.2f} threshold."
        if relevant
        else f"Top similarity {top:.2f} below the {threshold:.2f} relevance threshold."
    )
    return RelevanceEvaluation(
        relevant=relevant,
        top_score=top,
        avg_score=avg,
        chunk_count=len(chunks),
        reason=reason,
    )


def build_context(chunks: List[RetrievedChunk]) -> str:
    """Render retrieved chunks as numbered, citation-tagged context blocks."""
    blocks: List[str] = []
    for i, chunk in enumerate(chunks, start=1):
        header = (
            f"[{i}] Document: {chunk.document_name} | Page: {chunk.page_number} | "
            f"Similarity: {chunk.score:.3f}"
        )
        blocks.append(f"{header}\n{chunk.content}")
    return "\n\n---\n\n".join(blocks)


def generate_citations(chunks: List[RetrievedChunk]) -> List[Dict[str, Any]]:
    """Produce structured citation objects for the frontend."""
    citations: List[Dict[str, Any]] = []
    for i, chunk in enumerate(chunks, start=1):
        citations.append(
            {
                "index": i,
                "document_id": chunk.document_id,
                "document_name": chunk.document_name,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "similarity": round(chunk.score, 4),
                "label": chunk.citation,
                "excerpt": chunk.content[:400],
            }
        )
    return citations


def _split_claims(answer: str) -> List[str]:
    if not answer:
        return []
    text = re.sub(r"```.*?```", " ", answer, flags=re.DOTALL)
    text = re.sub(r"[#*_>`]", " ", text)
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s and len(s.strip()) > 0]
    claims: List[str] = []
    for s in sentences:
        if len(s.split()) < 4:
            continue
        if re.fullmatch(r"\[Source:[^\]]+\]", s):
            continue
        claims.append(s)
    return claims


def verify_answer(
    answer: str,
    chunks: List[RetrievedChunk],
    support_threshold: float = 0.45,
) -> VerificationResult:
    """Check how well each claim in the answer is supported by retrieved chunks."""
    if not chunks:
        return VerificationResult(
            verdict="no_sources",
            coverage=0.0,
            claims=[],
            unsupported_claims=[],
        )

    claims = _split_claims(answer)
    if not claims:
        return VerificationResult(verdict="unverified", coverage=0.0, claims=[])

    checks: List[ClaimCheck] = []
    unsupported: List[str] = []
    for claim in claims:
        best = 0.0
        best_source = ""
        for chunk in chunks:
            overlap = keyword_overlap(claim, chunk.content)
            if overlap > best:
                best = overlap
                best_source = chunk.citation
        supported = best >= support_threshold
        if not supported:
            unsupported.append(claim)
        checks.append(
            ClaimCheck(claim=claim, supported=supported, best_overlap=best, source=best_source)
        )

    coverage = sum(1 for c in checks if c.supported) / len(checks)
    if coverage >= 0.8:
        verdict = "verified"
    elif coverage >= 0.4:
        verdict = "partially_verified"
    else:
        verdict = "unverified"

    return VerificationResult(
        verdict=verdict,
        coverage=coverage,
        claims=checks,
        unsupported_claims=unsupported,
    )
