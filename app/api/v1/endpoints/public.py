"""Public, JWT-less website-widget endpoints.

This is the system's only unauthenticated surface, in front of a finite GPU shared
with another app. Every request is bounded by: a per-key+IP rate limit, a global
in-flight-inference cap, a per-bot daily message cap, and the org token quota.
Tenant identity (organization_id) comes ONLY from the resolved widget Channel.
"""
import html
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db, SessionLocal
from app.core import rag, embeddings, llm, billing, widget, limits, email
from app.core.settings import settings
from app.models.user import User
from app.models.conversation import Message
from app.schemas.widget import (
    PublicChatRequest,
    PublicChatResponse,
    WidgetPublicConfig,
    HandoffRequest,
    HandoffResponse,
    VisitorMessagesOut,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _notify_tenant(org_id: int, bot_name: str, name: str, contact_email: str, message: str) -> None:
    """Best-effort email to the org's active users that a visitor wants a human."""
    db = SessionLocal()
    try:
        if not email.is_configured(db):
            logger.info("handoff email skipped (SMTP off) for org %s", org_id)
            return
        recipients = [
            u.email for u in db.query(User).filter(
                User.organization_id == org_id, User.is_active.is_(True)
            ).all()
        ]
        subject = f"New chat lead for {bot_name}"
        body_html = (
            f"<p>A website visitor asked to talk to a human on <b>{html.escape(bot_name)}</b>.</p>"
            f"<p><b>Name:</b> {html.escape(name)}<br>"
            f"<b>Email:</b> {html.escape(contact_email)}</p>"
            f"<p><b>Message:</b><br>{html.escape(message or '(none)')}</p>"
            f"<p>Reply to them directly, or view it in your dashboard inbox.</p>"
        )
        for to in recipients:
            try:
                email.send(db, to, subject, body_html)
            except Exception:  # noqa: BLE001 — one bad address shouldn't drop the rest
                logger.warning("handoff email to %s failed", to, exc_info=True)
    finally:
        db.close()


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


def _resolve_and_ratelimit(public_key: str, request: Request, db: Session):
    """Resolve the tenant widget + the cheapest abuse gate. Runs before any streaming."""
    resolved = widget.resolve_widget(db, public_key)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    channel, bot = resolved
    ip = _client_ip(request)
    if not limits.rate_limit_ok(f"{public_key}:{ip}", settings.WIDGET_RATE_PER_MIN, 60):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.",
                            headers={"Retry-After": "60"})
    return channel, bot


def _inference_gates(public_key: str, channel, db: Session) -> None:
    """Guards that only apply when we're about to spend GPU: config, quota, daily cap."""
    if not embeddings.is_configured() or not llm.is_configured():
        raise HTTPException(status_code=503, detail="Assistant temporarily unavailable.")
    sub = billing.get_or_create_subscription(db, channel.organization_id)
    if not billing.has_quota(db, sub):
        raise HTTPException(status_code=402, detail="This assistant has reached its usage limit.")
    cap = channel.widget_daily_message_cap or settings.WIDGET_DAILY_CAP_DEFAULT
    if limits.daily_incr(public_key) > cap:
        raise HTTPException(status_code=429, detail="Daily message limit reached for this assistant.",
                            headers={"Retry-After": "3600"})


def _bot_paused(db: Session, channel, session_id: str):
    """If a human owns this session's conversation, return its status (bot is paused),
    else None. When paused, the widget's chat must NOT spend GPU or bill."""
    conv = widget.find_conversation(db, channel, session_id)
    if conv and conv.status in ("needs_human", "human"):
        return conv.status
    return None


@router.post("/widget/{public_key}/chat", response_model=PublicChatResponse)
def widget_chat(
    public_key: str,
    payload: PublicChatRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Buffered (non-streaming) answer — kept as the fallback for the streaming path."""
    channel, bot = _resolve_and_ratelimit(public_key, request, db)
    session_id = widget.clean_session_id(payload.session_id)

    # Bot-pause: a human owns this conversation -> store the visitor turn, no inference.
    paused = _bot_paused(db, channel, session_id)
    if paused:
        widget.record_user_message(db, channel, session_id, payload.question)
        return PublicChatResponse(answer="", session_id=session_id, status=paused, handoff=True)

    _inference_gates(public_key, channel, db)

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
    # tokens == 0 means the no-context fallback fired -> suggest a human.
    return PublicChatResponse(answer=answer, session_id=session_id, status=conv.status,
                              handoff=(tokens == 0))


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
    channel, _bot = _resolve_and_ratelimit(public_key, request, db)
    session_id = widget.clean_session_id(payload.session_id)
    question = payload.question

    # Bot-pause: a human owns this conversation -> store the visitor turn + a terminal
    # 'done' event (no inference), so the widget flips to polling for agent replies.
    paused = _bot_paused(db, channel, session_id)
    if paused:
        widget.record_user_message(db, channel, session_id, question)

        def paused_stream():
            yield _sse({"type": "done", "session_id": session_id, "status": paused, "handoff": True})

        return StreamingResponse(paused_stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    _inference_gates(public_key, channel, db)

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
            yield _sse({"type": "done", "session_id": session_id, "status": conv.status,
                        "handoff": (tokens == 0)})
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


@router.post("/widget/{public_key}/handoff", response_model=HandoffResponse)
def widget_handoff(
    public_key: str,
    payload: HandoffRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Lead-capture: a visitor asks for a human. Flags their conversation needs_human,
    stores their contact, and emails the tenant (best-effort, off the request path)."""
    resolved = widget.resolve_widget(db, public_key)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    channel, bot = resolved

    ip = _client_ip(request)
    if not limits.rate_limit_ok(f"{public_key}:{ip}:handoff", settings.WIDGET_RATE_PER_MIN, 60):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.",
                            headers={"Retry-After": "60"})

    session_id = widget.clean_session_id(payload.session_id)
    conv = widget.mark_handoff(db, channel, session_id, payload.name, payload.email, payload.message)
    background.add_task(_notify_tenant, channel.organization_id, bot.name,
                        payload.name, payload.email, payload.message or "")
    return HandoffResponse(ok=True, status=conv.status)


@router.get("/widget/{public_key}/conversation/{session_id}/messages", response_model=VisitorMessagesOut)
def widget_conversation_messages(
    public_key: str,
    session_id: str,
    request: Request,
    after: int = 0,
    db: Session = Depends(get_db),
):
    """Visitor poll for live human replies: agent messages (role='agent') with id>after,
    plus the conversation status. Scoped STRICTLY to this widget's channel + this session —
    never a client-supplied conversation id — so one visitor can't read another's thread."""
    resolved = widget.resolve_widget(db, public_key)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    channel, _bot = resolved
    ip = _client_ip(request)
    if not limits.rate_limit_ok(f"{public_key}:{ip}:poll", settings.WIDGET_RATE_PER_MIN * 6, 60):
        raise HTTPException(status_code=429, detail="Too many requests.", headers={"Retry-After": "10"})
    conv = widget.find_conversation(db, channel, widget.clean_session_id(session_id))
    if conv is None:
        return VisitorMessagesOut(status="bot", messages=[])
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id, Message.role == "agent", Message.id > max(0, after))
        .order_by(Message.id.asc())
        .limit(100)
        .all()
    )
    return VisitorMessagesOut(status=conv.status, messages=msgs)
