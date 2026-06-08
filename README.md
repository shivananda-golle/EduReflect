# EduReflect

An AI-powered educational learning assistant built as an MVP. EduReflect helps students learn, revise, and self-assess by combining a Retrieval-Augmented Generation (RAG) Q&A pipeline, document understanding (PDF/DOCX), chat-based study sessions, and automated weekly quiz emails.

> **Stack:** FastAPI · Streamlit · SQLAlchemy + Alembic · FAISS + Sentence-Transformers · Hugging Face Inference Router · APScheduler

---

## Features

- **Conversational learning** — multi-turn chats grouped into projects, with editable messages and full edit history.
- **Grounded answers** — answers are generated against a local FAISS knowledge base (E5 embeddings) so responses cite the evidence used.
- **Configurable response style** — pick format (brief / bullets / presentation), depth (kid / standard / exam), and length (short / medium / long).
- **Document Q&A** — upload a PDF or DOCX and ask questions directly about its contents.
- **Weekly quiz emails** — APScheduler job auto-generates a personalised quiz each Sunday from the user's recent learning and emails a unique quiz link.
- **Quiz tracking** — quizzes are scored, time-tracked, and stored as attempts for progress analytics.
- **Auth & subscriptions** — JWT-based login/signup with bcrypt hashing and free / basic / premium tiers with monthly chat limits.
- **PDF export** — export chats as a styled PDF from the Streamlit UI (ReportLab).

---

## Architecture

```
┌─────────────────────┐        ┌──────────────────────┐
│  Streamlit frontend │ ─────► │   FastAPI backend    │
│  (frontend/         │  HTTP  │   (app/main.py)      │
│   streamlit_app.py) │        │                      │
└─────────────────────┘        │  ┌────────────────┐  │
                               │  │ auth_routes    │  │
                               │  │ chat_routes    │  │
                               │  │ routes (quiz)  │  │
                               │  └────────────────┘  │
                               │           │          │
                               │  ┌────────▼───────┐  │
                               │  │   services/    │  │
                               │  │  generator,    │  │
                               │  │  kb_retriever, │  │
                               │  │  question_gen, │  │
                               │  │  email_service │  │
                               │  └────────┬───────┘  │
                               └───────────┼──────────┘
                                           │
                ┌──────────────────────────┼──────────────────────────┐
                ▼                          ▼                          ▼
        ┌──────────────┐         ┌──────────────────┐       ┌──────────────────┐
        │  SQLite DB   │         │  FAISS index +   │       │  Hugging Face    │
        │ (edureflect  │         │   metadata.json  │       │  Router API      │
        │    .db)      │         │  (data/index/)   │       │  (LLM)           │
        └──────────────┘         └──────────────────┘       └──────────────────┘
```

---

## Project structure

```
.
├── app/
│   ├── main.py                  # FastAPI entrypoint
│   ├── scheduler.py             # APScheduler: weekly quiz job (Sun 9 AM)
│   ├── api/
│   │   ├── auth_routes.py       # signup / login / JWT
│   │   ├── chat_routes.py       # projects, chats, messages, documents
│   │   └── routes.py            # /ask, weekly-quiz endpoints
│   ├── database/
│   │   └── models.py            # SQLAlchemy models + JWT helpers
│   ├── services/
│   │   ├── generator.py         # LLM call (HF Router)
│   │   ├── kb_builder.py        # build FAISS index from data/clean/
│   │   ├── kb_retriever.py      # query FAISS index
│   │   ├── question_generator.py
│   │   ├── weekly_quiz_scheduler.py
│   │   ├── email_service.py     # SMTP sender
│   │   ├── document_processor.py
│   │   ├── summarizer.py
│   │   ├── refiner.py
│   │   ├── verifier.py
│   │   └── concept_tracker.py
│   └── utils/
│       ├── config.py            # env-driven LLM config
│       └── email_config.py      # SMTP config
├── alembic/                     # DB migrations
├── frontend/
│   └── streamlit_app.py         # Streamlit UI
├── scripts/
│   ├── wiki_collector.py        # ingest Wikipedia content
│   ├── pdf_to_text.py           # PDF → text
│   └── clean_text.py            # cleanup helper
├── requirements.txt
├── alembic.ini
└── .env.example
```

---

## Quick start

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/shivananda-golle/EduReflect.git
cd EduReflect
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> First-time runs of any RAG endpoint will download the `intfloat/e5-base` sentence-transformer model (~430 MB). This can take a few minutes.

### 3. Configure environment

Copy the example file and fill in the values:

