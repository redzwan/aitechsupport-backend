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


def view_url(db: Session, key: str | None, mime: str | None) -> str | None:
    """Short-lived inline URL, or None if unset / expired / storage unavailable.

    Never raises: a missing image must degrade to a placeholder, not break a
    whole conversation from loading.
    """
    if not key:
        return None
    try:
        return storage.inline_image_url(db, key, mime)
    except Exception:
        return None
