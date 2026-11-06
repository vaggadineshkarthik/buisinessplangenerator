"""LangGraph workflow assembly for business-plan generation.

Workflow:
    Inputs -> Analyse -> Gather context (optional retrieval)
           -> Write section -> More sections?
                YES -> Write section (loop)
                NO  -> Finalise -> Plan
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from .plan_nodes import (
    analyze_inputs,
    finalize_plan,
    gather_context,
    write_section,
)
from .plan_state import PlanState, new_plan_state

_graph = None


def _route_after_write(state: PlanState) -> str:
    sections = state.get("sections") or []
    if int(state.get("current_index", 0)) < len(sections):
        return "write_section"
    return "finalize"


def build_plan_graph():
    builder = StateGraph(PlanState)

    builder.add_node("analyze", analyze_inputs)
    builder.add_node("gather_context", gather_context)
    builder.add_node("write_section", write_section)
    builder.add_node("finalize", finalize_plan)

    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", "gather_context")
    builder.add_edge("gather_context", "write_section")
    builder.add_conditional_edges(
        "write_section",
        _route_after_write,
        {"write_section": "write_section", "finalize": "finalize"},
    )
    builder.add_edge("finalize", END)

    return builder.compile()


def get_plan_graph():
    global _graph
    if _graph is None:
        _graph = build_plan_graph()
    return _graph


async def run_plan_graph(
    business_name: str,
    industry: str = "",
    notes: str = "",
    inputs: Optional[Dict[str, Any]] = None,
    document_ids: Optional[List[str]] = None,
    sections: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    emit=None,
) -> Dict[str, Any]:
    """Execute the plan workflow and return the final state."""
    state = new_plan_state(
        business_name=business_name,
        industry=industry,
        notes=notes,
        inputs=inputs or {},
        document_ids=document_ids or [],
        sections=sections or [],
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    graph = get_plan_graph()
    config: Dict[str, Any] = {
        "configurable": {"emit": emit} if emit else {},
        "recursion_limit": 60,
    }
    return await graph.ainvoke(state, config=config)
