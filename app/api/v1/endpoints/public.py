"""Public, JWT-less website-widget endpoints.

This is the system's only unauthenticated surface, in front of a finite GPU shared
with another app. Every request is bounded by: a per-key+IP rate limit, a global
in-flight-inference cap, a per-bot daily message cap, and the org token quota.
Tenant identity (organization_id) comes ONLY from the resolved widget Channel.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db, SessionLocal
from app.core import rag, embeddings, llm, billing, widget, limits
from app.core.settings import settings
from app.schemas.widget import PublicChatRequest, PublicChatResponse, WidgetPublicConfig

logger = logging.getLogger(__name__)
router = APIRouter()


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _client_ip(request: Request) -> str:
    """Real client IP behind nginx (first X-Forwarded-For hop), else the peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/widget/{public_key}/config", response_model=WidgetPublicConfig)
def widget_config(public_key: str, db: Session = Depends(get_db)):
    resolved = widget.resolve_widget(db, public_key)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    channel, _bot = resolved
    ap = {**widget.DEFAULT_APPEARANCE, **(channel.appearance or {})}
    return WidgetPublicConfig(**{k: ap[k] for k in WidgetPublicConfig.model_fields})


def _guard(public_key: str, request: Request, db: Session):
    """Shared pre-flight for the public chat paths: resolve the tenant + run every
    abuse/quota gate. Returns (channel, bot) or raises the appropriate HTTPException.
    Runs BEFORE any streaming starts, so these stay normal HTTP status codes."""
    resolved = widget.resolve_widget(db, public_key)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    channel, bot = resolved

    # 1) Per-key + IP rate limit (cheapest abuse gate first).
    ip = _client_ip(request)
    if not limits.rate_limit_ok(f"{public_key}:{ip}", settings.WIDGET_RATE_PER_MIN, 60):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.",
                            headers={"Retry-After": "60"})

    # 2) Config guard — clear 503 instead of a 500 if inference isn't wired.
    if not embeddings.is_configured() or not llm.is_configured():
        raise HTTPException(status_code=503, detail="Assistant temporarily unavailable.")

    # 3) Org token quota (a leaked key must not bypass metering).
    sub = billing.get_or_create_subscription(db, channel.organization_id)
    if not billing.has_quota(db, sub):
        raise HTTPException(status_code=402, detail="This assistant has reached its usage limit.")

    # 4) Per-bot daily cap — counted only once we're about to actually spend GPU.
    cap = channel.widget_daily_message_cap or settings.WIDGET_DAILY_CAP_DEFAULT
    if limits.daily_incr(public_key) > cap:
        raise HTTPException(status_code=429, detail="Daily message limit reached for this assistant.",
                            headers={"Retry-After": "3600"})
    return channel, bot


@router.post("/widget/{public_key}/chat", response_model=PublicChatResponse)
def widget_chat(
    public_key: str,
    payload: PublicChatRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Buffered (non-streaming) answer — kept as the fallback for the streaming path."""
    channel, bot = _guard(public_key, request, db)
    session_id = widget.clean_session_id(payload.session_id)

    # Generate under the global in-flight-inference cap so the widget can never
    # monopolize the shared GPU.
    try:
        with limits.inference_slot(settings.WIDGET_MAX_CONCURRENCY):
            answer, tokens = rag.answer_question(db, bot, payload.question)
    except limits.AtCapacity:
        raise HTTPException(status_code=429, detail="Busy right now — please retry shortly.",
                            headers={"Retry-After": "5"})
    except Exception:  # noqa: BLE001 — upstream embedding/LLM/network failure
        logger.exception("widget chat failed for bot %s", bot.id)
        raise HTTPException(status_code=502,
                            detail="The assistant is temporarily unavailable. Please try again.")

    if tokens:
        billing.record_usage(db, channel.organization_id, tokens)
    conv = widget.record_turn(db, channel, session_id, payload.question, answer, tokens)
    return PublicChatResponse(answer=answer, session_id=session_id, status=conv.status)


@router.post("/widget/{public_key}/chat/stream")
def widget_chat_stream(
    public_key: str,
    payload: PublicChatRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """SSE token streaming. Pre-flight gates use normal HTTP status; once the stream
    starts, everything (busy / errors / done) is a terminal in-band SSE event, since
    the HTTP status is committed the moment the first byte flushes."""
    # Gates run on the request session BEFORE we commit to a 200 stream.
    _guard(public_key, request, db)
    session_id = widget.clean_session_id(payload.session_id)
    question = payload.question

    def event_stream():
        # Hold one inference slot for the stream's whole lifetime (in-band 'busy' if none).
        token = limits.acquire_slot(settings.WIDGET_MAX_CONCURRENCY)
        if token is None:
            yield _sse({"type": "error", "detail": "busy"})
            return
        # Own DB session: the request's get_db session is closed before a streaming
        # body finishes, so retrieval + persistence must run on a fresh session.
        sdb = SessionLocal()
        org_id = None
        full_text = ""
        tokens = 0
        recorded = False
        try:
            resolved = widget.resolve_widget(sdb, public_key)
            if resolved is None:
                yield _sse({"type": "error", "detail": "not_found"})
                return
            channel, bot = resolved
            org_id = channel.organization_id
            yield _sse({"type": "start", "session_id": session_id})
            for ev in rag.answer_question_stream(sdb, bot, question):
                if ev["type"] == "delta":
                    yield _sse({"type": "delta", "text": ev["text"]})
                elif ev["type"] == "final":
                    full_text = ev["text"]
                    tokens = ev["tokens"]
            if tokens:
                billing.record_usage(sdb, org_id, tokens)
            conv = widget.record_turn(sdb, channel, session_id, question, full_text, tokens)
            recorded = True
            yield _sse({"type": "done", "session_id": session_id, "status": conv.status})
        except GeneratorExit:
            # Client disconnected mid-stream — fall through to finally (no more yields).
            raise
        except Exception:  # noqa: BLE001
            logger.exception("widget stream failed for key %s", public_key)
            yield _sse({"type": "error", "detail": "unavailable"})
        finally:
            # Meter + persist whatever was produced, even on disconnect, exactly once.
            if not recorded and full_text and org_id is not None:
                try:
                    billing.record_usage(sdb, org_id, tokens or max(1, len(full_text) // 4))
                    again = widget.resolve_widget(sdb, public_key)
                    if again is not None:
                        widget.record_turn(sdb, again[0], session_id, question, full_text, tokens)
                except Exception:  # noqa: BLE001
                    pass
            sdb.close()
            limits.release_slot(token)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
