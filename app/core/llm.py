"""Chat answer generation via OpenRouter (OpenAI-compatible API).

One API key reaches many providers/models (Claude, GPT, gpt-oss, Mistral, Gemma).
The model id is chosen per bot (see models_catalog). Keys resolve through
config_store (admin DB setting first, then env).
"""
from __future__ import annotations

import httpx

from app.core import config_store

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def _base_url() -> str:
    return config_store.get("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL


def _needs_key(base_url: str) -> bool:
    """External gateways (OpenRouter) need a key; a self-hosted endpoint (Ollama) does not."""
    return "openrouter.ai" in base_url


def is_configured() -> bool:
    base_url = _base_url()
    if not _needs_key(base_url):
        return True  # local/self-hosted endpoint (e.g. Ollama on the ai-server)
    return bool(config_store.get("OPENROUTER_API_KEY"))


def _build_system(system_prompt: str) -> str:
    return (
        (system_prompt or "You are a helpful customer-support assistant.")
        + "\n\nAnswer ONLY using the CONTEXT below. If the answer is not in the "
        "context, say you don't know and offer to connect a human. Be concise."
    )


def answer(system_prompt: str, context: str, question: str, model: str) -> tuple[str, int]:
    """Generate a grounded answer. Returns (text, total_tokens) for usage metering."""
    from openai import OpenAI  # lazy import so the app boots without the SDK configured

    base_url = _base_url()
    # Self-hosted Ollama ignores the key but the OpenAI SDK requires a non-empty string.
    key = config_store.get("OPENROUTER_API_KEY") or ("ollama" if not _needs_key(base_url) else "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    # Bounded timeout so a slow/hung self-hosted model fails deterministically
    # (well within nginx's proxy window) instead of tying up the worker to the
    # SDK default (~600s) and billing tokens for an answer the client never gets.
    client = OpenAI(
        api_key=key,
        base_url=base_url,
        timeout=httpx.Timeout(45.0, connect=5.0),
        default_headers={"X-Title": "AiTechSupport"},
    )
    resp = client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": _build_system(system_prompt)},
            {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"},
        ],
    )
    text = (resp.choices[0].message.content or "").strip()
    # `or 0` guards against usage present but total_tokens == None (some providers).
    tokens = (getattr(resp.usage, "total_tokens", 0) or 0) if resp.usage else 0
    if not tokens:
        # Provider didn't report usage — estimate (~4 chars/token) so metering still advances.
        approx = len(_build_system(system_prompt)) + len(context) + len(question) + len(text)
        tokens = max(1, approx // 4)
    return text, tokens
