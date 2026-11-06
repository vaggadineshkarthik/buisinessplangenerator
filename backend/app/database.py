"""SQLite metadata database.

Stores documents, chunk metadata, conversations, messages and runtime settings.
The vector store (ChromaDB) holds the embeddings; this database holds everything
else that needs to survive a restart.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import settings

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    filename      TEXT NOT NULL,
    file_type     TEXT NOT NULL,
    file_path     TEXT NOT NULL,
    file_size     INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'processing',
    error         TEXT,
    num_chunks    INTEGER NOT NULL DEFAULT 0,
    num_pages     INTEGER NOT NULL DEFAULT 0,
    char_count    INTEGER NOT NULL DEFAULT 0,
    preview       TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id              TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    page_number     INTEGER,
    char_start      INTEGER NOT NULL DEFAULT 0,
    char_end        INTEGER NOT NULL DEFAULT 0,
    content         TEXT NOT NULL,
    token_estimate  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

CREATE TABLE IF NOT EXISTS conversations (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    document_ids TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    citations       TEXT NOT NULL DEFAULT '[]',
    contexts        TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    business_name TEXT NOT NULL,
    industry      TEXT,
    status        TEXT NOT NULL DEFAULT 'draft',
    error         TEXT,
    inputs        TEXT NOT NULL DEFAULT '{}',
    document_ids  TEXT NOT NULL DEFAULT '[]',
    model         TEXT,
    overview      TEXT NOT NULL DEFAULT '',
    section_count INTEGER NOT NULL DEFAULT 0,
    word_count    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_sections (
    id         TEXT PRIMARY KEY,
    plan_id    TEXT NOT NULL,
    key        TEXT NOT NULL,
    title      TEXT NOT NULL,
    position   INTEGER NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    citations  TEXT NOT NULL DEFAULT '[]',
    word_count INTEGER NOT NULL DEFAULT 0,
    status     TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_plan_sections_plan ON plan_sections(plan_id);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(settings.db_path), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.execute("PRAGMA journal_mode = WAL")
    return _conn


def init_db() -> None:
    with _lock:
        conn = get_conn()
        conn.executescript(SCHEMA)
        conn.commit()


def _rows_to_dicts(rows) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------
def insert_document(doc: Dict[str, Any]) -> None:
    with _lock:
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO documents
                (id, name, filename, file_type, file_path, file_size, status,
                 error, num_chunks, num_pages, char_count, preview, created_at, updated_at)
            VALUES (:id, :name, :filename, :file_type, :file_path, :file_size, :status,
                    :error, :num_chunks, :num_pages, :char_count, :preview, :created_at, :updated_at)
            """,
            {
                "error": None,
                "num_chunks": 0,
                "num_pages": 0,
                "char_count": 0,
                "preview": None,
                **doc,
            },
        )
        conn.commit()


