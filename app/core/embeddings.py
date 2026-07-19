"""Pluggable text embeddings.

- provider "ollama": self-hosted Ollama on the ai-server (e.g. bge-m3, 1024-dim,
                     multilingual). No API key; reached at settings.OLLAMA_BASE_URL.
- provider "voyage": Voyage AI (external). Requires VOYAGE_API_KEY.
- provider "fake":   deterministic, dependency-free hashing embedder for offline
                     dev/CI. It has NO real semantics (bag-of-words hashing) — it
                     only makes the ingest/retrieve pipeline runnable without a key.
                     Never use in production.

All providers return L2-normalized vectors of length settings.EMBEDDING_DIM, so
cosine distance in pgvector behaves consistently.
"""
from __future__ import annotations

import hashlib
import math

from app.core.settings import settings
from app.core import config_store


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def _fake_embed(text: str, dim: int) -> list[float]:
    """Deterministic bag-of-words hash into `dim` buckets. Dev/CI only."""
    vec = [0.0] * dim
    for token in text.lower().split():
        h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    return _l2_normalize(vec)


def _ollama_base_url() -> str:
    # admin DB setting first, then env/settings default
    return (config_store.get("OLLAMA_BASE_URL") or settings.OLLAMA_BASE_URL).rstrip("/")


def _ollama_embed(texts: list[str]) -> list[list[float]]:
    """Embed via the ai-server's Ollama /api/embed (batch). Model = EMBEDDING_MODEL."""
    import httpx  # lazy import so the app boots without the SDK configured

    resp = httpx.post(
        f"{_ollama_base_url()}/api/embed",
        json={"model": settings.EMBEDDING_MODEL, "input": texts},
        # Fast connect failure if the ai-server is unreachable; generous read
        # budget for a cold/CPU-offloaded embed model.
        timeout=httpx.Timeout(120.0, connect=5.0),
    )
    resp.raise_for_status()
    vectors = resp.json().get("embeddings")
    if not vectors or len(vectors) != len(texts):
        raise RuntimeError(
            f"Ollama returned {len(vectors) if vectors else 0} embeddings for "
            f"{len(texts)} inputs (model={settings.EMBEDDING_MODEL})."
        )
    dim = settings.EMBEDDING_DIM
    for v in vectors:
        if len(v) != dim:
            raise RuntimeError(
                f"Embedding dim mismatch: model '{settings.EMBEDDING_MODEL}' returned "
                f"{len(v)} but the schema expects {dim}. Pick a {dim}-dim model or migrate."
            )
    # Ollama does not guarantee normalized vectors; normalize for stable cosine search.
    return [_l2_normalize(v) for v in vectors]


def _voyage_key() -> str:
    # admin DB setting first, then env
    return config_store.get("VOYAGE_API_KEY")


def _voyage_embed(texts: list[str], input_type: str) -> list[list[float]]:
    import voyageai  # lazy import so the app boots without the SDK configured

    key = _voyage_key()
    if not key:
        raise RuntimeError("VOYAGE_API_KEY is not set (EMBEDDINGS_PROVIDER=voyage).")
    client = voyageai.Client(api_key=key)
    result = client.embed(texts, model=settings.EMBEDDING_MODEL, input_type=input_type)
    return result.embeddings


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed knowledge-base chunks for storage.

    Batched to stay under the provider's per-request text/token limits — a large
    source can produce thousands of chunks, which a single Voyage call rejects.
    """
    if not texts:
        return []
    if settings.EMBEDDINGS_PROVIDER == "fake":
        return [_fake_embed(t, settings.EMBEDDING_DIM) for t in texts]
    batch = max(1, settings.EMBED_BATCH_SIZE)
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        if settings.EMBEDDINGS_PROVIDER == "ollama":
            out.extend(_ollama_embed(chunk))
        else:
            out.extend(_voyage_embed(chunk, "document"))
    return out


def embed_query(text: str) -> list[float]:
    """Embed a user question for retrieval."""
    if settings.EMBEDDINGS_PROVIDER == "fake":
        return _fake_embed(text, settings.EMBEDDING_DIM)
    if settings.EMBEDDINGS_PROVIDER == "ollama":
        return _ollama_embed([text])[0]
    return _voyage_embed([text], "query")[0]


def is_configured() -> bool:
    """True when embeddings can actually run (fake/ollama need no key; voyage does)."""
    if settings.EMBEDDINGS_PROVIDER in ("fake", "ollama"):
        return True
    return bool(_voyage_key())
