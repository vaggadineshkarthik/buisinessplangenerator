"""Application configuration.

All configuration is sourced from environment variables (or a local .env file)
so that secrets such as the OpenRouter API key never leave the backend process.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Project layout: <repo root>/backend/app/config.py  ->  <repo root>
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
# Storage location can be overridden (used by the test-suite to run isolated).
STORAGE_DIR = Path(os.environ.get("RAGIFY_STORAGE_DIR", str(REPO_ROOT / "storage")))
DOCUMENTS_DIR = STORAGE_DIR / "documents"
CHROMA_DIR = STORAGE_DIR / "chroma"
DB_PATH = STORAGE_DIR / "ragify.db"

for _p in (STORAGE_DIR, DOCUMENTS_DIR, CHROMA_DIR):
    _p.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- OpenRouter ----
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="openai/gpt-oss-120b", alias="OPENROUTER_MODEL")
    openrouter_site_url: str = Field(default="http://localhost:3000", alias="OPENROUTER_SITE_URL")
    openrouter_app_name: str = Field(default="RAGify AI", alias="OPENROUTER_APP_NAME")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    openrouter_temperature: float = Field(default=0.2, alias="OPENROUTER_TEMPERATURE")
    openrouter_max_tokens: int = Field(default=1200, alias="OPENROUTER_MAX_TOKENS")
    openrouter_timeout: float = Field(default=120.0, alias="OPENROUTER_TIMEOUT")

    # ---- Embeddings ----
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5", alias="EMBEDDING_MODEL")
    embedding_batch_size: int = Field(default=32, alias="EMBEDDING_BATCH_SIZE")

    # ---- Vector store ----
    vector_db: str = Field(default="chroma", alias="VECTOR_DB")
    chroma_collection: str = Field(default="ragify_documents", alias="CHROMA_COLLECTION")

    # ---- Chunking / retrieval ----
    chunk_size: int = Field(default=1000, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=200, alias="CHUNK_OVERLAP")
    top_k: int = Field(default=5, alias="TOP_K")
    similarity_threshold: float = Field(default=0.35, alias="SIMILARITY_THRESHOLD")
    max_retries: int = Field(default=2, alias="MAX_RETRIES")

    # ---- Uploads ----
    max_file_size_mb: int = Field(default=25, alias="MAX_FILE_SIZE_MB")
    allowed_extensions: Annotated[List[str], NoDecode] = Field(
        default=[".pdf", ".docx", ".txt", ".csv"], alias="ALLOWED_EXTENSIONS"
    )

    # ---- Server ----
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    cors_origins: Annotated[List[str], NoDecode] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        alias="CORS_ORIGINS",
    )

    @field_validator("allowed_extensions", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def has_openrouter_key(self) -> bool:
        return bool(self.openrouter_api_key and self.openrouter_api_key.strip())

    @property
    def storage_dir(self) -> Path:
        return STORAGE_DIR

    @property
    def documents_dir(self) -> Path:
        return DOCUMENTS_DIR

    @property
    def chroma_dir(self) -> Path:
        return CHROMA_DIR

    @property
    def db_path(self) -> Path:
        return DB_PATH


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
