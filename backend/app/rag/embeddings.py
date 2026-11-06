"""Local embedding generation using sentence-transformers.

The model is loaded lazily and cached for the lifetime of the process. Query and
document embeddings use the same model so that cosine similarity is meaningful.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Dict, List, Optional

from ..config import settings


class EmbeddingError(Exception):
    """Raised when embeddings cannot be produced."""


class EmbeddingService:
    """Thread-safe singleton wrapper around a sentence-transformers model."""

    _instance: Optional["EmbeddingService"] = None
    _instance_lock = threading.Lock()

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = model_name or settings.embedding_model
        self._model = None
        self._load_lock = threading.Lock()
        self._dimension: Optional[int] = None

    # -- singleton ---------------------------------------------------------
    @classmethod
    def instance(cls) -> "EmbeddingService":
        with cls._instance_lock:
            if cls._instance is None or cls._instance.model_name != settings.embedding_model:
                cls._instance = cls()
            return cls._instance

    # -- loading -----------------------------------------------------------
    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def dimension(self) -> Optional[int]:
        if self._dimension is None and self._model is not None:
            self._dimension = self._model.get_sentence_embedding_dimension()
        return self._dimension

    def _load_model(self):
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer
            except Exception as exc:  # noqa: BLE001
                raise EmbeddingError(
                    "sentence-transformers is not installed. Run "
                    "`pip install -r requirements.txt`."
                ) from exc
            try:
                self._model = SentenceTransformer(self.model_name)
                self._dimension = self._model.get_sentence_embedding_dimension()
            except Exception as exc:  # noqa: BLE001
                raise EmbeddingError(
                    f"Failed to load embedding model '{self.model_name}': {exc}. "
                    "Check your internet connection (the model is downloaded on first use)."
                ) from exc
        return self._model

    def ensure_loaded(self) -> None:
        self._load_model()

    # -- encoding ----------------------------------------------------------
    def _encode(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        if not texts:
            return []
        model = self._load_model()
        prefix = ""
        # bge models recommend a query instruction prefix for retrieval.
        if is_query and "bge" in self.model_name.lower():
            prefix = "Represent this sentence for searching relevant passages: "
        payload = [prefix + t for t in texts] if prefix else texts
        vectors = model.encode(
            payload,
            batch_size=settings.embedding_batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        result = [v.tolist() for v in vectors]
        if self._dimension is None and result:
            self._dimension = len(result[0])
        return result

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._encode(texts, is_query=False)

    def embed_query(self, text: str) -> List[float]:
        vectors = self._encode([text], is_query=True)
        if not vectors:
            raise EmbeddingError("Query embedding produced no vector.")
        return vectors[0]

    # -- async helpers -----------------------------------------------------
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, text: str) -> List[float]:
        return await asyncio.to_thread(self.embed_query, text)

    async def aensure_loaded(self) -> None:
        await asyncio.to_thread(self.ensure_loaded)

    def status(self) -> Dict[str, object]:
        return {
            "model": self.model_name,
            "loaded": self.is_loaded,
            "dimension": self.dimension,
        }

    def validate_dimensions(self, vectors: List[List[float]]) -> None:
        if not vectors:
            return
        if self._dimension is None:
            self._dimension = len(vectors[0])
        expected = self._dimension
        for v in vectors:
            if len(v) != expected:
                raise EmbeddingError(
                    f"Embedding dimension mismatch: expected {expected}, got {len(v)}."
                )


embedding_service = EmbeddingService.instance()
