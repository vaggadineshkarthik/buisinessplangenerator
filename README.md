# RAGify AI — Business Plan Generator (Agentic RAG)

RAGify AI turns your documents and business inputs into an investor-ready
**business plan**, and it is also a fully local, citation-grounded
Retrieval-Augmented Generation (RAG) application for asking questions about your
documents. Every generated section and every answer is produced by **OpenRouter**
from **retrieved document context**, with page-level citations you can inspect.

It runs entirely on your machine — the only external service is OpenRouter for
LLM generation. Embeddings run locally, and the vector database is a local
ChromaDB instance. No paid subscriptions required beyond an OpenRouter API key.

---

## ✨ Features

- **Business plan generator** — Describe your business (or paste notes) and
  RAGify AI writes a complete plan section by section: executive summary, market
  analysis, competitive analysis, financial projections, funding request and more.
  Choose which of the 13 standard sections to include, export to Markdown or text,
  and regenerate at any time.
- **Grounded generation** — The plan is grounded in the founder's structured
  inputs plus any uploaded research documents, and cites sourced facts as
  `[Source: market_research.pdf, Page 3]`. Unsupported figures are labelled as
  assumptions instead of being invented.
- **Document ingestion** — Upload PDF, DOCX, TXT and CSV files. Text is extracted,
  cleaned, chunked and embedded automatically.
- **Local embeddings** — `BAAI/bge-small-en-v1.5` (384-dim) via
  `sentence-transformers`. Batched, cached, with dimension validation.
- **Vector search** — Persistent ChromaDB (cosine similarity) with similarity
  thresholding, de-duplication and lexical + semantic reranking.
- **Agentic workflow** — Real **LangGraph** state machines with conditional edges.
  For questions: analyze → retrieve → evaluate → (rerank → generate → verify) or →
  insufficient, with up to two regeneration attempts. For plans:
  analyze → gather context → write each section → finalize, streaming every section
  as it is written.
- **Grounded answers** — Strict RAG system prompt. The model is instructed to never
  fabricate facts and to cite every important claim as
  `[Source: company_report.pdf, Page 4]`.
- **Answer verification** — Each claim is checked against the retrieved chunks and
  reported as verified / partially verified / unverified. (This is a heuristic
  support check — it does **not** guarantee correctness.)
- **Live streaming** — Server-Sent Events stream real workflow stages and real
  OpenRouter tokens. Nothing is simulated with timers.
- **Retrieved context panel** — Inspect the exact chunks, similarity scores and
  rerank scores behind every answer.
- **Conversation history** — Persisted in SQLite, resumable, regeneratable.
- **Premium dashboard** — Overview, Business Plan, AI Chat, Knowledge Base, Upload,
  Conversations, Analytics and Settings, with light/dark themes.

---

## 🧱 Tech Stack

| Layer            | Technology                                                        |
| ---------------- | ----------------------------------------------------------------- |
| Frontend         | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS        |
| UI               | shadcn-style components, Lucide React, react-markdown + remark-gfm |
| Backend          | Python 3.11+, FastAPI, Pydantic v2                                 |
| Orchestration    | LangChain, LangGraph (StateGraph + conditional edges)              |
| LLM              | OpenRouter (`openai/gpt-oss-120b` by default, configurable)        |
| Embeddings       | sentence-transformers (`BAAI/bge-small-en-v1.5`)                   |
| Vector database  | ChromaDB (persistent local storage)                                |
| Metadata DB      | SQLite                                                             |

---

## 📁 Project Structure

```
RAGify-AI/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, CORS, lifespan, /health
│   │   ├── config.py              # Environment-driven settings
│   │   ├── database.py            # SQLite schema + data access
│   │   ├── routes/                # documents, chat, conversations, plans, settings
│   │   ├── rag/                   # extraction, chunking, embeddings,
│   │   │                          # vector_store, retrieval, evaluation, ingestion
│   │   ├── agents/                # LangGraph state, prompts, nodes, graph
│   │   │                          # + plan_state, plan_prompts, plan_nodes, plan_graph
│   │   └── services/              # openrouter client, chat_service, plan_service
│   ├── tests/                     # pytest suite
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/
│   ├── app/                       # dashboard, plan, chat, documents, upload,
│   │                              # history, analytics, settings
│   ├── components/                # ui primitives, layout, chat, plan, shared
│   ├── lib/                       # api client, types, utils
│   └── package.json
├── storage/                       # created at runtime
│   ├── documents/                 # uploaded files
│   ├── chroma/                    # ChromaDB persistence
│   └── ragify.db                  # SQLite metadata
├── .env.example
├── start.bat
└── README.md
```

