"""Claude answer generation. Embeddings live in app/core/embeddings.py; RAG
orchestration lives in app/core/rag.py.
"""
from __future__ import annotations

from typing import Optional

from app.core.settings import settings


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
