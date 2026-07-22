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


def _client():
    """Build the OpenAI-compatible client (bounded timeout so a hung model fails fast)."""
    from openai import OpenAI  # lazy import so the app boots without the SDK configured

    base_url = _base_url()
    # Self-hosted Ollama ignores the key but the OpenAI SDK requires a non-empty string.
    key = config_store.get("OPENROUTER_API_KEY") or ("ollama" if not _needs_key(base_url) else "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    return OpenAI(
        api_key=key,
        base_url=base_url,
        timeout=httpx.Timeout(45.0, connect=5.0),
        default_headers={"X-Title": "AiTechSupport"},
    )


def _build_system_vision(system_prompt: str) -> str:
    """Vision turns must NOT be restricted to the KB context — the picture itself is
    evidence, and the KB usually has nothing about it. Describe, then help."""
    return (
        (system_prompt or "You are a helpful customer-support assistant.")
        + "\n\nThe customer has attached an image. Describe what you can see that is "
        "relevant to their problem, then help them using the CONTEXT below where it "
        "applies. If you cannot tell from the image, say so plainly and offer to "
        "connect a human. Be concise."
    )


def _messages(
    system_prompt: str,
    context: str,
    question: str,
    image_data_url: str | None = None,
) -> list[dict]:
    """OpenAI-format messages. With an image the user turn becomes a parts array."""
    text = f"CONTEXT:\n{context}\n\nQUESTION: {question}"
    if not image_data_url:
        return [
            {"role": "system", "content": _build_system(system_prompt)},
            {"role": "user", "content": text},
        ]
    return [
        {"role": "system", "content": _build_system_vision(system_prompt)},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        },
    ]


# A rough floor for an image's prompt cost, used only when the provider reports no
# usage at all. Without it the chars/4 estimate would bill a picture as ~nothing.
IMAGE_TOKEN_ESTIMATE = 800


def _estimate_tokens(
    system_prompt: str,
    context: str,
    question: str,
    text: str,
    has_image: bool = False,
) -> int:
    """Fallback (~4 chars/token) when the provider reports no usage — keeps metering moving."""
    approx = len(_build_system(system_prompt)) + len(context) + len(question) + len(text)
    return max(1, approx // 4) + (IMAGE_TOKEN_ESTIMATE if has_image else 0)


def answer(
    system_prompt: str,
    context: str,
    question: str,
    model: str,
    image_data_url: str | None = None,
) -> tuple[str, int]:
    """Generate a grounded answer. Returns (text, total_tokens) for usage metering."""
    resp = _client().chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=_messages(system_prompt, context, question, image_data_url),
    )
    text = (resp.choices[0].message.content or "").strip()
    # `or 0` guards against usage present but total_tokens == None (some providers).
    tokens = (getattr(resp.usage, "total_tokens", 0) or 0) if resp.usage else 0
    if not tokens:
        tokens = _estimate_tokens(
            system_prompt, context, question, text, has_image=bool(image_data_url)
        )
    return text, tokens


def answer_stream(
    system_prompt: str,
    context: str,
    question: str,
    model: str,
    image_data_url: str | None = None,
):
    """Stream a grounded answer. Yields {'type':'delta','text':...} per token chunk,
    then a terminal {'type':'final','text':<full>,'tokens':<total>} for persistence/metering.

    Ollama's OpenAI-compatible endpoint emits a final usage-only chunk (choices=[])
    with stream_options.include_usage — so token counts stay accurate when streaming.
    """
    stream = _client().chat.completions.create(
        model=model,
        max_tokens=1024,
        stream=True,
        stream_options={"include_usage": True},
        messages=_messages(system_prompt, context, question, image_data_url),
    )
    parts: list[str] = []
    tokens = 0
    for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta
            piece = getattr(delta, "content", None) if delta else None
            if piece:
                parts.append(piece)
                yield {"type": "delta", "text": piece}
        usage = getattr(chunk, "usage", None)
        if usage:
            tokens = getattr(usage, "total_tokens", 0) or 0
    full = "".join(parts).strip()
    if not tokens:
        tokens = _estimate_tokens(
            system_prompt, context, question, full, has_image=bool(image_data_url)
        )
    yield {"type": "final", "text": full, "tokens": tokens}
