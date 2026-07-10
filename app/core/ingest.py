"""Ingest a KnowledgeSource: load -> chunk -> embed -> store chunks.

Runs off the request path (FastAPI BackgroundTasks for the MVP; swap in a real
worker queue later — see PROJECT_STATE.md Phase 1). Opens its own DB session
because the request's session is already closed by the time this runs.

Idempotent: re-ingesting a source replaces its existing chunks.
"""
from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.core import embeddings, chunking, loaders
from app.models.knowledge import KnowledgeSource, Chunk

logger = logging.getLogger(__name__)


def _load_text(source_type: str, location: str | None, raw_text: str | None) -> tuple[str | None, str]:
    """Return (discovered_title, text) for the source."""
    if source_type == "url":
        if not location:
            raise ValueError("url source requires a location")
        return loaders.load_url(location)
    # "text" and "file" arrive with their content already extracted.
    return None, (raw_text or "")


def ingest_source(
    source_id: int,
    source_type: str,
    location: str | None = None,
    raw_text: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        src = db.get(KnowledgeSource, source_id)
        if src is None:
            logger.warning("ingest: source %s vanished before processing", source_id)
            return

        src.status = "processing"
        db.commit()

        try:
            discovered_title, text = _load_text(source_type, location, raw_text)
            if discovered_title and not src.title:
                src.title = discovered_title

            pieces = chunking.chunk_text(text)
            if not pieces:
                src.status = "failed"
                db.commit()
                logger.warning("ingest: source %s produced no chunks (empty text)", source_id)
                return

            vectors = embeddings.embed_documents(pieces)

            # Replace any prior chunks so re-ingest is idempotent.
            db.query(Chunk).filter(Chunk.knowledge_source_id == src.id).delete()
            db.add_all(
                Chunk(
                    organization_id=src.organization_id,
                    knowledge_source_id=src.id,
                    content=content,
                    embedding=vector,
                )
                for content, vector in zip(pieces, vectors)
            )
            src.status = "ready"
            db.commit()
            logger.info("ingest: source %s ready (%d chunks)", source_id, len(pieces))

        except Exception:
            db.rollback()
            # Re-fetch: the failed transaction was rolled back, so mark status in a fresh tx.
            src = db.get(KnowledgeSource, source_id)
            if src is not None:
                src.status = "failed"
                db.commit()
            logger.exception("ingest: source %s failed", source_id)
    finally:
        db.close()
