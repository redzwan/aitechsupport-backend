"""Rate limiting + a global in-flight-inference cap for the public widget endpoint.

Redis-backed so the limits coordinate across uvicorn workers (and ideally across
apps sharing the GPU). Falls back to per-process in-memory counters when REDIS_URL
is unset or Redis is unreachable — weaker (per-worker), but it never hard-fails the
app. These are the REAL abuse boundary for the unauthenticated widget path; CORS is
not (Origin is forgeable off-browser).
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager

from app.core.settings import settings

logger = logging.getLogger(__name__)


class AtCapacity(RuntimeError):
    """Raised when the global in-flight-inference cap is already reached."""


_redis = None
_redis_tried = False


def _client():
    """Lazily connect to Redis once; None means use the in-memory fallback."""
    global _redis, _redis_tried
    if _redis_tried:
        return _redis
    _redis_tried = True
    url = settings.REDIS_URL
    if not url:
        logger.warning("REDIS_URL unset — widget limits use a per-process in-memory fallback.")
        return None
    try:
        import redis  # lazy import so the app boots without the package in dev
        c = redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        c.ping()
        _redis = c
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable (%s) — widget limits fall back to in-memory.", exc)
        _redis = None
    return _redis


# ---- per-process fallbacks ----
_mem_lock = threading.Lock()
_mem_hits: dict[str, list[float]] = {}
_mem_daily: dict[str, int] = {}
_mem_inflight = 0


def rate_limit_ok(key: str, limit: int, window: int = 60) -> bool:
    """True if `key` has had <= `limit` events in the last `window` seconds."""
    c = _client()
    if c is not None:
        try:
            k = f"wl:rl:{key}"
            n = c.incr(k)
            if n == 1:
                c.expire(k, window)
            return int(n) <= limit
        except Exception as exc:  # noqa: BLE001
            logger.warning("rate_limit redis error (%s); allowing.", exc)
            return True
    now = time.monotonic()
    with _mem_lock:
        hits = [t for t in _mem_hits.get(key, []) if now - t < window]
        hits.append(now)
        _mem_hits[key] = hits
        return len(hits) <= limit


def daily_incr(key: str) -> int:
    """Increment and return today's counter for `key` (auto-expires after ~1 day)."""
    c = _client()
    if c is not None:
        try:
            k = f"wl:day:{key}"
            n = c.incr(k)
            if n == 1:
                c.expire(k, 86400)
            return int(n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("daily_incr redis error (%s); allowing.", exc)
            return 1
    with _mem_lock:
        _mem_daily[key] = _mem_daily.get(key, 0) + 1
        return _mem_daily[key]


_INFLIGHT_KEY = "wl:inflight"


def acquire_slot(max_concurrency: int) -> str | None:
    """Take one in-flight-inference slot. Returns a token to pass to release_slot(),
    or None if the global cap is already reached. Usable across a streaming response
    (hold the token for the stream's lifetime, release in a finally)."""
    global _mem_inflight
    c = _client()
    if c is not None:
        try:
            n = c.incr(_INFLIGHT_KEY)
            c.expire(_INFLIGHT_KEY, 120)  # self-heal if a DECR is ever missed
            if int(n) > max_concurrency:
                c.decr(_INFLIGHT_KEY)
                return None
            return "redis"
        except Exception as exc:  # noqa: BLE001
            logger.warning("inflight redis error (%s); using in-memory.", exc)
    with _mem_lock:
        if _mem_inflight >= max_concurrency:
            return None
        _mem_inflight += 1
        return "mem"


def release_slot(token: str | None) -> None:
    global _mem_inflight
    if token == "redis":
        c = _client()
        if c is not None:
            try:
                c.decr(_INFLIGHT_KEY)
            except Exception:  # noqa: BLE001
                pass
    elif token == "mem":
        with _mem_lock:
            _mem_inflight = max(0, _mem_inflight - 1)


@contextmanager
def inference_slot(max_concurrency: int):
    """Bound simultaneous in-flight LLM calls (non-streaming path). Raises AtCapacity
    if the global cap is already reached."""
    token = acquire_slot(max_concurrency)
    if token is None:
        raise AtCapacity()
    try:
        yield
    finally:
        release_slot(token)
