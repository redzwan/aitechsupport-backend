"""Retrieval-Augmented answering: embed the question, pull the nearest KB chunks
for THIS bot via pgvector, then ask Claude to answer from that context.
"""
from __future__ import annotations

import base64
import logging

from sqlalchemy.orm import Session

from app.core import billing, embeddings, llm, models_catalog, storage
from app.core.settings import settings
from app.models.knowledge import Chunk, KnowledgeSource
from app.models.bot import Bot

logger = logging.getLogger(__name__)

# Used when a visitor sends a picture with no caption — retrieval has nothing to
# embed, so we ask the vision model to lead with what it can see.
DEFAULT_IMAGE_PROMPT = "The customer sent this image without a caption. What can you tell them about it?"


def _image_data_url(db: Session, image_key: str, image_mime: str | None) -> str | None:
    """Read the stored image and inline it as a base64 data URL.

    Inlined rather than handed to the model as a presigned link: the self-hosted
    model server has no guaranteed route to the object store, and a link could
    expire mid-generation. Returns None (never raises) if the object is gone, so
    a missing image degrades to a text-only answer.
    """
    try:
        raw = storage.get_bytes(db, image_key)
    except Exception:
        logger.warning("could not read chat image %s", image_key, exc_info=True)
        return None
    mime = image_mime or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


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


def _prepare(
    db: Session, bot: Bot, question: str, image_key: str | None, image_mime: str | None
):
    """Shared setup for both answer paths.

    Returns (context, question, candidates, image_data_url) or None when there is
    nothing to answer with — the caller then emits the fallback (0 tokens), which
    is the handoff signal. `candidates` is an ordered list of (model, base_url)
    to try in turn — the org's package fallback chain (see
    models_catalog.resolve_candidates).

    An image turn is answered even with NO retrieved context: the picture is the
    evidence, and handing off the moment the KB misses would defeat the feature.
    A turn carrying an image is also forced onto the vision model, since a text
    model would silently ignore the picture. Vision stays platform-wide (a single
    model, not a fallback chain) and always uses the ambient default endpoint.
    """
    # Vision may be disabled (no VISION_MODEL); then an image is ignored here and
    # the caller has already routed the turn to a human.
    use_vision = bool(image_key) and models_catalog.vision_enabled()
    image_data_url = _image_data_url(db, image_key, image_mime) if use_vision else None
    # Nothing to embed for a captionless image, and embedding "" is meaningless.
    chunks = retrieve(db, bot, question) if question.strip() else []
    if not chunks and image_data_url is None:
        return None
    context = "\n\n---\n\n".join(c.content for c in chunks)
    if image_data_url:
        candidates = [(models_catalog.vision_model(), None)]
        return context, (question.strip() or DEFAULT_IMAGE_PROMPT), candidates, image_data_url
    sub = billing.get_or_create_subscription(db, bot.organization_id)
    package = billing.package_for(db, sub.plan)
    return context, question, models_catalog.resolve_candidates(bot, package), None


def answer_question(
    db: Session,
    bot: Bot,
    question: str,
    image_key: str | None = None,
    image_mime: str | None = None,
) -> tuple[str, int]:
    """End-to-end: retrieve context, then generate a grounded answer.

    Returns (answer, tokens_used). Nothing to answer with -> fallback, 0 tokens.
    """
    prepared = _prepare(db, bot, question, image_key, image_mime)
    if prepared is None:
        return (bot.fallback_message or "I don't have an answer for that yet."), 0
    context, q, candidates, image_data_url = prepared
    text, tokens, _model_used = llm.answer_with_fallback(
        bot.system_prompt or "", context, q, candidates, image_data_url=image_data_url
    )
    return text, tokens


def answer_question_stream(
    db: Session,
    bot: Bot,
    question: str,
    image_key: str | None = None,
    image_mime: str | None = None,
):
    """Streaming twin of answer_question. Yields {'type':'delta'|'final', ...} events;
    the terminal 'final' carries the full text + tokens for persistence/metering.
    Nothing to answer with -> the fallback message as a single delta, 0 tokens.
    """
    prepared = _prepare(db, bot, question, image_key, image_mime)
    if prepared is None:
        fb = bot.fallback_message or "I don't have an answer for that yet."
        yield {"type": "delta", "text": fb}
        yield {"type": "final", "text": fb, "tokens": 0}
        return
    context, q, candidates, image_data_url = prepared
    yield from llm.answer_stream_with_fallback(
        bot.system_prompt or "", context, q, candidates, image_data_url=image_data_url
    )
