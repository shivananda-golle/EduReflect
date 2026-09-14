# EduReflect

An AI-powered study assistant. EduReflect answers students' questions from a curated science and maths knowledge base using Retrieval-Augmented Generation (RAG), turns conversations into quizzes, tracks concept mastery, and answers questions about uploaded PDFs and DOCX files.

> **Stack:** FastAPI · Streamlit · SQLAlchemy (SQLite / Postgres) · FAISS + fastembed (`BAAI/bge-small-en-v1.5`, ONNX) · Groq (OpenAI-compatible LLM API) · APScheduler

**Live demo:** **<https://edureflect.streamlit.app/>** (free tier: sign up to try it; 20 actions per user per day. If the app has been idle, click "wake up" and give it about a minute.)

---

## Features

- **Grounded answers (RAG)**: questions are embedded with bge-small, matched against a FAISS index of 2,316 passages, and answered by an LLM using only the retrieved evidence, which is shown alongside the answer.
- **Configurable response style**: format (brief / bullets / presentation), depth (kid / standard / exam), and length (short / medium / long), plus optional diagnostic questions.
- **Quizzes and mastery tracking**: generate a 5-question multiple-choice quiz from any answer; results update per-concept mastery levels.
- **Document Q&A**: upload a PDF or DOCX, get a summary, and ask questions about it.
- **Study workspace**: multi-turn chats grouped into projects, pinning, search, message editing with history, chat summaries, and PDF export.
- **Weekly quiz emails** (optional): a scheduled job builds a personalised quiz from each user's recent chats and emails a link.
- **Runs entirely on free tiers**: no PyTorch (the whole app peaks at ~380 MB RAM), plus a global daily LLM budget, per-user daily limits, and sign-up throttling keep a public demo within free quotas.

---

## Architecture

```
┌──────────────────────┐   HTTP (server-side)   ┌──────────────────────────────┐
│  Streamlit frontend  │ ─────────────────────► │       FastAPI backend        │
│ frontend/            │  forwards visitor IP   │       app/main.py            │
│   streamlit_app.py   │                        │  auth · chats · quiz routes  │
└──────────────────────┘                        └──────────────┬───────────────┘
                                                               │
                         ┌─────────────────────────────────────┼─────────────────────────────┐
                         ▼                                     ▼                             ▼
               ┌───────────────────┐             ┌───────────────────────┐     ┌───────────────────────┐
               │  SQLite/Postgres  │             │  kb_retriever         │     │  llm_client           │
               │  users, chats,    │             │  bge-small (ONNX) +   │     │  Groq free tier       │
               │  quizzes, usage   │             │  FAISS (data/index/)  │     │  daily budget +       │
               │  counters         │             │                       │     │  model fallback       │
               └───────────────────┘             └───────────────────────┘     └───────────────────────┘
```

**Request flow for a question:** retrieve the top 5 passages from FAISS → build a grounded prompt (style, depth, length) → one LLM call through `llm_client` → store the answer and its evidence in the chat.

---

## Project structure

```
.
├── app/
│   ├── main.py                    # FastAPI app, startup table creation, limit error handler
│   ├── scheduler.py               # APScheduler: weekly quiz emails (Sun 09:00)
│   ├── api/
│   │   ├── auth_routes.py         # register / login / JWT / usage status
│   │   ├── chat_routes.py         # projects, chats, messages, documents, quizzes
│   │   └── routes.py              # /ask, weekly quizzes, admin email triggers
│   ├── database/
│   │   └── models.py              # SQLAlchemy models + JWT helpers
│   ├── services/
│   │   ├── llm_client.py          # single entry point for LLM calls
│   │   ├── usage_limits.py        # daily budgets, per-user and sign-up limits
│   │   ├── kb_builder.py          # build the FAISS index from data/clean/
│   │   ├── kb_retriever.py        # query the FAISS index
│   │   ├── generator.py           # grounded answer prompt
│   │   ├── question_generator.py  # quiz generation (JSON)
│   │   ├── summarizer.py          # chat summaries
│   │   ├── document_processor.py  # PDF/DOCX extraction + Q&A
│   │   ├── concept_tracker.py     # mastery tracking
│   │   ├── weekly_quiz_scheduler.py
│   │   └── email_service.py       # SMTP sender
│   └── utils/
│       ├── config.py              # environment-driven settings
│       └── email_config.py        # SMTP settings
├── frontend/
│   ├── streamlit_app.py           # Streamlit UI
│   └── embedded_backend.py        # optional: run the API inside the Streamlit process
├── data/index/                    # prebuilt FAISS index + passage metadata
├── scripts/                       # knowledge-base preparation (PDF → text, Wikipedia, cleaning)
├── alembic/                       # historical migrations (tables are created on startup)
├── requirements.txt
└── .env.example
```

