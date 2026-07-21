"""Object storage on an AIStor / MinIO (S3-compatible) endpoint.

Credentials live in config_store (admin panel), so a platform admin can point
AiTechSupport at their bucket without a redeploy — same pattern as the SMTP
settings. Objects (original KB uploads) are stored PRIVATELY; nothing is
public-read. Files are handed back to the dashboard via short-lived presigned
GET URLs (see presigned_url), never a guessable public link.

The MinIO client is built per call from the current config rather than cached in
a singleton, so an admin credential change takes effect immediately (config may
be read and written in different requests).
"""
from __future__ import annotations

import logging
from io import BytesIO
from datetime import timedelta

from minio import Minio
from sqlalchemy.orm import Session

from app.core import config_store
from app.core.settings import settings

logger = logging.getLogger(__name__)

# Chat image uploads live under this prefix so the 90-day expiry lifecycle rule
# can target them without ever touching knowledge-base objects (kb/...).
CHAT_IMAGE_PREFIX = "chat/"


def storage_config(db: Session | None = None) -> dict:
    """Resolve storage config (DB settings first, env fallback via config_store)."""
    g = config_store.get
    endpoint, scheme_secure = _split_endpoint(g("STORAGE_ENDPOINT") or settings.STORAGE_ENDPOINT)
    secure = _as_bool(g("STORAGE_SECURE"), settings.STORAGE_SECURE)
    # A scheme pasted into the endpoint wins over the flag, so an admin who types
    # https:// is never silently downgraded to plaintext by a stale secure=false.
    if scheme_secure is not None:
        secure = scheme_secure
    return {
        "endpoint": endpoint,
        "access_key": g("STORAGE_ACCESS_KEY") or settings.STORAGE_ACCESS_KEY,
        "secret_key": g("STORAGE_SECRET_KEY") or settings.STORAGE_SECRET_KEY,
        "bucket": g("STORAGE_BUCKET") or settings.STORAGE_BUCKET,
        "secure": secure,
        "enabled": _as_bool(g("STORAGE_ENABLED"), settings.STORAGE_ENABLED),
    }


def is_configured(db: Session | None = None) -> bool:
    """True when storage is enabled and all connection fields are present."""
    cfg = storage_config(db)
    return (
        cfg["enabled"]
        and bool(cfg["endpoint"])
        and bool(cfg["access_key"])
        and bool(cfg["secret_key"])
        and bool(cfg["bucket"])
    )


def _split_endpoint(raw: str) -> tuple[str, bool | None]:
    """Split host[:port] from an optional pasted scheme.

    MinIO wants host[:port] with no scheme (TLS is a separate flag), so strip any
    http(s):// prefix. Return whether the scheme implied TLS (True/False), or None
    when no scheme was given, so a pasted https:// can override the secure toggle
    instead of being silently discarded.
    """
    raw = (raw or "").strip()
    scheme_secure: bool | None = None
    for prefix, secure in (("https://", True), ("http://", False)):
        if raw.lower().startswith(prefix):
            scheme_secure = secure
            raw = raw[len(prefix):]
            break
    return raw.rstrip("/"), scheme_secure


