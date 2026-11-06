"""Business-plan orchestration: persistence, graph execution, SSE and export."""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from .. import database as db
from ..agents.plan_graph import run_plan_graph
from ..agents.plan_prompts import SECTION_CATALOG, resolve_sections
from ..services.chat_service import require_openrouter
from ..services.openrouter import OpenRouterError


def _new_id() -> str:
    return uuid.uuid4().hex


def section_catalog() -> List[Dict[str, Any]]:
    return [
        {
            "key": s["key"],
            "title": s["title"],
            "guidance": s["guidance"],
            "target_words": s["target_words"],
            "default": s["default"],
        }
        for s in SECTION_CATALOG
    ]


def create_plan(
    business_name: str,
    industry: Optional[str] = None,
    notes: Optional[str] = None,
    inputs: Optional[Dict[str, Any]] = None,
    document_ids: Optional[List[str]] = None,
    section_keys: Optional[List[str]] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert a plan record and its section skeleton, return the stored plan."""
    business_name = (business_name or "").strip() or "Untitled Business"
    inputs = dict(inputs or {})
    if notes:
        inputs.setdefault("notes", notes.strip())

    sections = resolve_sections(section_keys)
    plan_id = _new_id()
    now = db.utcnow()
    title = f"{business_name} — Business Plan"

    db.insert_plan(
        {
            "id": plan_id,
            "title": title,
            "business_name": business_name,
            "industry": (industry or "").strip() or None,
            "status": "generating",
            "inputs": json.dumps(inputs),
            "document_ids": json.dumps(document_ids or []),
            "model": model,
            "overview": "",
            "section_count": len(sections),
            "word_count": 0,
            "created_at": now,
            "updated_at": now,
        }
    )

    for position, section in enumerate(sections):
        db.insert_plan_section(
            {
                "id": _new_id(),
                "plan_id": plan_id,
                "key": section["key"],
                "title": section["title"],
                "position": position,
                "content": "",
                "citations": "[]",
                "word_count": 0,
                "status": "pending",
            }
        )

    return get_plan_payload(plan_id)  # type: ignore[return-value]


def get_plan_payload(plan_id: str) -> Optional[Dict[str, Any]]:
    plan = db.get_plan(plan_id)
    if not plan:
        return None
    sections = db.get_plan_sections(plan_id)
    return build_plan_payload(plan, sections)


def build_plan_payload(plan: Dict[str, Any], sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "id": plan["id"],
        "title": plan["title"],
        "business_name": plan["business_name"],
        "industry": plan.get("industry"),
        "status": plan["status"],
        "error": plan.get("error"),
        "inputs": plan.get("inputs", {}),
        "document_ids": plan.get("document_ids", []),
        "model": plan.get("model"),
        "overview": plan.get("overview", ""),
        "section_count": plan.get("section_count", len(sections)),
        "word_count": plan.get("word_count", 0),
        "created_at": plan["created_at"],
        "updated_at": plan["updated_at"],
        "sections": [
            {
                "id": s["id"],
                "key": s["key"],
                "title": s["title"],
                "position": s["position"],
                "content": s.get("content", ""),
                "citations": s.get("citations", []),
                "word_count": s.get("word_count", 0),
                "status": s.get("status", "pending"),
            }
            for s in sections
        ],
    }


def list_plans() -> List[Dict[str, Any]]:
    out = []
    for plan in db.list_plans():
        out.append(
            {
                "id": plan["id"],
                "title": plan["title"],
                "business_name": plan["business_name"],
                "industry": plan.get("industry"),
                "status": plan["status"],
                "overview": plan.get("overview", ""),
                "section_count": plan.get("section_count", 0),
                "word_count": plan.get("word_count", 0),
                "created_at": plan["created_at"],
                "updated_at": plan["updated_at"],
            }
        )
    return out


def delete_plan(plan_id: str) -> bool:
    if not db.get_plan(plan_id):
        raise ValueError("Plan not found.")
    return db.delete_plan(plan_id)


def _persist_section(plan_id: str, record: Dict[str, Any]) -> None:
    rows = db.get_plan_sections(plan_id)
    target = next((r for r in rows if r["key"] == record.get("key")), None)
    if not target:
        return
    db.update_plan_section(
        target["id"],
        content=record.get("content", ""),
        citations=json.dumps(record.get("citations", [])),
        word_count=int(record.get("word_count", 0)),
        status=record.get("status", "ready"),
    )


def _finalize_plan_record(plan_id: str, state: Dict[str, Any]) -> None:
    sections = db.get_plan_sections(plan_id)
    total_words = sum(int(s.get("word_count", 0)) for s in sections)
    errors = state.get("errors") or []
    status = "ready" if any(s.get("content") for s in sections) else "error"
    db.update_plan(
        plan_id,
        status=status,
        overview=state.get("overview", ""),
        word_count=total_words,
        error="; ".join(errors) if errors and status == "error" else None,
    )


async def generate_plan(
    plan_id: str,
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the plan graph to completion (non-streaming) and persist the result."""
    require_openrouter()
    plan = db.get_plan(plan_id)
    if not plan:
        raise ValueError("Plan not found.")

    state = await run_plan_graph(
        business_name=plan["business_name"],
        industry=plan.get("industry") or "",
        notes=(plan.get("inputs") or {}).get("notes", ""),
        inputs=plan.get("inputs") or {},
        document_ids=plan.get("document_ids") or [],
        sections=resolve_sections([s["key"] for s in db.get_plan_sections(plan_id)]),
        model=model or plan.get("model"),
        temperature=temperature,
        max_tokens=max_tokens,
        emit=None,
    )

    for record in state.get("written", []):
        _persist_section(plan_id, record)
    _finalize_plan_record(plan_id, state)
    return get_plan_payload(plan_id)  # type: ignore[return-value]


async def stream_plan(
    plan_id: str,
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Stream plan generation as workflow events, tokens and the final payload."""
    try:
        require_openrouter()
    except OpenRouterError as exc:
        if db.get_plan(plan_id):
            db.update_plan(plan_id, status="error", error=exc.message)
        yield {"event": "error", "data": {"message": exc.message, "code": exc.code}}
        return

    plan = db.get_plan(plan_id)
    if not plan:
        yield {"event": "error", "data": {"message": "Plan not found.", "code": "not_found"}}
        return

    sections = db.get_plan_sections(plan_id)
    yield {
        "event": "plan",
        "data": {
            "plan_id": plan["id"],
            "title": plan["title"],
            "business_name": plan["business_name"],
            "total": len(sections),
            "sections": [
                {"key": s["key"], "title": s["title"], "position": s["position"]}
                for s in sections
            ],
        },
    }

    queue: asyncio.Queue = asyncio.Queue()
    SENTINEL = object()

    async def emit(event: str, **data: Any) -> None:
        await queue.put({"event": event, "data": data})

    async def runner() -> None:
        try:
            state = await run_plan_graph(
                business_name=plan["business_name"],
                industry=plan.get("industry") or "",
                notes=(plan.get("inputs") or {}).get("notes", ""),
                inputs=plan.get("inputs") or {},
                document_ids=plan.get("document_ids") or [],
                sections=resolve_sections([s["key"] for s in sections]),
                model=model or plan.get("model"),
                temperature=temperature,
                max_tokens=max_tokens,
                emit=emit,
            )
            await queue.put({"event": "_final", "data": state})
        except Exception as exc:  # noqa: BLE001
            await queue.put({"event": "_error", "data": {"message": str(exc)}})
        finally:
            await queue.put(SENTINEL)

    task = asyncio.create_task(runner())
    final_state: Optional[Dict[str, Any]] = None
    try:
        while True:
            item = await queue.get()
            if item is SENTINEL:
                break
            event = item["event"]
            if event == "_final":
                final_state = item["data"]
                continue
            if event == "_error":
                yield {"event": "error", "data": item["data"]}
                continue
            if event == "section":
                _persist_section(plan_id, item["data"])
            yield item
    except asyncio.CancelledError:
        task.cancel()
        db.update_plan(plan_id, status="error", error="Generation cancelled.")
        raise
    finally:
        if not task.done():
            task.cancel()

    if final_state is not None:
        _finalize_plan_record(plan_id, final_state)
    payload = get_plan_payload(plan_id)
    yield {"event": "result", "data": payload or {}}


def export_plan_markdown(plan_id: str) -> str:
    payload = get_plan_payload(plan_id)
    if not payload:
        raise ValueError("Plan not found.")

    lines: List[str] = [f"# {payload['title']}", ""]
    lines.append(f"**Business:** {payload['business_name']}")
    if payload.get("industry"):
        lines.append(f"**Industry:** {payload['industry']}")
    lines.append(f"**Generated:** {payload['created_at']}")
    lines.append("")

    sources: Dict[str, Dict[str, Any]] = {}
    for section in payload["sections"]:
        if not section.get("content"):
            continue
        lines.append(f"## {section['title']}")
        lines.append("")
        lines.append(section["content"].strip())
        lines.append("")
        for citation in section.get("citations", []):
            key = citation.get("label") or citation.get("document_name", "")
            if key:
                sources[key] = citation

    if sources:
        lines.append("## Sources")
        lines.append("")
        for citation in sources.values():
            label = citation.get("label") or citation.get("document_name", "document")
            page = citation.get("page_number")
            lines.append(f"- {label}, Page {page}" if page else f"- {label}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Generated by RAGify AI. Figures marked as assumptions are illustrative and "
        "must be validated before use."
    )
    return "\n".join(lines)


def export_plan_text(plan_id: str) -> str:
    payload = get_plan_payload(plan_id)
    if not payload:
        raise ValueError("Plan not found.")
    lines = [payload["title"], "=" * len(payload["title"]), ""]
    for section in payload["sections"]:
        if not section.get("content"):
            continue
        lines.append(section["title"].upper())
        lines.append("-" * len(section["title"]))
        lines.append(section["content"].strip())
        lines.append("")
    return "\n".join(lines)
