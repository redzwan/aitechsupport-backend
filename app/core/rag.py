"""Retrieval-Augmented answering: embed the question, pull the nearest KB chunks
for THIS bot via pgvector, then ask Claude to answer from that context.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core import embeddings, llm, models_catalog
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


def answer_question(db: Session, bot: Bot, question: str) -> tuple[str, int]:
    """End-to-end: retrieve context, then generate a grounded answer.

    Returns (answer, tokens_used). No context -> fallback message, 0 tokens.
    """
    chunks = retrieve(db, bot, question)
    if not chunks:
        return (bot.fallback_message or "I don't have an answer for that yet."), 0
    context = "\n\n---\n\n".join(c.content for c in chunks)
    model = models_catalog.resolve_for_bot(bot.chat_model)
    return llm.answer(bot.system_prompt or "", context, question, model=model)


def answer_question_stream(db: Session, bot: Bot, question: str):
    """Streaming twin of answer_question. Yields {'type':'delta'|'final', ...} events;
    the terminal 'final' carries the full text + tokens for persistence/metering.
    No context -> the fallback message as a single delta, 0 tokens.
    """
    chunks = retrieve(db, bot, question)
    if not chunks:
        fb = bot.fallback_message or "I don't have an answer for that yet."
        yield {"type": "delta", "text": fb}
        yield {"type": "final", "text": fb, "tokens": 0}
        return
    context = "\n\n---\n\n".join(c.content for c in chunks)
    model = models_catalog.resolve_for_bot(bot.chat_model)
    yield from llm.answer_stream(bot.system_prompt or "", context, question, model=model)
