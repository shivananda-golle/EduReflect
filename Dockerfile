# EduReflect on Hugging Face Spaces (Docker SDK, port 7860).
# One process: Streamlit serves the UI and starts the FastAPI backend on localhost
# (EMBEDDED_BACKEND), so only the UI is reachable from outside.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Spaces run containers as UID 1000
RUN useradd -m -u 1000 user

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

USER user
ENV HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/home/user/.cache/fastembed \
    EMBEDDED_BACKEND=true
WORKDIR /home/user/app

# Bake the embedding model into the image so cold starts need no download
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY --chown=user:user app ./app
COPY --chown=user:user frontend ./frontend
COPY --chown=user:user data/index ./data/index

EXPOSE 7860
# XSRF/CORS checks are off because Spaces serves the app in an iframe, where they break file
# uploads; auth uses bearer tokens held server-side, not cookies.
CMD ["streamlit", "run", "frontend/streamlit_app.py", \
     "--server.port", "7860", \
     "--server.address", "0.0.0.0", \
     "--server.headless", "true", \
     "--server.maxUploadSize", "10", \
     "--server.enableXsrfProtection", "false", \
     "--server.enableCORS", "false", \
     "--browser.gatherUsageStats", "false"]
