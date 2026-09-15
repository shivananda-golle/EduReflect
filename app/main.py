import logging
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api import auth_routes, chat_routes, routes
from app.database.models import init_db
from app.services.usage_limits import LimitExceeded
from app.utils.config import CORS_ORIGINS

# App loggers (e.g. sign-up limiting mode, LLM rate limits) print at INFO; no-op if logging is already configured
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="EduReflect API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # Create any missing tables (a fresh database, or new tables such as usage_counters)
    init_db()
    # Load the embedding model and FAISS index in the background so the first question is fast
    threading.Thread(target=warm_up_retriever, daemon=True).start()


def warm_up_retriever():
    try:
        from app.services.kb_retriever import _lazy_load
        _lazy_load()
    except Exception as e:
        logging.getLogger(__name__).warning("Retriever warm-up failed: %s", e)


@app.exception_handler(LimitExceeded)
def limit_exceeded_handler(request: Request, exc: LimitExceeded):
    return JSONResponse(status_code=429, content={"detail": exc.message})

app.include_router(auth_routes.router)
app.include_router(chat_routes.router)
app.include_router(routes.router)

@app.get("/")
def root():
    return {"message": "EduReflect API is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}