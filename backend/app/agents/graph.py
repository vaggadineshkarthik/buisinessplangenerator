"""LangGraph workflow assembly for agentic RAG.

Workflow:
    Question -> Analyze -> Retrieve -> Evaluate -> Relevant?
        YES -> Rerank -> Build context -> OpenRouter generate -> Verify
                 -> (retry up to MAX_RETRIES / finalize) -> Answer
        NO  -> Explain that sufficient information was not found.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from langgraph.graph import END, START, StateGraph

from .nodes import (
    analyze_question,
    build_context_node,
    evaluate_node,
    finalize_response,
    generate_answer,
    insufficient_node,
    rerank_node,
    retrieve_documents,
    verify_node,
)
from .state import RAGState, new_state

EmitFn = Callable[..., Awaitable[None]]


def _route_after_evaluate(state: RAGState) -> str:
    return "rerank" if state.get("route") == "rerank" else "insufficient"


def _route_after_generate(state: RAGState) -> str:
    return "finalize" if state.get("status") == "error" else "verify"


def _route_after_verify(state: RAGState) -> str:
    return "retry" if state.get("route") == "retry" else "finalize"


def build_graph():
    builder = StateGraph(RAGState)

    builder.add_node("analyze", analyze_question)
    builder.add_node("retrieve", retrieve_documents)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("rerank", rerank_node)
    builder.add_node("build_context", build_context_node)
    builder.add_node("generate", generate_answer)
    builder.add_node("verify", verify_node)
    builder.add_node("insufficient", insufficient_node)
    builder.add_node("finalize", finalize_response)

    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", "retrieve")
    builder.add_edge("retrieve", "evaluate")
    builder.add_conditional_edges(
        "evaluate",
        _route_after_evaluate,
        {"rerank": "rerank", "insufficient": "insufficient"},
    )
    builder.add_edge("rerank", "build_context")
    builder.add_edge("build_context", "generate")
    builder.add_conditional_edges(
        "generate",
        _route_after_generate,
        {"verify": "verify", "finalize": "finalize"},
    )
    builder.add_conditional_edges(
        "verify",
        _route_after_verify,
        {"retry": "generate", "finalize": "finalize"},
    )
    builder.add_edge("insufficient", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_rag_graph(
    question: str,
    conversation_history: Optional[list] = None,
    document_ids: Optional[list] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    emit: Optional[EmitFn] = None,
) -> Dict[str, Any]:
    """Execute the workflow and return the final state."""
    state = new_state(
        question=question,
        conversation_history=conversation_history or [],
        document_ids=document_ids or [],
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    graph = get_graph()
    config: Dict[str, Any] = {
        "configurable": {"emit": emit} if emit else {},
        "recursion_limit": 25,
    }
    result = await graph.ainvoke(state, config=config)
    return result
