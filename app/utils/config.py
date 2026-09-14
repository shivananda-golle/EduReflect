
import os
from dotenv import load_dotenv

load_dotenv()

HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")

# Models
GENERATOR_MODEL = os.getenv("GENERATOR_MODEL", "meta-llama/Llama-3.1-8B-Instruct")

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