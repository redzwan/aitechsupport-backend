"""Retrieval-Augmented answering: embed the question, pull the nearest KB chunks
for the tenant's bot via pgvector, then ask Claude to answer from that context.

This is the heart of the product. Ingestion (chunk + embed KnowledgeSources) is a
sibling concern handled by a background worker — see PROJECT_STATE.md Phase 1.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core import llm
from app.models.knowledge import Chunk
from app.models.bot import Bot

TOP_K = 6


def retrieve(db: Session, organization_id: int, bot_id: int, question: str, k: int = TOP_K) -> list[Chunk]:
    """Return the k most similar chunks for this tenant's bot (pgvector cosine)."""
    query_vec = llm.embed_texts([question], input_type="query")[0]
    return (
        db.query(Chunk)
        .filter(Chunk.organization_id == organization_id)
        .join(Bot, Bot.id == bot_id)  # scope to the bot's org; refine to source ids as ingestion lands
        .order_by(Chunk.embedding.cosine_distance(query_vec))
        .limit(k)
        .all()
    )


def answer_question(db: Session, bot: Bot, question: str) -> str:
    """End-to-end: retrieve context, then generate a grounded answer."""
    chunks = retrieve(db, bot.organization_id, bot.id, question)
    if not chunks:
        return bot.fallback_message or "I don't have an answer for that yet."
    context = "\n\n---\n\n".join(c.content for c in chunks)
    return llm.answer(bot.system_prompt or "", context, question)
