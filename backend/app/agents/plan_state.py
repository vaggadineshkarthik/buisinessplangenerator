"""Shared state definition for the LangGraph business-plan workflow."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class PlanState(TypedDict, total=False):
    # inputs
    business_name: str
    industry: str
    notes: str
    inputs: Dict[str, Any]
    document_ids: List[str]
    model: Optional[str]
    temperature: Optional[float]
    max_tokens: Optional[int]

    # plan of work
    sections: List[Dict[str, Any]]
    current_index: int

    # grounding
    context: str
    citations: List[Dict[str, Any]]
    retrieval_stats: Dict[str, Any]

    # accumulated output
    written: List[Dict[str, Any]]
    overview: str

    # control
    status: str
    errors: List[str]


def new_plan_state(**overrides: Any) -> PlanState:
    base: PlanState = {
        "business_name": "",
        "industry": "",
        "notes": "",
        "inputs": {},
        "document_ids": [],
        "model": None,
        "temperature": None,
        "max_tokens": None,
        "sections": [],
        "current_index": 0,
        "context": "",
        "citations": [],
        "retrieval_stats": {},
        "written": [],
        "overview": "",
        "status": "pending",
        "errors": [],
    }
    base.update(overrides)  # type: ignore[arg-type]
    return base
