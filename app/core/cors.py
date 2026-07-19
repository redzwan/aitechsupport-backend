"""CORS for two audiences on one FastAPI app.

- Dashboard/API paths: the static allowlist, credentialed — unchanged behavior,
  delegated to Starlette's stock CORSMiddleware.
- Public widget paths (/api/v1/public/widget/{key}/...): per-bot dynamic Origin
  echo, credential-LESS. A short cache keeps preflights from hammering the DB.

Origin/CORS here is honest-browser embedding hygiene ONLY — it is not the abuse
boundary (Origin is trivially forged off-browser; see app/core/limits.py).
"""
from __future__ import annotations

import time

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.channel import Channel

_PUBLIC_PREFIX = settings.API_V1_STR + "/public/"
_CACHE_TTL = 30.0
_cache: dict[str, tuple[float, list[str]]] = {}


def _allowed_origins_for(public_key: str) -> list[str]:
    now = time.monotonic()
    hit = _cache.get(public_key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    origins: list[str] = []
    db = SessionLocal()
    try:
        ch = (
            db.query(Channel)
            .filter(Channel.public_key == public_key, Channel.kind == "widget")
            .first()
        )
        if ch and ch.is_active and ch.allowed_origins:
            origins = list(ch.allowed_origins)
    finally:
        db.close()
    _cache[public_key] = (now, origins)
    return origins


def _public_key_from_path(path: str) -> str | None:
    # /api/v1/public/widget/{key}/...
    parts = path[len(_PUBLIC_PREFIX):].split("/")
    if len(parts) >= 2 and parts[0] == "widget":
        return parts[1] or None
    return None


class WidgetCORSMiddleware:
    """Dispatch CORS by path: public widget paths get dynamic per-bot origin echo,
    everything else gets the stock static-allowlist credentialed CORS."""

    def __init__(self, app: ASGIApp, static_origins: list[str]):
        self.app = app
        self._stock = CORSMiddleware(
            app,
            allow_origins=static_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(_PUBLIC_PREFIX):
            await self._stock(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        origin = headers.get("origin")
        key = _public_key_from_path(scope["path"])
        allowed = bool(origin and key and origin in _allowed_origins_for(key))

        # Preflight — answer directly, never touch the app.
        if scope["method"] == "OPTIONS" and "access-control-request-method" in headers:
            resp_headers = [(b"vary", b"Origin")]
            if allowed:
                resp_headers += [
                    (b"access-control-allow-origin", origin.encode("latin-1")),
                    (b"access-control-allow-methods", b"POST, GET, OPTIONS"),
                    (b"access-control-allow-headers", b"content-type"),
                    (b"access-control-max-age", b"600"),
                ]
            await send({"type": "http.response.start", "status": 204, "headers": resp_headers})
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and allowed:
                hdrs = list(message.get("headers", []))
                hdrs.append((b"access-control-allow-origin", origin.encode("latin-1")))
                hdrs.append((b"vary", b"Origin"))
                message["headers"] = hdrs
            await send(message)

        await self.app(scope, receive, send_wrapper)