---

## Quick start

### 1. Clone and create a virtual environment (Python 3.12)

```bash
git clone https://github.com/shivananda-golle/EduReflect.git
cd EduReflect
python -m venv .venv

# macOS / Linux / WSL
source .venv/bin/activate
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

The embedding model (`BAAI/bge-small-en-v1.5`, ~70 MB ONNX) downloads automatically on first start.

### 3. Configure environment

```bash
cp .env.example .env
```

| Needed for | Variables |
| --- | --- |
| LLM answers (required) | `GROQ_API_KEY`: free, no credit card, from <https://console.groq.com/keys> |
| Stable logins (recommended) | `SECRET_KEY`: generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| Weekly quiz emails (optional) | `SMTP_USERNAME`, `SMTP_PASSWORD`, `SENDER_EMAIL`, `ADMIN_API_KEY` |

### 4. Knowledge base

The prebuilt index is included in `data/index/` (`faiss.index` + `metadata.json`). See [Knowledge base](#knowledge-base) to rebuild it or use your own content.

### 5. Run

```bash
# Terminal 1: backend (tables are created automatically on startup)
python -m uvicorn app.main:app --port 8000

# Terminal 2: frontend
streamlit run frontend/streamlit_app.py
```

- Frontend: <http://localhost:8501>
- API docs (Swagger): <http://localhost:8000/docs>

---

## Knowledge base

The reference index contains **2,316 passages**:

- **1,207** from NCERT textbooks (Class 9 Mathematics, Class 10 Science)
- **1,109** from Wikipedia articles on core science topics (physics, chemistry, biology, energy, forces, and more)

To build your own:

```bash
pip install -r scripts/requirements.txt
python scripts/pdf_to_text.py        # data/raw_pdfs/*.pdf → data/raw/textbooks/
python scripts/wiki_collector.py     # Wikipedia topics → data/raw/wikipedia/
python scripts/clean_text.py         # data/raw/ → data/clean/
python -m app.services.kb_builder    # data/clean/ → data/index/
```

Passages are ~120-word chunks; tiny or symbol-heavy chunks are filtered out. After changing `EMBEDDING_MODEL`, re-embed the existing passages with `python -m app.services.kb_builder --from-metadata`.

---

## Deploy for free (Streamlit Community Cloud)

The whole app runs as a single Streamlit process: with `EMBEDDED_BACKEND=true`, the FastAPI backend starts on a background thread bound to localhost, so only the UI is public.

1. Create a free Postgres database (e.g. [Neon](https://neon.tech)) so accounts survive restarts, and copy its connection string.
2. On [share.streamlit.io](https://share.streamlit.io), create an app from this repository: branch `main`, main file `frontend/streamlit_app.py`, Python 3.12.
3. In **Advanced settings → Secrets**, add:

   ```toml
   EMBEDDED_BACKEND = "true"
   GROQ_API_KEY = "gsk_..."
   SECRET_KEY = "a-long-random-hex-string"
   DATABASE_URL = "postgresql://user:password@host/dbname?sslmode=require"
   ```

Top-level secrets are exported as environment variables before the backend starts.

---

## Free-tier protection

Every LLM call goes through `app/services/llm_client.py`, which makes a public demo safe to run at zero cost:

| Control | Default | Setting |
| --- | --- | --- |
| LLM calls per day (all users) | 500 | `DAILY_LLM_CALL_LIMIT` |
| Actions per user per day (questions, quizzes, summaries, uploads) | 20 | `USER_DAILY_ACTION_LIMIT` |
| Sign-ups per IP per hour | 3 | `SIGNUPS_PER_IP_PER_HOUR` |
| Model fallback on rate limit | `gpt-oss-20b` → `qwen3.8-27b` | `LLM_MODELS` |
| Prompt-rewrite pre-call | off | `ENABLE_PROMPT_REWRITE` |

Daily counters are stored in the database (UTC days). When a limit is reached, users see a friendly message (HTTP 429) instead of an error. Groq's free tier needs no payment method, so usage can never be billed.

---

## Weekly quiz emails (optional)

Run the scheduler as a separate process:

```bash
python -m app.scheduler
```

Admin endpoints trigger a run manually. They are **disabled unless `ADMIN_API_KEY` is set** and require it in the `X-Admin-Key` header:

```bash
curl -X POST http://localhost:8000/api/v1/admin/send-weekly-quizzes -H "X-Admin-Key: $ADMIN_API_KEY"
curl -X POST http://localhost:8000/api/v1/test/send-quiz-email/<user_id> -H "X-Admin-Key: $ADMIN_API_KEY"
```

---

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Create an account |
| `POST` | `/api/v1/auth/login-json` | Log in (JSON) and get a JWT |
| `GET` | `/api/v1/auth/subscription/status` | Remaining actions today |
| `POST` | `/api/v1/ask` | One-off RAG question (auth required) |
| `POST` | `/api/v1/chats` | Start a chat |
| `POST` | `/api/v1/chats/{id}/messages` | Ask a question in a chat |
| `POST` | `/api/v1/chats/{id}/quiz` | Generate a quiz from the latest answer |
| `POST` | `/api/v1/quiz/submit` | Submit quiz results and update mastery |
| `GET` | `/api/v1/progress` | Concept mastery |
| `POST` | `/api/v1/documents/process` | Upload a PDF/DOCX (max 10 MB) and ask about it |
| `GET` | `/health` | Liveness probe |

The full schema is at `/docs` once the backend is running.

---

## Configuration reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` / `LLM_API_KEY` | *(empty)* | LLM API key |
| `DATABASE_URL` | SQLite file in the project root | Any SQLAlchemy URL; `postgresql://` URLs use psycopg 3 |
| `EMBEDDED_BACKEND` | `false` | Run the API inside the Streamlit process (single-process hosting) |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed model; must match the index |
| `LLM_API_URL` | Groq chat completions URL | Any OpenAI-compatible endpoint |
| `LLM_MODELS` | `openai/gpt-oss-20b,qwen/qwen3.8-27b` | Models, tried in order |
| `DAILY_LLM_CALL_LIMIT` | `500` | Global LLM calls per day |
| `USER_DAILY_ACTION_LIMIT` | `20` | Per-user actions per day |
| `SIGNUPS_PER_IP_PER_HOUR` | `3` | Sign-up throttling |
| `ENABLE_PROMPT_REWRITE` | `false` | Rewrite questions with an extra LLM call |
| `SECRET_KEY` | random per process | JWT signing key |
| `ADMIN_API_KEY` | *(empty = disabled)* | Key for admin email endpoints |
| `CORS_ORIGINS` | `http://localhost:8501,http://localhost:3000` | Allowed browser origins |
| `MAX_UPLOAD_MB` | `10` | Upload size limit |
| `MAX_EVIDENCE_CHARS` | `2000` | Evidence passed to the LLM |
| `REQUEST_TIMEOUT` | `120.0` | LLM HTTP timeout (seconds) |
| `BACKEND_URL` | `http://localhost:8000` | Backend URL used by Streamlit |
| `DEFAULT_API_TIMEOUT` / `LONG_API_TIMEOUT` | `30` / `300` | Frontend → backend timeouts |
| `SMTP_SERVER` / `SMTP_PORT` | `smtp.gmail.com` / `587` | Mail server |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | *(empty)* | SMTP credentials (Gmail: use an App Password) |
| `SENDER_EMAIL` / `SENDER_NAME` | *(empty)* / `EduReflect` | "From" identity |

---

## Roadmap

- Answer verification: check each generated sentence against the evidence and rewrite unsupported claims.
- Structured output for key terms and follow-up questions.
- Evaluation harness for retrieval and answer quality.

---

## Acknowledgements

- [FastAPI](https://fastapi.tiangolo.com/) · [Streamlit](https://streamlit.io/)
- [Groq](https://groq.com/) for free LLM inference
- [fastembed](https://github.com/qdrant/fastembed) with `BAAI/bge-small-en-v1.5`, and [FAISS](https://github.com/facebookresearch/faiss)
- NCERT textbooks and Wikipedia for knowledge-base content
