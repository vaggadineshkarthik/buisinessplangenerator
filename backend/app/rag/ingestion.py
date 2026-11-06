"""Document ingestion pipeline.

Flow: Validate -> Extract -> Clean -> Chunk -> Embed -> Store vectors -> Save metadata.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .. import database as db
from ..config import settings
from .chunking import Chunk, chunk_document
from .embeddings import embedding_service
from .extraction import ExtractionError, extract_document
from .vector_store import vector_store

ProgressCallback = Callable[[str, Dict[str, Any]], None]


def compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sanitize_filename(filename: str) -> str:
    """Strip directories and unsafe characters from an uploaded filename."""
    name = Path(filename or "document").name
    name = name.replace("\\", "/").split("/")[-1]
    cleaned = "".join(c for c in name if c.isalnum() or c in "._- ")
    cleaned = cleaned.strip().strip(".")
    return cleaned or "document"


def validate_upload(filename: str, content: bytes) -> str:
    """Validate an upload and return its normalised extension."""
    ext = Path(filename).suffix.lower()
    allowed = [e.lower() for e in settings.allowed_extensions]
    if ext not in allowed:
        raise ValueError(
            f"Unsupported file type '{ext or 'unknown'}'. Allowed: {', '.join(allowed)}."
        )
    if not content:
        raise ValueError("Uploaded file is empty.")
    if len(content) > settings.max_file_size_bytes:
        raise ValueError(
            f"File exceeds the {settings.max_file_size_mb} MB size limit."
        )
    return ext.lstrip(".")


def find_duplicate(content: bytes, exclude_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return an existing document with identical content, if any."""
    digest = compute_file_hash(content)
    for doc in db.list_documents():
        if exclude_id and doc["id"] == exclude_id:
            continue
        path = Path(doc["file_path"])
        if not path.exists():
            continue
        try:
            if compute_file_hash(path.read_bytes()) == digest:
                return doc
        except OSError:
            continue
    return None


def save_upload(filename: str, content: bytes) -> Path:
    safe_name = sanitize_filename(filename)
    ext = Path(safe_name).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    target = settings.documents_dir / stored_name
    target.write_bytes(content)
    return target


def _emit(on_progress: Optional[ProgressCallback], stage: str, **detail: Any) -> None:
    if on_progress:
        try:
            on_progress(stage, detail)
        except Exception:  # noqa: BLE001
            pass


async def ingest_document(
    document_id: str,
    name: str,
    file_path: Path,
    file_type: str,
    on_progress: Optional[ProgressCallback] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the full ingestion pipeline for a single document."""
    try:
        db.update_document(document_id, status="processing", error=None)
        _emit(on_progress, "processing", document_id=document_id)

        # 1. Extract + clean
        _emit(on_progress, "extracting")
        extracted = extract_document(file_path, file_type)

        # 2. Chunk
        _emit(on_progress, "chunking")
        chunks: List[Chunk] = chunk_document(extracted, chunk_size, chunk_overlap)
        if not chunks:
            raise ExtractionError("Document produced no usable chunks.")

        # 3. Embed
        _emit(on_progress, "embedding", chunks=len(chunks))
        await embedding_service.aensure_loaded()
        texts = [c.content for c in chunks]
        vectors: List[List[float]] = []
        batch = max(1, settings.embedding_batch_size)
        for i in range(0, len(texts), batch):
            vectors.extend(await embedding_service.aembed_documents(texts[i : i + batch]))
        embedding_service.validate_dimensions(vectors)

        # 4. Reset any previous vectors/rows for a clean reprocess
        vector_store.delete_document(document_id)
        db.delete_chunks_for_document(document_id)

        # 5. Persist vectors
        _emit(on_progress, "storing", chunks=len(chunks))
        ids = [f"{document_id}:{c.chunk_index}" for c in chunks]
        metadatas = [
            {
                "document_id": document_id,
                "document_name": name,
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "source": file_path.name,
                "upload_date": db.utcnow(),
            }
            for c in chunks
        ]
        vector_store.add_documents(
            ids=ids,
            embeddings=vectors,
            documents=texts,
            metadatas=metadatas,
        )

        # 6. Persist chunk metadata
        flat = extracted.full_text
        db.insert_chunks(
            [
                {
                    "id": ids[c.chunk_index],
                    "document_id": document_id,
                    "chunk_index": c.chunk_index,
                    "page_number": c.page_number,
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                    "content": c.content,
                    "token_estimate": c.token_estimate,
                }
                for c in chunks
            ]
        )

        db.update_document(
            document_id,
            status="ready",
            error=None,
            num_chunks=len(chunks),
            num_pages=extracted.num_pages,
            char_count=extracted.char_count,
            preview=flat[:400],
        )
        _emit(on_progress, "ready", chunks=len(chunks))
        return {
            "document_id": document_id,
            "status": "ready",
            "num_chunks": len(chunks),
            "num_pages": extracted.num_pages,
            "char_count": extracted.char_count,
            "warnings": extracted.warnings,
        }

    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        db.update_document(document_id, status="error", error=message)
        _emit(on_progress, "error", message=message)
        raise


async def reprocess_document(
    document_id: str, on_progress: Optional[ProgressCallback] = None
) -> Dict[str, Any]:
    doc = db.get_document(document_id)
    if not doc:
        raise ValueError("Document not found.")
    path = Path(doc["file_path"])
    if not path.exists():
        db.update_document(document_id, status="error", error="Source file is missing on disk.")
        raise ValueError("Source file is missing on disk.")

    return await ingest_document(
        document_id=document_id,
        name=doc["name"],
        file_path=path,
        file_type=doc["file_type"],
        on_progress=on_progress,
    )


def delete_document_fully(document_id: str) -> Dict[str, Any]:
    """Delete a document, its chunk metadata, its vectors and its source file."""
    doc = db.get_document(document_id)
    if not doc:
        raise ValueError("Document not found.")

    vectors_removed = 0
    try:
        vectors_removed = vector_store.delete_document(document_id)
    except Exception:  # noqa: BLE001
        vectors_removed = 0

    db.delete_chunks_for_document(document_id)
    path = Path(doc["file_path"])
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    db.delete_document(document_id)
    return {"document_id": document_id, "vectors_removed": vectors_removed}
