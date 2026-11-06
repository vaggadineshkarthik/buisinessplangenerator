"""Business plan generation, listing, retrieval, export and deletion endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from ..services.openrouter import OpenRouterError
from ..services.plan_service import (
    create_plan,
    delete_plan,
    export_plan_markdown,
    export_plan_text,
    generate_plan,
    get_plan_payload,
    list_plans,
    section_catalog,
    stream_plan,
)
from .chat import _sse_stream

router = APIRouter(prefix="/api/plans", tags=["plans"])


class PlanGenerateRequest(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=200)
    industry: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=4000)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    document_ids: Optional[List[str]] = None
    sections: Optional[List[str]] = None
    model: Optional[str] = Field(default=None, max_length=200)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=16, le=8000)


@router.get("/catalog")
async def plan_catalog() -> Dict[str, Any]:
    return {"sections": section_catalog()}


@router.post("/generate", status_code=status.HTTP_201_CREATED)
async def generate(request: PlanGenerateRequest) -> Dict[str, Any]:
    try:
        plan = create_plan(
            business_name=request.business_name,
            industry=request.industry,
            notes=request.notes,
            inputs=request.inputs,
            document_ids=request.document_ids,
            section_keys=request.sections,
            model=request.model,
        )
        return await generate_plan(
            plan["id"],
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except OpenRouterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/generate/stream")
async def generate_stream(request: PlanGenerateRequest, http_request: Request) -> StreamingResponse:
    try:
        plan = create_plan(
            business_name=request.business_name,
            industry=request.industry,
            notes=request.notes,
            inputs=request.inputs,
            document_ids=request.document_ids,
            section_keys=request.sections,
            model=request.model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    generator = stream_plan(
        plan["id"],
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    return StreamingResponse(
        _sse_stream(http_request, generator),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{plan_id}/regenerate", status_code=status.HTTP_201_CREATED)
async def regenerate_plan(plan_id: str, http_request: Request) -> StreamingResponse:
    if not get_plan_payload(plan_id):
        raise HTTPException(status_code=404, detail="Plan not found.")
    # Reset sections before regenerating.
    from .. import database as db

    for section in db.get_plan_sections(plan_id):
        db.update_plan_section(
            section["id"], content="", citations="[]", word_count=0, status="pending"
        )
    db.update_plan(plan_id, status="generating", error=None, overview="", word_count=0)

    generator = stream_plan(plan_id)
    return StreamingResponse(
        _sse_stream(http_request, generator),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("")
async def get_plans() -> List[Dict[str, Any]]:
    return list_plans()


@router.get("/{plan_id}")
async def get_plan(plan_id: str) -> Dict[str, Any]:
    payload = get_plan_payload(plan_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return payload


@router.delete("/{plan_id}")
async def remove_plan(plan_id: str) -> Dict[str, Any]:
    try:
        delete_plan(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "plan_id": plan_id}


@router.get("/{plan_id}/export")
async def export_plan(
    plan_id: str,
    format: str = Query("markdown", pattern="^(markdown|text)$"),
) -> Response:
    try:
        if format == "text":
            content = export_plan_text(plan_id)
            return PlainTextResponse(
                content,
                headers={"Content-Disposition": f'attachment; filename="plan-{plan_id}.txt"'},
            )
        content = export_plan_markdown(plan_id)
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="plan-{plan_id}.md"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
