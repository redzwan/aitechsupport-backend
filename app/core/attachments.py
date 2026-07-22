"""Chat image attachments: validation, object keys, and viewable URLs.

Visitor and agent uploads share one shape: bytes are validated by MAGIC BYTES
(never the client-declared content type), stored privately under
`storage.CHAT_IMAGE_PREFIX`, and handed back as short-lived presigned inline
URLs. The object key embeds org/bot/session so a key can be proven to belong to
the visitor presenting it — otherwise anyone could attach another tenant's
image by guessing a key.
"""
from __future__ import annotations

import hashlib
import time
import uuid

from sqlalchemy.orm import Session

from app.core import storage

# Client-declared type is ignored; this maps the SNIFFED type to a file extension.
ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def sniff_image_mime(data: bytes) -> str | None:
    """Real image type from magic bytes, or None if this isn't a supported image.

    SVG is deliberately unsupported: it's XML that can carry script, and we serve
    these inline.
    """
    for prefix, mime in _MAGIC:
        if data.startswith(prefix):
            return mime
    # WEBP: "RIFF" <4-byte size> "WEBP"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _session_bucket(session_id: str) -> str:
    """Short, non-reversible fingerprint of the visitor session for the key path."""
    return hashlib.sha256((session_id or "").encode()).hexdigest()[:16]


def build_key(org_id: int, bot_id: int, session_id: str, mime: str) -> str:
    ext = ALLOWED_IMAGE_TYPES.get(mime, "bin")
    return (
        f"{storage.CHAT_IMAGE_PREFIX}{org_id}/{bot_id}/"
        f"{_session_bucket(session_id)}/{uuid.uuid4().hex}.{ext}"
    )


def owns_key(key: str | None, org_id: int, bot_id: int, session_id: str) -> bool:
    """True only if `key` was uploaded by this session, on this bot, in this org."""
    if not key:
        return False
    expected = f"{storage.CHAT_IMAGE_PREFIX}{org_id}/{bot_id}/{_session_bucket(session_id)}/"
    return key.startswith(expected)


def agent_key(org_id: int, bot_id: int, conversation_id: int, mime: str) -> str:
    """Key for an image an agent sends into a conversation (same expiry prefix)."""
    ext = ALLOWED_IMAGE_TYPES.get(mime, "bin")
    return (
        f"{storage.CHAT_IMAGE_PREFIX}{org_id}/{bot_id}/"
        f"agent/{conversation_id}/{uuid.uuid4().hex}.{ext}"
    )


def owns_agent_key(key: str | None, org_id: int, bot_id: int, conversation_id: int) -> bool:
    """True only if `key` was uploaded by an agent into THIS conversation."""
    if not key:
        return False
    expected = f"{storage.CHAT_IMAGE_PREFIX}{org_id}/{bot_id}/agent/{conversation_id}/"
    return key.startswith(expected)


# Presigning is deterministic per call only in its inputs — the signature embeds
# the current time, so a fresh URL is produced every time. Clients poll the
# thread every ~4s, so returning a new URL each poll would make them re-download
# every image continuously. Hand back the SAME url for REUSE_SECONDS instead, so
# the browser / Image.network cache actually works.
_URL_SIGN_SECONDS = 900   # how long the presigned URL stays valid
_URL_REUSE_SECONDS = 600  # how long we keep handing out the same one
_URL_CACHE_MAX = 2000

_url_cache: dict[str, tuple[str, float]] = {}


def _prune_url_cache(now: float) -> None:
    for k, (_, exp) in list(_url_cache.items()):
        if exp <= now:
            del _url_cache[k]
    if len(_url_cache) > _URL_CACHE_MAX:  # pathological growth guard
        for k in list(_url_cache)[: len(_url_cache) - _URL_CACHE_MAX]:
            del _url_cache[k]


def view_url(db: Session, key: str | None, mime: str | None) -> str | None:
    """Inline URL for an image, stable for ~10 minutes so clients can cache it.

    Returns None if unset / expired / storage unavailable — never raises, since a
    missing image must degrade to a placeholder rather than break a whole
    conversation from loading.
    """
    if not key:
        return None
    now = time.time()
    cached = _url_cache.get(key)
    if cached is not None and cached[1] > now:
        return cached[0]
    try:
        url = storage.inline_image_url(db, key, mime, expiry=_URL_SIGN_SECONDS)
    except Exception:
        return None
    # Reused for less than it's signed for, so a URL handed out at the last
    # moment still has several minutes of validity left.
    _url_cache[key] = (url, now + _URL_REUSE_SECONDS)
    _prune_url_cache(now)
    return url
