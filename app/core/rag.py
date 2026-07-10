"""Retrieval-Augmented answering: embed the question, pull the nearest KB chunks
for THIS bot via pgvector, then ask Claude to answer from that context.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core import embeddings, llm
from app.core.settings import settings
from app.models.knowledge import Chunk, KnowledgeSource
from app.models.bot import Bot


def retrieve(db: Session, bot: Bot, question: str, k: int | None = None) -> list[Chunk]:
    """Return the k most similar chunks belonging to this bot (pgvector cosine).

    Scoped to the bot's own KnowledgeSources (and its org), so a multi-bot org
    never leaks one bot's knowledge into another's answers.
    """
    k = k or settings.RETRIEVAL_TOP_K
    query_vec = embeddings.embed_query(question)
    return (
        db.query(Chunk)
        .join(KnowledgeSource, KnowledgeSource.id == Chunk.knowledge_source_id)
        .filter(
            KnowledgeSource.bot_id == bot.id,
            Chunk.organization_id == bot.organization_id,
            Chunk.embedding.isnot(None),
        )
        .order_by(Chunk.embedding.cosine_distance(query_vec))
        .limit(k)
        .all()
    )


def answer_question(db: Session, bot: Bot, question: str) -> str:
    """End-to-end: retrieve context, then generate a grounded answer."""
    chunks = retrieve(db, bot, question)
    if not chunks:
        return bot.fallback_message or "I don't have an answer for that yet."
    context = "\n\n---\n\n".join(c.content for c in chunks)
    return llm.answer(bot.system_prompt or "", context, question)