def _as_bool(raw: str, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    return str(raw).strip().lower() in ("true", "1", "yes", "on")


def _safe_filename(name: str | None) -> str:
    """Basename with header-breaking characters removed (for Content-Disposition)."""
    if not name:
        return ""
    name = name.replace("\\", "/").split("/")[-1]
    # Drop quotes/backslashes and control chars (incl. CR/LF) to prevent header injection.
    return "".join(c for c in name if c >= " " and c not in '"\\').strip()[:200]


def _client(cfg: dict) -> Minio:
    return Minio(
        cfg["endpoint"],
        access_key=cfg["access_key"],
        secret_key=cfg["secret_key"],
        secure=cfg["secure"],
    )


def put_bytes(
    db: Session,
    data: bytes,
    object_name: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Store bytes at object_name in the configured bucket; return the object key.

    Raises RuntimeError if storage isn't configured and S3Error on transport
    failure — callers on a non-critical path should catch and continue.
    """
    cfg = storage_config(db)
    if not is_configured(db):
        raise RuntimeError("Object storage is not configured")
    client = _client(cfg)
    client.put_object(
        cfg["bucket"],
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type or "application/octet-stream",
    )
    logger.info("stored object %s (%d bytes) in %s", object_name, len(data), cfg["bucket"])
    return object_name


def presigned_url(
    db: Session,
    object_name: str,
    expiry: int | None = None,
    download_name: str | None = None,
) -> str:
    """Short-lived presigned GET URL for a private object.

    Forces `Content-Disposition: attachment` so the browser downloads the file
    instead of rendering it inline — a stored .html/.svg with a client-declared
    content type can't execute script on the storage origin. download_name sets
    the suggested filename.
    """
    cfg = storage_config(db)
    if not is_configured(db):
        raise RuntimeError("Object storage is not configured")
    seconds = expiry or settings.STORAGE_URL_EXPIRY
    safe = _safe_filename(download_name)
    disposition = f'attachment; filename="{safe}"' if safe else "attachment"
    return _client(cfg).presigned_get_object(
        cfg["bucket"],
        object_name,
        expires=timedelta(seconds=seconds),
        response_headers={"response-content-disposition": disposition},
    )


# Chat images must render in an <img>, so they get `inline` instead of the
# `attachment` above. Kept to a strict raster allowlist: SVG is intentionally
# excluded because inline SVG on the storage origin can execute script.
INLINE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def inline_image_url(
    db: Session,
    object_name: str,
    content_type: str | None = None,
    expiry: int | None = None,
) -> str:
    """Short-lived presigned GET URL that renders inline in an <img> tag.

    Only for raster images we control the type of (see INLINE_IMAGE_TYPES); any
    other content type falls back to the download-forcing presigned_url.
    """
    ctype = (content_type or "").lower()
    if ctype not in INLINE_IMAGE_TYPES:
        return presigned_url(db, object_name, expiry=expiry)
    cfg = storage_config(db)
    if not is_configured(db):
        raise RuntimeError("Object storage is not configured")
    seconds = expiry or settings.STORAGE_URL_EXPIRY
    return _client(cfg).presigned_get_object(
        cfg["bucket"],
        object_name,
        expires=timedelta(seconds=seconds),
        response_headers={
            "response-content-disposition": "inline",
            "response-content-type": ctype,
        },
    )


def get_bytes(db: Session, object_name: str) -> bytes:
    """Read an object back (used to inline an image for the vision model)."""
    cfg = storage_config(db)
    if not is_configured(db):
        raise RuntimeError("Object storage is not configured")
    resp = None
    try:
        resp = _client(cfg).get_object(cfg["bucket"], object_name)
        return resp.read()
    finally:
        if resp is not None:
            resp.close()
            resp.release_conn()


def apply_chat_image_lifecycle(db: Session, days: int = 90) -> None:
    """Expire chat image uploads after `days` via a bucket lifecycle rule.

    Cheaper and more reliable than a cron: the storage layer enforces it. Scoped
    to the CHAT_IMAGE_PREFIX so knowledge-base uploads are never touched.
    """
    from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration
    from minio.commonconfig import ENABLED, Filter

    cfg = storage_config(db)
    if not is_configured(db):
        raise RuntimeError("Object storage is not configured")
    client = _client(cfg)
    rule = Rule(
        ENABLED,
        rule_id="ats-chat-images-expire",
        rule_filter=Filter(prefix=CHAT_IMAGE_PREFIX),
        expiration=Expiration(days=days),
    )
    # Preserve any unrelated rules the operator already set on the bucket.
    keep: list = []
    try:
        existing = client.get_bucket_lifecycle(cfg["bucket"])
        if existing and existing.rules:
            keep = [r for r in existing.rules if r.rule_id != "ats-chat-images-expire"]
    except Exception:  # no lifecycle configured yet
        keep = []
    client.set_bucket_lifecycle(cfg["bucket"], LifecycleConfig(keep + [rule]))


def remove(db: Session, object_name: str) -> bool:
    """Best-effort delete of a stored object. Never raises."""
    if not object_name or not is_configured(db):
        return False
    try:
        cfg = storage_config(db)
        _client(cfg).remove_object(cfg["bucket"], object_name)
        logger.info("removed object %s", object_name)
        return True
    except Exception as exc:  # noqa: BLE001 — best-effort cleanup; a delete must never fail on this
        logger.warning("failed to remove object %s: %s", object_name, exc)
        return False


def test_connection(db: Session) -> None:
    """Verify the credentials reach the bucket. Raises on any failure.

    Does NOT create the bucket — the operator creates it out-of-band; we only
    confirm it exists and is reachable with the configured keys.
    """
    cfg = storage_config(db)
    missing = [k for k in ("endpoint", "access_key", "secret_key", "bucket") if not cfg[k]]
    if missing:
        raise RuntimeError(f"Missing storage config: {', '.join(missing)}")
    exists = _client(cfg).bucket_exists(cfg["bucket"])
    if not exists:
        raise RuntimeError(
            f"Connected, but bucket '{cfg['bucket']}' was not found on {cfg['endpoint']}"
        )
