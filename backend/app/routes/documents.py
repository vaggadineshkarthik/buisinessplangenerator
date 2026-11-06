"""Document upload, listing, preview, reprocessing and deletion endpoints."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from .. import database as db
from ..config import settings
from ..rag.ingestion import (
    delete_document_fully,
    find_duplicate,
    ingest_document,
    reprocess_document,
    save_upload,
    validate_upload,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentOut(BaseModel):
    id: str
    name: str
    filename: str
    file_type: str
    file_size: int
    status: str
    error: Optional[str] = None
    num_chunks: int
    num_pages: int
    char_count: int
    created_at: str
    updated_at: str


class UploadResult(BaseModel):
    accepted: List[DocumentOut] = Field(default_factory=list)
    rejected: List[Dict[str, str]] = Field(default_factory=list)


def _serialize(doc: Dict[str, Any]) -> DocumentOut:
    return DocumentOut(
        id=doc["id"],
        name=doc["name"],
        filename=doc["filename"],
        file_type=doc["file_type"],
        file_size=doc["file_size"],
        status=doc["status"],
        error=doc.get("error"),
        num_chunks=doc["num_chunks"],
        num_pages=doc["num_pages"],
        char_count=doc["char_count"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.post("/upload", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_documents(
    background: BackgroundTasks,
    files: List[UploadFile] = File(..., description="PDF, DOCX, TXT or CSV files"),
    process_inline: bool = Query(False, description="Wait for full ingestion before responding"),
) -> UploadResult:
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")

    accepted: List[DocumentOut] = []
    rejected: List[Dict[str, str]] = []

    for upload in files:
        original_name = upload.filename or "document"
        try:
            content = await upload.read()
            file_type = validate_upload(original_name, content)
        except ValueError as exc:
            rejected.append({"filename": original_name, "reason": str(exc)})
            continue

        duplicate = find_duplicate(content)
        if duplicate:
            rejected.append(
                {
                    "filename": original_name,
                    "reason": f"Duplicate of already uploaded document '{duplicate['name']}'.",
                }
            )
            continue

        try:
            stored_path = save_upload(original_name, content)
        except OSError as exc:
            rejected.append({"filename": original_name, "reason": f"Could not store file: {exc}"})
            continue

        doc_id = uuid.uuid4().hex
        now = db.utcnow()
        safe_name = stored_path.stem + stored_path.suffix
        db.insert_document(
            {
                "id": doc_id,
                "name": original_name,
                "filename": safe_name,
                "file_type": file_type,
                "file_path": str(stored_path),
                "file_size": len(content),
                "status": "processing",
                "created_at": now,
                "updated_at": now,
            }
        )

        if process_inline:
            try:
                await ingest_document(doc_id, original_name, stored_path, file_type)
            except Exception as exc:  # noqa: BLE001
                rejected.append({"filename": original_name, "reason": str(exc)})
                continue
        else:
            background.add_task(ingest_document, doc_id, original_name, stored_path, file_type)

        doc = db.get_document(doc_id)
        if doc:
            accepted.append(_serialize(doc))

    if not accepted and rejected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "No documents could be accepted.", "rejected": rejected},
        )
    return UploadResult(accepted=accepted, rejected=rejected)


@router.get("", response_model=List[DocumentOut])
async def list_documents() -> List[DocumentOut]:
    return [_serialize(d) for d in db.list_documents()]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: str) -> DocumentOut:
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return _serialize(doc)


@router.get("/{document_id}/chunks")
async def get_document_chunks(document_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    chunks = db.get_chunks_for_document(document_id)
    sliced = chunks[offset : offset + limit]
    return {
        "document_id": document_id,
        "total_chunks": len(chunks),
        "offset": offset,
        "limit": limit,
        "chunks": [
            {
                "id": c["id"],
                "chunk_index": c["chunk_index"],
                "page_number": c["page_number"],
                "content": c["content"],
                "token_estimate": c["token_estimate"],
            }
            for c in sliced
        ],
    }


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(document_id: str) -> Dict[str, Any]:
    try:
        result = delete_document_fully(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, **result}


@router.post("/{document_id}/reprocess", response_model=DocumentOut)
async def reprocess(document_id: str, background: BackgroundTasks) -> DocumentOut:
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    db.update_document(document_id, status="processing", error=None)
    background.add_task(reprocess_document, document_id)
    refreshed = db.get_document(document_id)
    return _serialize(refreshed or doc)
