import logging

from fastapi import FastAPI

from app.api.routes_incidents import router as incidents_router
from app.config import settings
from app.db import init_db

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("rca_agent")

app = FastAPI(
    title="AI Production Incident RCA Agent",
    description="Multi-agent RCA investigation over logs, metrics, traces, and RAG-retrieved runbooks.",
    version="0.1.0",
)

app.include_router(incidents_router)


@app.on_event("startup")
def on_startup() -> None:
    try:
        init_db()
        logger.info("Database initialized (pgvector extension + tables ensured).")
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB init failed on startup (is Postgres up?): %s", exc)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