---

## ✅ Prerequisites

- **Python 3.11+** — https://www.python.org/downloads/
- **Node.js 18+** (includes npm) — https://nodejs.org/
- **An OpenRouter API key** — https://openrouter.ai/keys (free tier available)

> The first backend start downloads the embedding model (~90 MB) from Hugging
> Face. Make sure you have an internet connection for that first run.

---

## 🚀 Quick Start (Windows)

1. Copy `.env.example` to `.env` and add your OpenRouter key:

   ```bat
   copy .env.example .env
   ```

   Then edit `.env` and set:

   ```
   OPENROUTER_API_KEY=sk-or-v1-...
   ```

2. Double-click **`start.bat`**.

The script checks Python and Node.js, creates the backend virtual environment,
installs all dependencies, verifies your `.env`, starts both servers and opens
http://localhost:3000 in your browser.

| Service      | URL                            |
| ------------ | ------------------------------ |
| Frontend     | http://localhost:3000          |
| Backend      | http://localhost:8000          |
| API docs     | http://localhost:8000/docs     |

---

## 🛠 Manual Setup (any OS)

### 1. Backend

```bash
cd RAGify-AI/backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd RAGify-AI/frontend
npm install
npm run dev
```

Then open http://localhost:3000.

---

## ⚙️ Configuration

All configuration lives in a single `.env` file in the project root (see
`.env.example`). The backend reads it automatically; the **API key is never sent
to the browser**.

| Variable                | Default                    | Purpose                              |
| ----------------------- | -------------------------- | ------------------------------------ |
| `OPENROUTER_API_KEY`    | *(empty)*                  | OpenRouter API key (required for chat) |
| `OPENROUTER_MODEL`      | `openai/gpt-oss-120b`      | Model id (changeable in Settings)    |
| `EMBEDDING_MODEL`       | `BAAI/bge-small-en-v1.5`   | Local embedding model                |
| `VECTOR_DB`             | `chroma`                   | Vector store backend                 |
| `CHUNK_SIZE`            | `1000`                     | Characters per chunk                 |
| `CHUNK_OVERLAP`         | `200`                      | Overlap between chunks               |
| `TOP_K`                 | `5`                        | Chunks retrieved per query           |
| `SIMILARITY_THRESHOLD`  | `0.35`                     | Minimum similarity to keep a chunk   |
| `MAX_FILE_SIZE_MB`      | `25`                       | Upload size limit per file           |
| `NEXT_PUBLIC_API_URL`   | `http://localhost:8000`    | Backend URL used by the frontend     |

Most of these can also be changed at runtime from the **Settings** page.

---

## 🧭 Using the App

1. **Business Plan** — Enter the business name and, optionally, industry, product,
   target market, the problem you solve, funding sought and free-text notes. Pick
   which sections to include, optionally scope the plan to uploaded research
   documents, then generate. Each section streams in live, and the finished plan is
   saved — export it to Markdown/text or regenerate it any time.
2. **Upload Documents** — Drag & drop PDF/DOCX/TXT/CSV files. They are queued and
   processed in the background (extract → clean → chunk → embed → store).
3. **Knowledge Base** — Watch processing status, preview chunks, reprocess or
   delete documents (deletes also remove their embeddings).
4. **AI Chat** — Ask a question. Optionally scope the search to specific
   documents. Watch the live workflow stages and streaming tokens. Click any
   source chip to jump to the exact retrieved passage in the context panel.
5. **Conversations** — Reopen, preview or delete past threads.
6. **Analytics** — Corpus growth, chunk distribution and activity.
7. **Settings** — Model, temperature, retrieval and ingestion parameters, plus
   live diagnostics.

---

## 🔌 API Endpoints

