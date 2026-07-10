"""AiTechSupport API — FastAPI entrypoint.

Run: uvicorn main:app --reload --port 8100
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import engine, Base
from app.core.settings import settings, cors_origins
from app.api.v1.api import api_router

# Dev convenience: create tables on boot. In production, migrations are the
# source of truth (`alembic upgrade head`).
import app.models  # noqa: F401 — register all models on Base.metadata
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
def root() -> dict:
    return {"message": "AiTechSupport API", "docs": "/docs"}
