"""FastAPI application entry point for RAGify AI."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import database as db
from .config import settings
from .rag.embeddings import embedding_service
from .rag.vector_store import vector_store
from .routes import chat, conversations, documents, plans, settings as settings_routes
from .services.openrouter import openrouter_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("ragify")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    settings_routes.apply_persisted_settings()
    logger.info("Database ready at %s", settings.db_path)
    logger.info("Vector store ready at %s", settings.chroma_dir)
    if not openrouter_client.configured:
        logger.warning(
            "OPENROUTER_API_KEY is not set. Chat will return a configuration error "
            "until it is added to your .env file."
        )
    yield


app = FastAPI(
    title="RAGify AI",
    description="Agentic Retrieval-Augmented Generation API powered by OpenRouter, "
    "LangGraph and ChromaDB.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(plans.router)
app.include_router(settings_routes.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


@app.get("/health", tags=["system"])
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.openrouter_app_name,
        "openrouter_configured": openrouter_client.configured,
        "model": settings.openrouter_model,
        "embedding_model": settings.embedding_model,
        "embedding_loaded": embedding_service.is_loaded,
        "vector_store": vector_store.health(),
    }


@app.get("/", tags=["system"])
async def root() -> Dict[str, Any]:
    return {
        "name": "RAGify AI API",
        "docs": "/docs",
        "health": "/health",
    }
