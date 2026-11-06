"""Persistent vector store backed by ChromaDB.

Embeddings are always computed by our own :mod:`embeddings` service and passed
to Chroma explicitly, so the same model is used for indexing and querying.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import settings


class VectorStoreError(Exception):
    pass


@dataclass
class VectorRecord:
    id: str
    content: str
    metadata: Dict[str, Any]
    score: float = 0.0
    distance: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


class VectorStore:
    _instance: Optional["VectorStore"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._client = None
        self._collection = None
        self._lock = threading.Lock()

    @classmethod
    def instance(cls) -> "VectorStore":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # -- client / collection ----------------------------------------------
    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        with self._lock:
            if self._collection is not None:
                return self._collection
            try:
                import chromadb
                from chromadb.config import Settings as ChromaSettings
            except Exception as exc:  # noqa: BLE001
                raise VectorStoreError(
                    "chromadb is not installed. Run `pip install -r requirements.txt`."
                ) from exc

            settings.chroma_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(settings.chroma_dir),
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
            )
            self._collection = self._client.get_or_create_collection(
                name=settings.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )
            return self._collection

    @property
    def collection(self):
        return self._get_collection()

    def count(self) -> int:
        try:
            return int(self.collection.count())
        except Exception:  # noqa: BLE001
            return 0

    def health(self) -> Dict[str, Any]:
        try:
            return {"available": True, "count": self.count(), "path": str(settings.chroma_dir)}
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "error": str(exc)}

    # -- writes ------------------------------------------------------------
    def add_documents(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        if not ids:
            return
        if not (len(ids) == len(embeddings) == len(documents) == len(metadatas)):
            raise VectorStoreError("Mismatched lengths when adding documents to vector store.")
        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Failed to add embeddings to vector store: {exc}") from exc

    def delete_document(self, document_id: str) -> int:
        try:
            existing = self.collection.get(where={"document_id": document_id})
            n = len(existing.get("ids", []) or [])
            if n:
                self.collection.delete(where={"document_id": document_id})
            return n
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Failed to delete document embeddings: {exc}") from exc

    def delete_ids(self, ids: List[str]) -> None:
        if not ids:
            return
        try:
            self.collection.delete(ids=ids)
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Failed to delete embeddings: {exc}") from exc

    # -- reads -------------------------------------------------------------
    def query(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        document_ids: Optional[List[str]] = None,
    ) -> List[VectorRecord]:
        if not query_embedding:
            return []
        where: Optional[Dict[str, Any]] = None
        if document_ids:
            where = {"document_id": {"$in": list(document_ids)}} if len(document_ids) > 1 else {
                "document_id": document_ids[0]
            }
        try:
            raw = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=max(1, top_k),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"Vector search failed: {exc}") from exc

        ids = (raw.get("ids") or [[]])[0]
        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]

        records: List[VectorRecord] = []
        for i, _id in enumerate(ids):
            distance = float(dists[i]) if i < len(dists) else 1.0
            similarity = 1.0 - distance  # cosine space
            records.append(
                VectorRecord(
                    id=_id,
                    content=docs[i] if i < len(docs) else "",
                    metadata=dict(metas[i]) if i < len(metas) and metas[i] else {},
                    score=similarity,
                    distance=distance,
                )
            )
        return records


vector_store = VectorStore.instance()