def update_document(doc_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = utcnow()
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = doc_id
    with _lock:
        conn = get_conn()
        conn.execute(f"UPDATE documents SET {cols} WHERE id = :id", fields)
        conn.commit()


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        row = get_conn().execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def list_documents() -> List[Dict[str, Any]]:
    with _lock:
        rows = get_conn().execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return _rows_to_dicts(rows)


def delete_document(doc_id: str) -> bool:
    with _lock:
        conn = get_conn()
        cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        conn.commit()
    return cur.rowcount > 0


# --------------------------------------------------------------------------
# Chunks
# --------------------------------------------------------------------------
def insert_chunks(chunks: List[Dict[str, Any]]) -> None:
    if not chunks:
        return
    with _lock:
        conn = get_conn()
        conn.executemany(
            """
            INSERT OR REPLACE INTO chunks
                (id, document_id, chunk_index, page_number, char_start, char_end,
                 content, token_estimate)
            VALUES (:id, :document_id, :chunk_index, :page_number, :char_start, :char_end,
                    :content, :token_estimate)
            """,
            chunks,
        )
        conn.commit()


def get_chunks_for_document(doc_id: str) -> List[Dict[str, Any]]:
    with _lock:
        rows = (
            get_conn()
            .execute(
                "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index",
                (doc_id,),
            )
            .fetchall()
        )
    return _rows_to_dicts(rows)


def delete_chunks_for_document(doc_id: str) -> None:
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        conn.commit()


# --------------------------------------------------------------------------
# Conversations & messages
# --------------------------------------------------------------------------
def insert_conversation(conv: Dict[str, Any]) -> None:
    with _lock:
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO conversations (id, title, document_ids, created_at, updated_at)
            VALUES (:id, :title, :document_ids, :created_at, :updated_at)
            """,
            conv,
        )
        conn.commit()


def update_conversation(conv_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = utcnow()
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = conv_id
    with _lock:
        conn = get_conn()
        conn.execute(f"UPDATE conversations SET {cols} WHERE id = :id", fields)
        conn.commit()


def get_conversation(conv_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        row = get_conn().execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    if not row:
        return None
    conv = dict(row)
    conv["document_ids"] = json.loads(conv.get("document_ids") or "[]")
    return conv


def list_conversations() -> List[Dict[str, Any]]:
    with _lock:
        rows = (
            get_conn()
            .execute(
                """
                SELECT c.*,
                       (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
                FROM conversations c
                ORDER BY c.updated_at DESC
                """
            )
            .fetchall()
        )
    result = []
    for r in rows:
        d = dict(r)
        d["document_ids"] = json.loads(d.get("document_ids") or "[]")
        result.append(d)
    return result


def delete_conversation(conv_id: str) -> bool:
    with _lock:
        conn = get_conn()
        cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        conn.commit()
    return cur.rowcount > 0


def insert_message(msg: Dict[str, Any]) -> None:
    with _lock:
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO messages
                (id, conversation_id, role, content, citations, contexts, created_at)
            VALUES (:id, :conversation_id, :role, :content, :citations, :contexts, :created_at)
            """,
            msg,
        )
        conn.commit()


def delete_message(message_id: str) -> bool:
    with _lock:
        conn = get_conn()
        cur = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        conn.commit()
    return cur.rowcount > 0


def get_messages(conv_id: str) -> List[Dict[str, Any]]:
    with _lock:
        rows = (
            get_conn()
            .execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
                (conv_id,),
            )
            .fetchall()
        )
    result = []
    for r in rows:
        d = dict(r)
        d["citations"] = json.loads(d.get("citations") or "[]")
        d["contexts"] = json.loads(d.get("contexts") or "[]")
        result.append(d)
    return result