| Method | Path                                | Description                     |
| ------ | ----------------------------------- | ------------------------------- |
| GET    | `/api/plans/catalog`                | Available plan sections         |
| POST   | `/api/plans/generate`               | Generate a plan (non-streaming)  |
| POST   | `/api/plans/generate/stream`        | Generate a plan (SSE streaming)  |
| POST   | `/api/plans/{id}/regenerate`        | Regenerate a plan (SSE)          |
| GET    | `/api/plans`                        | List saved plans                 |
| GET    | `/api/plans/{id}`                   | Plan with all sections           |
| DELETE | `/api/plans/{id}`                   | Delete a plan                    |
| GET    | `/api/plans/{id}/export`            | Export plan (markdown or text)   |
| POST   | `/api/documents/upload`             | Upload one or more documents    |
| GET    | `/api/documents`                    | List documents                  |
| GET    | `/api/documents/{id}`               | Get a document                  |
| GET    | `/api/documents/{id}/chunks`        | List indexed chunks             |
| DELETE | `/api/documents/{id}`               | Delete document + embeddings    |
| POST   | `/api/documents/{id}/reprocess`     | Re-run the ingestion pipeline   |
| POST   | `/api/chat`                         | Non-streaming chat              |
| POST   | `/api/chat/stream`                  | Streaming chat (SSE)            |
| POST   | `/api/chat/regenerate`              | Regenerate the last answer (SSE)|
| POST   | `/api/search`                       | Semantic search only            |
| GET    | `/api/conversations`                | List conversations              |
| POST   | `/api/conversations`                | Create a conversation           |
| GET    | `/api/conversations/{id}`           | Conversation + messages         |
| DELETE | `/api/conversations/{id}`           | Delete a conversation           |
| GET    | `/api/settings`                     | Runtime settings                |
| PUT    | `/api/settings`                     | Update runtime settings         |
| GET    | `/api/stats`                        | Dashboard statistics            |
| GET    | `/health`                           | Health & connectivity           |

Interactive docs: http://localhost:8000/docs

---

## 🧪 Testing

```bash
cd RAGify-AI/backend
pytest
```

The suite covers extraction (PDF/DOCX/TXT/CSV), chunking/overlap, embeddings,
ChromaDB storage, semantic retrieval, reranking, evaluation, citation generation,
answer verification, the LangGraph workflow, OpenRouter error handling, streaming,
the HTTP API, security (path traversal, file type/size validation, 404s) and the
business-plan generator (section catalogue, section-loop graph, grounded planning,
persistence, export, deletion and streaming).

Tests use a deterministic local embedder and a mocked OpenRouter client so they
run **offline and fast**, and they write to an isolated temp storage directory.
Mocks are used **only in tests** — the running application always calls the real
OpenRouter API and the real embedding model.

---

## 🩺 Troubleshooting

**`OPENROUTER_API_KEY is not configured` (HTTP 503)**
Add your key to `.env` in the project root and restart the backend. You can verify
connectivity from **Settings → Diagnostics**, or at http://localhost:8000/health.

**Backend says "Cannot reach the RAGify AI backend"**
The FastAPI server isn't running, or `NEXT_PUBLIC_API_URL` is wrong. Start it with
`uvicorn app.main:app --reload --port 8000` and confirm http://localhost:8000/health
returns `{"status":"ok"}`.

**First upload/query is very slow**
The embedding model is downloaded and loaded on first use. Subsequent runs use the
cached model in memory. This is expected.

**`pip install` fails on `torch` / `sentence-transformers`**
Use a 64-bit Python 3.11–3.12. On Windows, upgrade pip first:
`python -m pip install --upgrade pip`. If you're on Python 3.13+, some wheels may
be missing — Python 3.11 or 3.12 is recommended.

**Port already in use (3000 / 8000)**
Stop the process using the port, or run the servers on different ports:
`uvicorn app.main:app --port 8001` and `npm run dev -- -p 3001`
(update `NEXT_PUBLIC_API_URL` and `CORS_ORIGINS` accordingly).

**CORS errors in the browser console**
Ensure `CORS_ORIGINS` includes the exact frontend origin you're using
(e.g. `http://localhost:3000`), then restart the backend.

**Upload rejected**
Only `.pdf, .docx, .txt, .csv` are accepted, up to `MAX_FILE_SIZE_MB` (default 25).
Duplicate files (identical content) are rejected by content hash.

**ChromaDB / SQLite errors**
Delete the `storage/` folder to reset the index and metadata, then restart. You'll
need to re-upload your documents.

**Changing the embedding model**
If you switch `EMBEDDING_MODEL`, existing vectors become incompatible — reprocess
your documents (or reset `storage/`).

---

## 🔒 Security Notes

- The OpenRouter API key is stored in `.env` and read **only** by the backend. It is
  never returned by any API endpoint or sent to the frontend.
- Uploads are validated by extension **and** content, size-limited, and stored under
  a sanitized, UUID-based filename to prevent path traversal.
- Uploaded document text is treated as **untrusted data**, never as instructions,
  and is not executed. The RAG system prompt explicitly instructs the model to
  ignore instructions found inside documents.
- CORS is restricted by default to localhost origins.
- Answer verification is a heuristic support check and does not guarantee factual
  correctness — always review the cited sources.

---

## 📄 License

Provided for educational and personal use. OpenRouter, ChromaDB,
sentence-transformers, LangChain and LangGraph are subject to their own licenses.
