"""Pluggable text embeddings.

- provider "voyage": Voyage AI (production). Requires VOYAGE_API_KEY.
- provider "fake":   deterministic, dependency-free hashing embedder for offline
                     dev/CI. It has NO real semantics (bag-of-words hashing) — it
                     only makes the ingest/retrieve pipeline runnable without a key.
                     Never use in production.

Both return L2-normalized vectors of length settings.EMBEDDING_DIM, so cosine
distance in pgvector behaves consistently.
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
        out.extend(_voyage_embed(texts[i : i + batch], "document"))
    return out


def embed_query(text: str) -> list[float]:
    """Embed a user question for retrieval."""
    if settings.EMBEDDINGS_PROVIDER == "fake":
        return _fake_embed(text, settings.EMBEDDING_DIM)
    return _voyage_embed([text], "query")[0]


def is_configured() -> bool:
    """True when embeddings can actually run (fake always can; voyage needs a key)."""
    if settings.EMBEDDINGS_PROVIDER == "fake":
        return True
    return bool(_voyage_key())
