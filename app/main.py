from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api import auth_routes, chat_routes, routes
from app.database.models import init_db
from app.services.usage_limits import LimitExceeded
from app.utils.config import CORS_ORIGINS

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