```bash
cp .env.example .env
```

Required for LLM responses:

- `HF_API_TOKEN` — get one from <https://huggingface.co/settings/tokens>

Required for weekly quiz emails:

- `SMTP_USERNAME`, `SMTP_PASSWORD`, `SENDER_EMAIL` — for Gmail, generate an [App Password](https://support.google.com/accounts/answer/185833) and use it as `SMTP_PASSWORD`.

### 4. Initialise the database

```bash
alembic upgrade head
```

(If you don't have any migrations to apply, the tables will also be created on first API call via `Base.metadata.create_all`.)

### 5. Run the backend

```bash
python -m uvicorn app.main:app --reload
```

Backend: <http://127.0.0.1:8000> · Interactive docs: <http://127.0.0.1:8000/docs>

### 6. Run the frontend

In a new terminal (with the venv activated):

```bash
streamlit run frontend/streamlit_app.py
```

Frontend: <http://127.0.0.1:8501>

---

## Optional: build the local knowledge base

The `/ask` endpoint uses a FAISS index built from cleaned text files. To build one:

1. Drop `.txt` files into `data/clean/` (you can use the helpers in `scripts/` to convert PDFs or pull from Wikipedia).
2. Run:

   ```bash
   python -m app.services.kb_builder
   ```

This writes `data/index/faiss.index` and `data/index/metadata.json`. The `data/` directory is gitignored by design — knowledge bases are local-only.

---

## Optional: schedule weekly quiz emails

The scheduler is a separate process so you can run the API stateless. Start it with:

```bash
python -m app.scheduler
```

It triggers `process_weekly_quizzes()` every Sunday at 09:00 server time.

You can also trigger a run manually:

```bash
# all users
curl -X POST http://127.0.0.1:8000/api/v1/admin/send-weekly-quizzes

# single user
curl -X POST http://127.0.0.1:8000/api/v1/test/send-quiz-email/<user_id>
```

---

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/auth/signup` | Create a user |
| `POST` | `/api/v1/auth/login` | Get a JWT |
| `POST` | `/api/v1/ask` | Ask a question (RAG over the local KB) |
| `POST` | `/api/v1/projects` | Create a project |
| `POST` | `/api/v1/chats` | Start a chat |
| `POST` | `/api/v1/chats/{id}/messages` | Send a message |
| `POST` | `/api/v1/documents/process` | Upload PDF/DOCX and ask about it |
| `GET`  | `/api/v1/weekly-quiz/{quiz_id}` | Fetch a weekly quiz |
| `POST` | `/api/v1/weekly-quiz/{quiz_id}/submit` | Submit quiz answers |
| `GET`  | `/health` | Liveness probe |

Full schema at `/docs` (Swagger UI) once the backend is running.

---

## Configuration reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `HF_API_TOKEN` | *(empty)* | Hugging Face Router API token |
| `GENERATOR_MODEL` | `meta-llama/Llama-3.2-1B-Instruct` | LLM used for generation |
| `MAX_EVIDENCE_CHARS` | `2000` | Truncate evidence passed to the LLM |
| `REQUEST_TIMEOUT` | `120.0` | LLM HTTP timeout (seconds) |
| `BACKEND_URL` | `http://localhost:8000` | Used by the Streamlit frontend |
| `DEFAULT_API_TIMEOUT` | `30` | Frontend → backend timeout |
| `LONG_API_TIMEOUT` | `300` | Frontend timeout for slow endpoints |
| `SMTP_SERVER` | `smtp.gmail.com` | Outgoing mail server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | *(empty)* | SMTP creds |
| `SENDER_EMAIL` / `SENDER_NAME` | *(empty)* / `EduReflect` | "From" identity |

---

## Roadmap

- Replace the hard-coded JWT secret in `app/database/models.py` with an environment variable.
- Admin auth on `/admin/send-weekly-quizzes`.
- Dockerfile + `docker-compose` for one-command setup.
- Pluggable LLM providers (OpenAI, Anthropic, local Ollama).
- Better evaluation harness for answer quality.

---

## License

This project is released for educational use. Add a license of your choice (e.g. MIT) before publishing widely.

---

## Acknowledgements

- [FastAPI](https://fastapi.tiangolo.com/) · [Streamlit](https://streamlit.io/)
- [Hugging Face Inference Router](https://huggingface.co/) and the `meta-llama/Llama-3.2-1B-Instruct` model
- [Sentence-Transformers](https://www.sbert.net/) (`intfloat/e5-base`) and [FAISS](https://github.com/facebookresearch/faiss)
