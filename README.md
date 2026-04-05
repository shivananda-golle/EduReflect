# EduReflect (MVP)

FastAPI backend + Streamlit frontend for an educational Q&A / RAG prototype.

## Run locally

### 1) Create venv + install deps

```bash
python -m venv .venv
# activate on Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Start backend

```bash
python -m uvicorn app.main:app --reload
```

Backend runs at: http://127.0.0.1:8000

### 3) Start frontend

```bash
streamlit run frontend/streamlit_app.py
```

Frontend runs at: http://127.0.0.1:8501

## Notes

- Sensitive/local files are intentionally ignored (e.g. `.env`, `*.db`).
- Large/local datasets and generated indexes under `data/` are not committed to GitHub.
