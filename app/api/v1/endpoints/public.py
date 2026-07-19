"""Public, JWT-less website-widget endpoints.

This is the system's only unauthenticated surface, in front of a finite GPU shared
with another app. Every request is bounded by: a per-key+IP rate limit, a global
in-flight-inference cap, a per-bot daily message cap, and the org token quota.
Tenant identity (organization_id) comes ONLY from the resolved widget Channel.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core import rag, embeddings, llm, billing, widget, limits
from app.core.settings import settings
from app.schemas.widget import PublicChatRequest, PublicChatResponse, WidgetPublicConfig

logger = logging.getLogger(__name__)
router = APIRouter()


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


@router.post("/widget/{public_key}/chat", response_model=PublicChatResponse)
def widget_chat(
    public_key: str,
    payload: PublicChatRequest,
    request: Request,
    db: Session = Depends(get_db),
):
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

    session_id = widget.clean_session_id(payload.session_id)

    # 5) Generate under the global in-flight-inference cap so the widget can never
    #    monopolize the shared GPU.
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
