
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# LLM provider: any OpenAI-compatible chat completions endpoint (default: Groq free tier).
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.groq.com/openai/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY", "")
# Tried in order; the next model is used when one is rate-limited (each has its own free quota).
LLM_MODELS = [m.strip() for m in os.getenv("LLM_MODELS", "openai/gpt-oss-20b,qwen/qwen3.8-27b").split(",") if m.strip()]
# When every model is rate-limited, wait up to this many seconds (from Retry-After) and retry once
LLM_MAX_RETRY_WAIT = float(os.getenv("LLM_MAX_RETRY_WAIT", "10"))

# Free-tier protection
DAILY_LLM_CALL_LIMIT = int(os.getenv("DAILY_LLM_CALL_LIMIT", "500"))      # all users combined
USER_DAILY_ACTION_LIMIT = int(os.getenv("USER_DAILY_ACTION_LIMIT", "20"))  # questions/quizzes/summaries/uploads per user
SIGNUPS_PER_IP_PER_HOUR = int(os.getenv("SIGNUPS_PER_IP_PER_HOUR", "3"))
# Used instead when the visitor IP is unknown (e.g. hidden by a hosting proxy)
SIGNUPS_PER_HOUR_GLOBAL = int(os.getenv("SIGNUPS_PER_HOUR_GLOBAL", "30"))
# Extra LLM call that rewrites each question before retrieval; off by default to halve usage.
ENABLE_PROMPT_REWRITE = _env_bool("ENABLE_PROMPT_REWRITE", "false")

# Retrieval: the index in data/index must be built with this same embedding model
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
INDEX_DIR = PROJECT_ROOT / "data" / "index"
# dense | bm25 | hybrid | hybrid_rerank (see eval/evaluate_retrieval.py for measurements)
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid")
RETRIEVAL_CANDIDATES = int(os.getenv("RETRIEVAL_CANDIDATES", "10"))
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")

# Evidence / truncation
MAX_EVIDENCE_CHARS = int(os.getenv("MAX_EVIDENCE_CHARS", "4500"))

# Request timeouts (seconds)
# HF generation + first-time downloads can exceed 30s on some machines/networks.
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "120.0"))

# Database (SQLite by default; any SQLAlchemy URL works, e.g. a hosted Postgres)
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{PROJECT_ROOT / 'edureflect.db'}"
# Hosted Postgres URLs (e.g. Neon) use the plain postgresql:// scheme; route them to the psycopg 3 driver
for _prefix in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_prefix):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_prefix):]

# JWT signing key. Set a long random value in production (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`).
SECRET_KEY = os.getenv("SECRET_KEY", "")

# Public URL of the Streamlit app, used in emailed quiz links
APP_URL = os.getenv("APP_URL", "http://localhost:8501")

# Browser origins allowed to call the API (comma-separated). Streamlit calls the API
# server-side, so it does not need an entry; only add origins for browser-based clients.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8501,http://localhost:3000").split(",") if o.strip()]

# Uploaded documents larger than this are rejected.
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))

# Admin endpoints (email triggers) require this key in the X-Admin-Key header.
# Leave empty to disable admin endpoints entirely.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")