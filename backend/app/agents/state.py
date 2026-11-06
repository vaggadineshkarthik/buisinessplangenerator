"""Shared state definition for the LangGraph RAG workflow."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class RAGState(TypedDict, total=False):
    # inputs
    question: str
    conversation_history: List[Dict[str, str]]
    document_ids: List[str]
    model: Optional[str]
    temperature: Optional[float]
    max_tokens: Optional[int]

    # analysis
    analysis: Dict[str, Any]

    # retrieval
    retrieved_chunks: List[Dict[str, Any]]
    retrieval_stats: Dict[str, Any]

    # evaluation
    relevance: Dict[str, Any]

    # context
    context: str

    # generation
    answer: str
    citations: List[Dict[str, Any]]

    # verification
    verification: Dict[str, Any]

    # control
    retry_count: int
    needs_retry: bool
    route: str
    status: str
    errors: List[str]


def new_state(**overrides: Any) -> RAGState:
    base: RAGState = {
        "question": "",
        "conversation_history": [],
        "document_ids": [],
        "model": None,
        "temperature": None,
        "max_tokens": None,
        "analysis": {},
        "retrieved_chunks": [],
        "retrieval_stats": {},
        "relevance": {},
        "context": "",
        "answer": "",
        "citations": [],
        "verification": {},
        "retry_count": 0,
        "needs_retry": False,
        "route": "",
        "status": "pending",
        "errors": [],
    }
    base.update(overrides)  # type: ignore[arg-type]
    return base
