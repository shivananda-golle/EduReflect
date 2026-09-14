
import os
from dotenv import load_dotenv

load_dotenv()

def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# LLM provider: any OpenAI-compatible chat completions endpoint (default: Groq free tier).
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.groq.com/openai/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY", "")
# Tried in order; the next model is used when one is rate-limited (each has its own free quota).
LLM_MODELS = [m.strip() for m in os.getenv("LLM_MODELS", "openai/gpt-oss-20b,qwen/qwen3.8-27b").split(",") if m.strip()]

# Free-tier protection
DAILY_LLM_CALL_LIMIT = int(os.getenv("DAILY_LLM_CALL_LIMIT", "500"))      # all users combined
USER_DAILY_ACTION_LIMIT = int(os.getenv("USER_DAILY_ACTION_LIMIT", "20"))  # questions/quizzes/summaries/uploads per user
SIGNUPS_PER_IP_PER_HOUR = int(os.getenv("SIGNUPS_PER_IP_PER_HOUR", "3"))
# Extra LLM call that rewrites each question before retrieval; off by default to halve usage.
ENABLE_PROMPT_REWRITE = _env_bool("ENABLE_PROMPT_REWRITE", "false")

# Evidence / truncation
MAX_EVIDENCE_CHARS = int(os.getenv("MAX_EVIDENCE_CHARS", "2000"))

# Request timeouts (seconds)
# HF generation + first-time downloads can exceed 30s on some machines/networks.
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "120.0"))

# JWT signing key. Set a long random value in production (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`).
SECRET_KEY = os.getenv("SECRET_KEY", "")

# Browser origins allowed to call the API (comma-separated). Streamlit calls the API
# server-side, so it does not need an entry; only add origins for browser-based clients.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8501,http://localhost:3000").split(",") if o.strip()]

# Uploaded documents larger than this are rejected.
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))

# Admin endpoints (email triggers) require this key in the X-Admin-Key header.
# Leave empty to disable admin endpoints entirely.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")