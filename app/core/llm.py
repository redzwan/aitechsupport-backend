"""Thin wrappers around Claude (answers) and Voyage (embeddings).

Kept intentionally minimal — the RAG orchestration lives in app/core/rag.py.
"""
from __future__ import annotations

from typing import Optional

from app.core.settings import settings


def embed_texts(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Embed a batch of texts with Voyage AI. input_type: 'document' | 'query'."""
    import voyageai  # imported lazily so the app boots without the key during setup

    client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)
    result = client.embed(texts, model=settings.EMBEDDING_MODEL, input_type=input_type)
    return result.embeddings


def answer(system_prompt: str, context: str, question: str, model: Optional[str] = None) -> str:
    """Generate a grounded answer with Claude. Answers ONLY from `context`."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    system = (
        (system_prompt or "You are a helpful customer-support assistant.")
        + "\n\nAnswer ONLY using the CONTEXT below. If the answer is not in the "
        "context, say you don't know and offer to connect a human. Be concise."
    )
    msg = client.messages.create(
        model=model or settings.ANSWER_MODEL,
        max_tokens=1024,
        system=system,
        messages=[
            {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"}
        ],
    )
    return "".join(block.text for block in msg.content if block.type == "text")
