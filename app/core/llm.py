"""Chat answer generation via OpenRouter (OpenAI-compatible API).

One API key reaches many providers/models (Claude, GPT, gpt-oss, Mistral, Gemma).
The model id is chosen from the platform fallback chain (see models_catalog). Keys
resolve through config_store (admin DB setting first, then env).
"""
from __future__ import annotations

import logging
import time

import httpx

from app.core import config_store

logger = logging.getLogger(__name__)

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


# A text model answers in seconds, but a vision model that isn't resident has to
# be paged in first — measured at ~70s cold vs ~3s warm for a 3B VLM on the
# self-hosted box. The old flat 45s timeout (times SDK retries) made a cold image
# turn impossible, so vision gets its own, much longer budget.
TEXT_TIMEOUT_SECONDS = 45.0
VISION_TIMEOUT_SECONDS = 180.0


def _client(timeout_seconds: float = TEXT_TIMEOUT_SECONDS, max_retries: int = 0, base_url: str | None = None):
    """Build the OpenAI-compatible client (bounded timeout so a hung model fails fast).

    `base_url` lets a caller point this call at a specific candidate's self-hosted
    Ollama server instead of the global OpenRouter endpoint; omit to use the
    platform default. max_retries defaults to 0: retrying the SAME slow/stuck
    endpoint just multiplies the wait (up to 3x with the SDK default) — the chat
    fallback chain (see answer_with_fallback) is our retry strategy, and it should
    move to the NEXT candidate quickly rather than hammer a struggling one.
    """
    from openai import OpenAI  # lazy import so the app boots without the SDK configured

    url = base_url or _base_url()
    # Self-hosted Ollama ignores the key but the OpenAI SDK requires a non-empty string.
    key = config_store.get("OPENROUTER_API_KEY") or ("ollama" if not _needs_key(url) else "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    return OpenAI(
        api_key=key,
        base_url=url,
        timeout=httpx.Timeout(timeout_seconds, connect=5.0),
        # Retrying a cold model load just multiplies an already long wait.
        max_retries=max_retries,
        default_headers={"X-Title": "AiTechSupport"},
    )


def _client_for(image_data_url: str | None, base_url: str | None = None):
    if image_data_url:
        return _client(VISION_TIMEOUT_SECONDS, max_retries=0, base_url=base_url)
    return _client(base_url=base_url)


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
    base_url: str | None = None,
) -> tuple[str, int]:
    """Generate a grounded answer. Returns (text, total_tokens) for usage metering."""
    resp = _client_for(image_data_url, base_url).chat.completions.create(
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
    base_url: str | None = None,
):
    """Stream a grounded answer. Yields {'type':'delta','text':...} per token chunk,
    then a terminal {'type':'final','text':<full>,'tokens':<total>} for persistence/metering.

    Ollama's OpenAI-compatible endpoint emits a final usage-only chunk (choices=[])
    with stream_options.include_usage — so token counts stay accurate when streaming.
    """
    stream = _client_for(image_data_url, base_url).chat.completions.create(
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


class AllCandidatesFailed(Exception):
    """Every candidate in a fallback chain errored; carries each (model, error)."""

    def __init__(self, errors: list[tuple[str, Exception]]):
        self.errors = errors
        detail = "; ".join(f"{model}: {err}" for model, err in errors)
        super().__init__(f"all {len(errors)} chat model candidate(s) failed: {detail}")


def answer_with_fallback(
    system_prompt: str,
    context: str,
    question: str,
    candidates: list[tuple[str, str | None]],
    image_data_url: str | None = None,
) -> tuple[str, int, str]:
    """Try each (model, base_url) candidate in order; return the first success as
    (text, tokens, model_used). Raises AllCandidatesFailed only if every candidate
    errors — the fallback chain (see models_catalog)."""
    errors: list[tuple[str, Exception]] = []
    for model, base_url in candidates:
        started = time.monotonic()
        try:
            text, tokens = answer(
                system_prompt, context, question, model=model,
                image_data_url=image_data_url, base_url=base_url,
            )
            logger.info("chat candidate %s answered in %.1fs", model, time.monotonic() - started)
            return text, tokens, model
        except Exception as e:  # noqa: BLE001 — try the next candidate
            logger.warning(
                "chat candidate %s failed after %.1fs, trying next: %s",
                model, time.monotonic() - started, e,
            )
            errors.append((model, e))
    raise AllCandidatesFailed(errors)


def answer_stream_with_fallback(
    system_prompt: str,
    context: str,
    question: str,
    candidates: list[tuple[str, str | None]],
    image_data_url: str | None = None,
):
    """Streaming twin of answer_with_fallback. Only falls back to the next
    candidate if the CURRENT one fails before yielding any delta (connection
    refused, model-not-found, rate-limited — all fail immediately). Once a delta
    has reached the caller the visitor may already be seeing it, so a mid-stream
    failure is re-raised rather than silently restarted on a different model.
    """
    errors: list[tuple[str, Exception]] = []
    for model, base_url in candidates:
        started = False
        t0 = time.monotonic()
        try:
            for ev in answer_stream(
                system_prompt, context, question, model=model,
                image_data_url=image_data_url, base_url=base_url,
            ):
                started = True
                yield ev
            logger.info("chat candidate %s streamed in %.1fs", model, time.monotonic() - t0)
            return
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "chat candidate %s failed after %.1fs (started=%s): %s",
                model, time.monotonic() - t0, started, e,
            )
            errors.append((model, e))
            if started:
                raise
    raise AllCandidatesFailed(errors)
