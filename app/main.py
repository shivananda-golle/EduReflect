from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth_routes, chat_routes, routes
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
    # Initialize database if needed
    pass

app.include_router(auth_routes.router)
app.include_router(chat_routes.router)
app.include_router(routes.router)

@app.get("/")
def root():
    return {"message": "EduReflect API is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}