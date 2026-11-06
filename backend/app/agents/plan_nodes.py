"""LangGraph node implementations for the business-plan workflow."""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Dict, List, Optional

from langchain_core.runnables import RunnableConfig

from ..config import settings
from ..rag.evaluation import build_context as build_context_text
from ..rag.evaluation import generate_citations
from ..rag.retrieval import RetrievedChunk, retrieve
from ..services.openrouter import OpenRouterError, openrouter_client
from .plan_prompts import (
    CITATION_FORMAT,
    PLAN_SYSTEM_PROMPT,
    SECTION_PROMPT,
    format_inputs,
    format_prior,
    resolve_sections,
)
from .plan_state import PlanState

EmitFn = Callable[..., Awaitable[None]]


async def _emit(config: RunnableConfig, event: str, **data: Any) -> None:
    emit: Optional[EmitFn] = (config.get("configurable") or {}).get("emit")
    if emit is None:
        return
    try:
        await emit(event, **data)
    except Exception:  # noqa: BLE001
        pass


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def _context_from(retrieved: List[RetrievedChunk], limit: int = 4) -> str:
    return build_context_text(retrieved[:limit])


# --------------------------------------------------------------------------
# 1. Analyse inputs
# --------------------------------------------------------------------------
async def analyze_inputs(state: PlanState, config: RunnableConfig) -> Dict[str, Any]:
    await _emit(config, "stage", name="analyzing", status="started")
    sections = state.get("sections") or resolve_sections(None)
    business = (state.get("business_name") or "").strip() or "Untitled Business"
    await _emit(
        config,
        "stage",
        name="analyzing",
        status="completed",
        detail={"business_name": business, "sections": len(sections)},
    )
    return {
        "business_name": business,
        "sections": sections,
        "current_index": 0,
        "written": [],
        "status": "analyzed",
    }


# --------------------------------------------------------------------------
# 2. Gather grounding context (optional)
# --------------------------------------------------------------------------
def _build_query(state: PlanState) -> str:
    inputs = state.get("inputs") or {}
    parts = [
        state.get("business_name", ""),
        state.get("industry", ""),
        str(inputs.get("product", "")),
        str(inputs.get("target_market", "")),
        str(inputs.get("problem", "")),
        state.get("notes", ""),
    ]
    query = " ".join(p for p in parts if p).strip()
    return query or state.get("business_name", "") or "business plan"


async def gather_context(state: PlanState, config: RunnableConfig) -> Dict[str, Any]:
    document_ids = [d for d in (state.get("document_ids") or []) if d]
    if not document_ids:
        return {"context": "", "citations": [], "retrieval_stats": {}, "status": "context_ready"}

    await _emit(config, "stage", name="embedding", status="started")
    query = _build_query(state)
    await _emit(config, "stage", name="embedding", status="completed")
    await _emit(config, "stage", name="searching", status="started")

    try:
        result = await retrieve(
            question=query,
            document_ids=document_ids,
            top_k=settings.top_k,
            threshold=settings.similarity_threshold,
        )
    except Exception as exc:  # noqa: BLE001
        await _emit(config, "stage", name="searching", status="completed",
                    detail={"error": str(exc), "returned": 0})
        errors = list(state.get("errors", []))
        errors.append(f"Retrieval skipped: {exc}")
        return {
            "context": "",
            "citations": [],
            "retrieval_stats": {"returned": 0, "error": str(exc)},
            "errors": errors,
            "status": "context_ready",
        }

    context = _context_from(result.chunks)
    citations = generate_citations(result.chunks)
    await _emit(
        config,
        "stage",
        name="searching",
        status="completed",
        detail={"candidates": result.candidates, "returned": len(result.chunks)},
    )
    return {
        "context": context,
        "citations": citations,
        "retrieval_stats": result.to_dict(),
        "status": "context_ready",
    }


# --------------------------------------------------------------------------
# 3. Write the current section (streams tokens)
# --------------------------------------------------------------------------
async def write_section(state: PlanState, config: RunnableConfig) -> Dict[str, Any]:
    sections = state.get("sections") or []
    index = int(state.get("current_index", 0))
    written: List[Dict[str, Any]] = list(state.get("written", []))

    if index >= len(sections):
        return {"status": "writing_done"}

    section = sections[index]
    key = section["key"]
    title = section["title"]

    await _emit(
        config,
        "stage",
        name="generating",
        status="started",
        detail={"section_key": key, "title": title, "position": index, "total": len(sections)},
    )

    prompt = SECTION_PROMPT.format(
        title=title,
        business_name=state.get("business_name", ""),
        industry=state.get("industry") or "(not specified)",
        inputs_block=format_inputs(state.get("inputs") or {}),
        notes=(state.get("notes") or "").strip() or "(none)",
        prior=format_prior(written),
        context=state.get("context") or "(no research documents selected)",
        guidance=section.get("guidance", ""),
        citation_format=CITATION_FORMAT,
        target_words=section.get("target_words", 220),
    )
    messages = [
        {"role": "system", "content": PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    parts: List[str] = []
    error_message: Optional[str] = None
    try:
        async for token in openrouter_client.stream_chat(
            messages=messages,
            model=state.get("model") or None,
            temperature=state.get("temperature"),
            max_tokens=state.get("max_tokens"),
        ):
            parts.append(token)
            await _emit(config, "token", text=token, section_key=key)
    except OpenRouterError as exc:
        error_message = exc.message
        await _emit(config, "error", message=exc.message, code=exc.code)

    content = "".join(parts).strip()
    record = {
        "key": key,
        "title": title,
        "position": index,
        "content": content,
        "word_count": _word_count(content),
        "citations": state.get("citations", []) if content else [],
        "status": "error" if error_message else "ready",
    }
    written.append(record)

    await _emit(
        config,
        "stage",
        name="generating",
        status="completed",
        detail={"section_key": key, "title": title, "words": record["word_count"]},
    )
    await _emit(config, "section", **record)

    errors = list(state.get("errors", []))
    if error_message:
        errors.append(error_message)

    return {
        "written": written,
        "current_index": index + 1,
        "errors": errors,
        "status": "error" if error_message and len(errors) >= len(sections) else "writing",
    }


# --------------------------------------------------------------------------
# 4. Finalise
# --------------------------------------------------------------------------
async def finalize_plan(state: PlanState, config: RunnableConfig) -> Dict[str, Any]:
    written = state.get("written", [])
    overview = ""
    for section in written:
        if section.get("key") == "executive_summary" and section.get("content"):
            overview = section["content"]
            break
    if not overview and written:
        overview = written[0].get("content", "")
    if len(overview) > 400:
        overview = overview[:400].rstrip() + "..."

    await _emit(config, "stage", name="citations", status="started")
    await _emit(
        config,
        "stage",
        name="citations",
        status="completed",
        detail={"citations": len(state.get("citations", []))},
    )
    await _emit(config, "done", status="complete")

    has_error = bool(state.get("errors")) and not any(s.get("content") for s in written)
    return {
        "overview": overview,
        "status": "error" if has_error else "ready",
    }
