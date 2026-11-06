"""LangGraph node implementations for the agentic RAG workflow."""
from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional

from langchain_core.runnables import RunnableConfig

from ..config import settings
from ..rag.evaluation import (
    build_context as build_context_text,
    evaluate_relevance,
    generate_citations,
    verify_answer,
)
from ..rag.retrieval import RetrievedChunk, rerank, retrieve, tokenize
from ..services.openrouter import OpenRouterError, openrouter_client
from .prompts import (
    ANALYZE_PROMPT,
    ANSWER_PROMPT,
    CITATION_FORMAT,
    INSUFFICIENT_ANSWER,
    RETRY_PROMPT,
    SYSTEM_PROMPT,
    format_history,
)
from .state import RAGState

EmitFn = Callable[..., Awaitable[None]]


async def _emit(config: RunnableConfig, event: str, **data: Any) -> None:
    emit: Optional[EmitFn] = (config.get("configurable") or {}).get("emit")
    if emit is None:
        return
    try:
        await emit(event, **data)
    except Exception:  # noqa: BLE001
        pass


def _chunk_to_dataclass(chunk: Dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.get("chunk_id", ""),
        document_id=chunk.get("document_id", ""),
        document_name=chunk.get("document_name", "unknown"),
        page_number=int(chunk.get("page_number", 0) or 0),
        content=chunk.get("content", ""),
        score=float(chunk.get("score", 0.0)),
        char_start=int(chunk.get("char_start", 0) or 0),
        char_end=int(chunk.get("char_end", 0) or 0),
        chunk_index=int(chunk.get("chunk_index", 0) or 0),
        source=chunk.get("source", ""),
        rerank_score=float(chunk.get("rerank_score", 0.0) or 0.0),
    )