# --------------------------------------------------------------------------
# App settings (runtime key/value overrides)
# --------------------------------------------------------------------------
def set_setting(key: str, value: str) -> None:
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    with _lock:
        row = get_conn().execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def all_settings() -> Dict[str, str]:
    with _lock:
        rows = get_conn().execute("SELECT key, value FROM app_settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


# --------------------------------------------------------------------------
# Business plans
# --------------------------------------------------------------------------
def _plan_row(row: sqlite3.Row) -> Dict[str, Any]:
    plan = dict(row)
    plan["inputs"] = json.loads(plan.get("inputs") or "{}")
    plan["document_ids"] = json.loads(plan.get("document_ids") or "[]")
    return plan


def insert_plan(plan: Dict[str, Any]) -> None:
    with _lock:
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO plans
                (id, title, business_name, industry, status, error, inputs,
                 document_ids, model, overview, section_count, word_count,
                 created_at, updated_at)
            VALUES (:id, :title, :business_name, :industry, :status, :error, :inputs,
                    :document_ids, :model, :overview, :section_count, :word_count,
                    :created_at, :updated_at)
            """,
            {
                "industry": None,
                "error": None,
                "model": None,
                "overview": "",
                "section_count": 0,
                "word_count": 0,
                **plan,
            },
        )
        conn.commit()


def update_plan(plan_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = utcnow()
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = plan_id
    with _lock:
        conn = get_conn()
        conn.execute(f"UPDATE plans SET {cols} WHERE id = :id", fields)
        conn.commit()


def get_plan(plan_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        row = get_conn().execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    return _plan_row(row) if row else None


def list_plans() -> List[Dict[str, Any]]:
    with _lock:
        rows = (
            get_conn()
            .execute("SELECT * FROM plans ORDER BY created_at DESC")
            .fetchall()
        )
    return [_plan_row(r) for r in rows]


def delete_plan(plan_id: str) -> bool:
    with _lock:
        conn = get_conn()
        cur = conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        conn.execute("DELETE FROM plan_sections WHERE plan_id = ?", (plan_id,))
        conn.commit()
    return cur.rowcount > 0


def insert_plan_section(section: Dict[str, Any]) -> None:
    with _lock:
        conn = get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO plan_sections
                (id, plan_id, key, title, position, content, citations, word_count, status)
            VALUES (:id, :plan_id, :key, :title, :position, :content, :citations,
                    :word_count, :status)
            """,
            {
                "content": "",
                "citations": "[]",
                "word_count": 0,
                "status": "pending",
                **section,
            },
        )
        conn.commit()


def update_plan_section(section_id: str, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = section_id
    with _lock:
        conn = get_conn()
        conn.execute(f"UPDATE plan_sections SET {cols} WHERE id = :id", fields)
        conn.commit()


def get_plan_sections(plan_id: str) -> List[Dict[str, Any]]:
    with _lock:
        rows = (
            get_conn()
            .execute(
                "SELECT * FROM plan_sections WHERE plan_id = ? ORDER BY position",
                (plan_id,),
            )
            .fetchall()
        )
    result = []
    for r in rows:
        d = dict(r)
        d["citations"] = json.loads(d.get("citations") or "[]")
        result.append(d)
    return result


def delete_plan_sections(plan_id: str) -> None:
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM plan_sections WHERE plan_id = ?", (plan_id,))
        conn.commit()


# --------------------------------------------------------------------------
# Analytics helpers
# --------------------------------------------------------------------------
def stats() -> Dict[str, Any]:
    with _lock:
        conn = get_conn()
        total_docs = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
        ready_docs = conn.execute(
            "SELECT COUNT(*) AS c FROM documents WHERE status = 'ready'"
        ).fetchone()["c"]
        total_chunks = conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()["c"]
        total_convs = conn.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"]
        user_msgs = conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE role = 'user'"
        ).fetchone()["c"]
        recent_docs = [
            dict(r)
            for r in conn.execute(
                "SELECT id, name, status, num_chunks, created_at FROM documents "
                "ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
        ]
        recent_questions = [
            dict(r)
            for r in conn.execute(
                "SELECT m.content, m.created_at, c.title AS conversation_title "
                "FROM messages m JOIN conversations c ON c.id = m.conversation_id "
                "WHERE m.role = 'user' ORDER BY m.created_at DESC LIMIT 5"
            ).fetchall()
        ]
        total_plans = conn.execute("SELECT COUNT(*) AS c FROM plans").fetchone()["c"]
        ready_plans = conn.execute(
            "SELECT COUNT(*) AS c FROM plans WHERE status = 'ready'"
        ).fetchone()["c"]
        recent_plans = [
            dict(r)
            for r in conn.execute(
                "SELECT id, title, business_name, status, section_count, word_count, "
                "created_at FROM plans ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
        ]
    return {
        "total_documents": total_docs,
        "ready_documents": ready_docs,
        "total_chunks": total_chunks,
        "total_conversations": total_convs,
        "total_questions": user_msgs,
        "total_plans": total_plans,
        "ready_plans": ready_plans,
        "recent_uploads": recent_docs,
        "recent_questions": recent_questions,
        "recent_plans": recent_plans,
    }
