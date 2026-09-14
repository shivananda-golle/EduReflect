"""
Run the FastAPI backend inside the Streamlit process.

Streamlit Community Cloud runs a single `streamlit run` command, so with EMBEDDED_BACKEND=true the API
starts once per process on a background thread, listening on localhost only. Locally you can still run
the backend separately and leave EMBEDDED_BACKEND unset.
"""
import os
import sys
import threading
import time
from pathlib import Path

import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def export_secrets_to_env():
    """Expose top-level Streamlit secrets as environment variables, which the backend config reads."""
    try:
        for key, value in st.secrets.items():
            if isinstance(value, (str, int, float, bool)) and key not in os.environ:
                os.environ[key] = str(value)
    except Exception:
        # No secrets file (e.g. local runs configured through .env)
        pass


def is_enabled() -> bool:
    return os.getenv("EMBEDDED_BACKEND", "false").strip().lower() in ("1", "true", "yes", "on")


@st.cache_resource(show_spinner="Starting EduReflect…")
def start(port: int) -> str:
    """Start the API on a daemon thread and return its base URL once /health responds."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import uvicorn
    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, name="embedded-api", daemon=True).start()

    url = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            if requests.get(f"{url}/health", timeout=1).ok:
                return url
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError("Embedded backend did not start within 60 seconds")