def _parse_json_object(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _heuristic_analysis(question: str) -> Dict[str, Any]:
    keywords = tokenize(question)[:12]
    lowered = question.lower()
    if lowered.startswith(("summar", "overview", "tl;dr")):
        qtype = "summary"
    elif "compare" in lowered or "difference" in lowered or " vs " in lowered:
        qtype = "comparison"
    elif lowered.startswith("list") or "what are" in lowered:
        qtype = "list"
    elif lowered.startswith(("what is", "define", "definition")):
        qtype = "definition"
    else:
        qtype = "factual"
    return {"rewritten_query": question.strip(), "keywords": keywords, "question_type": qtype}


# --------------------------------------------------------------------------
# 1. Analyze
# --------------------------------------------------------------------------
async def analyze_question(state: RAGState, config: RunnableConfig) -> Dict[str, Any]:
    await _emit(config, "stage", name="analyzing", status="started")
    question = state.get("question", "").strip()
    history_text = format_history(state.get("conversation_history", []))

    analysis = _heuristic_analysis(question)
    if openrouter_client.configured:
        try:
            prompt = ANALYZE_PROMPT.format(question=question, history=history_text)
            result = await openrouter_client.chat_completion(
                messages=[
                    {"role": "system", "content": "You output strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=300,
                max_retries=2,
            )
            parsed = _parse_json_object(result.get("content", ""))
            if parsed.get("rewritten_query"):
                analysis.update(
                    {
                        "rewritten_query": str(parsed["rewritten_query"]),
                        "keywords": [str(k) for k in parsed.get("keywords", [])][:12]
                        or analysis["keywords"],
                        "question_type": str(parsed.get("question_type", analysis["question_type"])),
                    }
                )
        except OpenRouterError:
            analysis["analysis_degraded"] = True

    search_query = analysis.get("rewritten_query") or question
    if analysis.get("keywords"):
        search_query = f"{search_query} {' '.join(analysis['keywords'][:6])}".strip()

    await _emit(
        config,
        "stage",
        name="analyzing",
        status="completed",
        detail={"query": search_query, "question_type": analysis.get("question_type")},
    )
    return {"analysis": analysis, "route": "retrieve", "status": "analyzed"}


# --------------------------------------------------------------------------
# 2. Retrieve
# --------------------------------------------------------------------------
async def retrieve_documents(state: RAGState, config: RunnableConfig) -> Dict[str, Any]:
    await _emit(config, "stage", name="embedding", status="started")
    query = (state.get("analysis") or {}).get("rewritten_query") or state.get("question", "")
    await _emit(config, "stage", name="embedding", status="completed")
    await _emit(config, "stage", name="searching", status="started")

    result = await retrieve(
        question=query,
        document_ids=state.get("document_ids") or None,
        top_k=settings.top_k,
        threshold=settings.similarity_threshold,
    )

    await _emit(
        config,
        "stage",
        name="searching",
        status="completed",
        detail={"candidates": result.candidates, "returned": len(result.chunks)},
    )
    return {
        "retrieved_chunks": [c.to_dict() for c in result.chunks],
        "retrieval_stats": result.to_dict(),
        "status": "retrieved",
    }


# --------------------------------------------------------------------------
# 3. Evaluate relevance
# --------------------------------------------------------------------------
async def evaluate_node(state: RAGState, config: RunnableConfig) -> Dict[str, Any]:
    await _emit(config, "stage", name="evaluating", status="started")
    chunks = [_chunk_to_dataclass(c) for c in state.get("retrieved_chunks", [])]
    evaluation = evaluate_relevance(chunks, threshold=settings.similarity_threshold)
    await _emit(
        config,
        "stage",
        name="evaluating",
        status="completed",
        detail=evaluation.to_dict(),
    )
    return {
        "relevance": evaluation.to_dict(),
        "route": "rerank" if evaluation.relevant else "insufficient",
        "status": "evaluated",
    }


# --------------------------------------------------------------------------
# 4. Rerank
# --------------------------------------------------------------------------
async def rerank_node(state: RAGState, config: RunnableConfig) -> Dict[str, Any]:
    await _emit(config, "stage", name="reranking", status="started")
    question = state.get("question", "")
    chunks = [_chunk_to_dataclass(c) for c in state.get("retrieved_chunks", [])]
    ranked = rerank(chunks, question, top_n=settings.top_k)
    await _emit(
        config,
        "stage",
        name="reranking",
        status="completed",
        detail={"kept": len(ranked)},
    )
    return {"retrieved_chunks": [c.to_dict() for c in ranked], "status": "reranked"}


# --------------------------------------------------------------------------
# 5. Build context
# --------------------------------------------------------------------------
async def build_context_node(state: RAGState, config: RunnableConfig) -> Dict[str, Any]:
    chunks = [_chunk_to_dataclass(c) for c in state.get("retrieved_chunks", [])]
    context = build_context_text(chunks)
    citations = generate_citations(chunks)
    await _emit(config, "stage", name="context", status="completed", detail={"chunks": len(chunks)})
    return {"context": context, "citations": citations, "status": "context_ready"}


# --------------------------------------------------------------------------
# 6. Generate answer (streams tokens)
# --------------------------------------------------------------------------
async def generate_answer(state: RAGState, config: RunnableConfig) -> Dict[str, Any]:
    await _emit(config, "stage", name="generating", status="started")
    question = state.get("question", "")
    context = state.get("context", "")
    history_text = format_history(state.get("conversation_history", []))
    retry_count = int(state.get("retry_count", 0))

    if retry_count > 0:
        verification = state.get("verification") or {}
        unsupported = verification.get("unsupported_claims", [])
        unsupported_text = "\n".join(f"- {c}" for c in unsupported) or "- (previous answer was unsupported)"
        user_prompt = RETRY_PROMPT.format(
            unsupported=unsupported_text,
            citation_format=CITATION_FORMAT,
            context=context,
            question=question,
        )
    else:
        user_prompt = ANSWER_PROMPT.format(
            citation_format=CITATION_FORMAT,
            context=context,
            history=history_text,
            question=question,
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    answer_parts: List[str] = []
    try:
        async for token in openrouter_client.stream_chat(
            messages=messages,
            model=state.get("model") or None,
            temperature=state.get("temperature"),
            max_tokens=state.get("max_tokens"),
        ):
            answer_parts.append(token)
            await _emit(config, "token", text=token)
    except OpenRouterError as exc:
        await _emit(config, "error", message=exc.message, code=exc.code)
        errors = list(state.get("errors", []))
        errors.append(exc.message)
        return {"status": "error", "errors": errors, "answer": "".join(answer_parts)}

    answer = "".join(answer_parts).strip()
    await _emit(config, "stage", name="generating", status="completed", detail={"chars": len(answer)})
    return {"answer": answer, "status": "generated"}


# --------------------------------------------------------------------------
# 7. Verify answer
# --------------------------------------------------------------------------
async def verify_node(state: RAGState, config: RunnableConfig) -> Dict[str, Any]:
    await _emit(config, "stage", name="verifying", status="started")
    chunks = [_chunk_to_dataclass(c) for c in state.get("retrieved_chunks", [])]
    result = verify_answer(state.get("answer", ""), chunks)
    verification = result.to_dict()

    retry_count = int(state.get("retry_count", 0))
    needs_retry = (
        verification["verdict"] in ("unverified", "partially_verified")
        and retry_count < settings.max_retries
        and verification["coverage"] < 0.6
    )
    await _emit(config, "stage", name="verifying", status="completed", detail=verification)
    return {
        "verification": verification,
        "needs_retry": needs_retry,
        "retry_count": retry_count + 1 if needs_retry else retry_count,
        "route": "retry" if needs_retry else "finalize",
        "status": "verified",
    }


# --------------------------------------------------------------------------
# 8. Insufficient context branch
# --------------------------------------------------------------------------
async def insufficient_node(state: RAGState, config: RunnableConfig) -> Dict[str, Any]:
    await _emit(
        config,
        "stage",
        name="insufficient",
        status="completed",
        detail={"reason": (state.get("relevance") or {}).get("reason", "")},
    )
    return {
        "answer": INSUFFICIENT_ANSWER,
        "citations": [],
        "verification": {
            "verdict": "no_sources",
            "coverage": 0.0,
            "claims": [],
            "unsupported_claims": [],
            "disclaimer": "",
        },
        "status": "no_context",
    }


# --------------------------------------------------------------------------
# 9. Finalize
# --------------------------------------------------------------------------
async def finalize_response(state: RAGState, config: RunnableConfig) -> Dict[str, Any]:
    await _emit(config, "stage", name="citations", status="started")
    chunks = [_chunk_to_dataclass(c) for c in state.get("retrieved_chunks", [])]
    citations = state.get("citations") or generate_citations(chunks)
    await _emit(
        config,
        "stage",
        name="citations",
        status="completed",
        detail={"citations": len(citations)},
    )
    await _emit(config, "done", status="complete")
    final_status = state.get("status")
    if final_status in (None, "", "pending", "generated", "verified", "context_ready", "retrieved", "reranked", "analyzed", "evaluated"):
        final_status = "complete"
    return {"citations": citations, "status": final_status}
