import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user, get_agent_user
from app.core import rag, embeddings, llm, models_catalog, billing, widget, analytics
from app.core.settings import settings
from app.models.user import User
from app.models.bot import Bot
from app.models.channel import Channel
from app.models.conversation import Conversation, Message
from app.schemas.bot import BotCreate, BotOut, ChatRequest, ChatResponse
from app.schemas.setting import ModelOption
from app.schemas.widget import (
    WidgetConfigOut,
    WidgetConfigUpdate,
    ConversationOut,
    ConversationMessageOut,
    ConversationStatusUpdate,
    AgentReplyRequest,
    WidgetAnalyticsOut,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/models", response_model=list[ModelOption])
def list_models(user: User = Depends(get_current_user)):
    """Suggested chat models for a bot's model dropdown (any authenticated user)."""
    return models_catalog.CHAT_MODELS


@router.get("", response_model=list[BotOut])
def list_bots(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Bot).filter(Bot.organization_id == user.organization_id).all()


@router.post("", response_model=BotOut, status_code=201)
def create_bot(payload: BotCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Enforce the plan's bot limit. A missing package row is treated as the most
    # restrictive (1 bot) rather than fail-open.
    sub = billing.get_or_create_subscription(db, user.organization_id)
    pkg = billing.package_for(db, sub.plan)
    max_bots = pkg.max_bots if pkg is not None else 1
    current = db.query(Bot).filter(Bot.organization_id == user.organization_id).count()
    if current >= max_bots:
        plan_name = pkg.name if pkg is not None else sub.plan
        raise HTTPException(
            status_code=402,
            detail=f"Your {plan_name} plan allows {max_bots} bot(s). Upgrade to add more.",
        )
    bot = Bot(organization_id=user.organization_id, **payload.model_dump(exclude_none=True))
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


def _get_owned_bot(bot_id: int, db: Session, user: User) -> Bot:
    bot = (
        db.query(Bot)
        .filter(Bot.id == bot_id, Bot.organization_id == user.organization_id)
        .first()
    )
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.post("/{bot_id}/chat", response_model=ChatResponse)
def chat(
    bot_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dashboard test harness — ask the bot a question through the RAG engine."""
    bot = _get_owned_bot(bot_id, db, user)
    # RAG needs embeddings (retrieve) AND a chat model via OpenRouter (generate).
    # Surface a clear 503 instead of a 500 when either isn't configured yet.
    if not embeddings.is_configured() or not llm.is_configured():
        raise HTTPException(
            status_code=503,
            detail="LLM not configured: set OPENROUTER_API_KEY and VOYAGE_API_KEY "
            "(or EMBEDDINGS_PROVIDER=fake for dev).",
        )
    # Enforce the monthly token quota before spending more.
    sub = billing.get_or_create_subscription(db, user.organization_id)
    if not billing.has_quota(db, sub):
        raise HTTPException(
            status_code=402,
            detail="Monthly token quota reached. Upgrade your plan to keep chatting.",
        )
    try:
        answer, tokens = rag.answer_question(db, bot, payload.question)
    except Exception:  # noqa: BLE001 — upstream embedding/LLM/network failure
        logger.exception("chat failed for bot %s", bot_id)
        raise HTTPException(
            status_code=502,
            detail="The assistant is temporarily unavailable. Please try again.",
        )
    if tokens:
        billing.record_usage(db, user.organization_id, tokens)
    return ChatResponse(answer=answer)


# ===== Website widget config (JWT, org-scoped) =====

def _widget_out(ch: Channel) -> WidgetConfigOut:
    src = settings.WIDGET_SRC_URL
    snippet = f'<script src="{src}" data-public-key="{ch.public_key}" defer></script>'
    return WidgetConfigOut(
        enabled=bool(ch.is_active),
        public_key=ch.public_key,
        allowed_origins=list(ch.allowed_origins or []),
        appearance={**widget.DEFAULT_APPEARANCE, **(ch.appearance or {})},
        daily_message_cap=ch.widget_daily_message_cap,
        src_url=src,
        snippet=snippet,
    )


@router.get("/{bot_id}/widget", response_model=WidgetConfigOut)
def get_widget(bot_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Widget config for this bot (find-or-creates a disabled widget channel)."""
    bot = _get_owned_bot(bot_id, db, user)
    return _widget_out(widget.get_or_create_widget_channel(db, bot))


@router.put("/{bot_id}/widget", response_model=WidgetConfigOut)
def update_widget(
    bot_id: int,
    payload: WidgetConfigUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update widget config. Origins are normalized/validated; unknown appearance keys dropped."""
    bot = _get_owned_bot(bot_id, db, user)
    ch = widget.get_or_create_widget_channel(db, bot)
    if payload.enabled is not None:
        ch.is_active = payload.enabled
    if payload.allowed_origins is not None:
        ch.allowed_origins = widget.validate_origins(payload.allowed_origins)
    if payload.appearance is not None:
        merged = {**widget.DEFAULT_APPEARANCE, **(ch.appearance or {})}
        for k, v in payload.appearance.items():
            if k in widget.DEFAULT_APPEARANCE and isinstance(v, str):
                merged[k] = v[:200]
        ch.appearance = merged
    if payload.daily_message_cap is not None:
        ch.widget_daily_message_cap = max(0, payload.daily_message_cap) or None
    db.commit()
    db.refresh(ch)
    return _widget_out(ch)


@router.post("/{bot_id}/widget/rotate-key", response_model=WidgetConfigOut)
def rotate_widget_key(bot_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Mint a new public_key (invalidates already-pasted snippets)."""
    bot = _get_owned_bot(bot_id, db, user)
    ch = widget.get_or_create_widget_channel(db, bot)
    ch.public_key = widget.gen_public_key()
    db.commit()
    db.refresh(ch)
    return _widget_out(ch)


# ===== Conversation inbox (JWT, org + bot scoped) =====

def _conv_out(conv: Conversation, message_count: int, channel_kind: str | None,
              assignee_name: str | None = None) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        status=conv.status,
        channel_kind=channel_kind,
        contact_name=conv.contact_name,
        contact_email=conv.contact_email,
        needs_human_at=conv.needs_human_at,
        assigned_user_id=conv.assigned_user_id,
        assignee_name=assignee_name,
        last_message_at=conv.last_message_at,
        created_at=conv.created_at,
        message_count=message_count,
    )


def _conv_out_full(conv: Conversation, db: Session, bot: Bot) -> ConversationOut:
    """Build a ConversationOut for a single conversation (message count + assignee name)."""
    mc = db.query(func.count(Message.id)).filter(Message.conversation_id == conv.id).scalar() or 0
    kinds = {c.id: c.kind for c in db.query(Channel).filter(Channel.bot_id == bot.id).all()}
    name = None
    if conv.assigned_user_id:
        u = db.query(User).filter(User.id == conv.assigned_user_id).first()
        name = (u.full_name or u.email) if u else None
    return _conv_out(conv, int(mc), kinds.get(conv.channel_id), name)


def _owned_conversation(bot: Bot, conv_id: int, db: Session) -> Conversation:
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == conv_id,
            Conversation.bot_id == bot.id,
            Conversation.organization_id == bot.organization_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.get("/{bot_id}/conversations", response_model=list[ConversationOut])
def list_conversations(
    bot_id: int,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Conversations for a bot (newest first). Filter by status (e.g. needs_human)."""
    bot = _get_owned_bot(bot_id, db, user)
    q = db.query(Conversation).filter(
        Conversation.bot_id == bot.id,
        Conversation.organization_id == user.organization_id,
    )
    if status:
        q = q.filter(Conversation.status == status)
    convs = q.order_by(Conversation.last_message_at.desc()).limit(200).all()
    if not convs:
        return []
    ids = [c.id for c in convs]
    counts = dict(
        db.query(Message.conversation_id, func.count(Message.id))
        .filter(Message.conversation_id.in_(ids))
        .group_by(Message.conversation_id)
        .all()
    )
    kinds = {c.id: c.kind for c in db.query(Channel).filter(Channel.bot_id == bot.id).all()}
    assignee_ids = {c.assigned_user_id for c in convs if c.assigned_user_id}
    names = {}
    if assignee_ids:
        for u in db.query(User).filter(User.id.in_(assignee_ids)).all():
            names[u.id] = u.full_name or u.email
    return [_conv_out(c, counts.get(c.id, 0), kinds.get(c.channel_id), names.get(c.assigned_user_id)) for c in convs]


@router.get("/{bot_id}/conversations/{conv_id}/messages", response_model=list[ConversationMessageOut])
def conversation_messages(
    bot_id: int,
    conv_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bot = _get_owned_bot(bot_id, db, user)
    conv = _owned_conversation(bot, conv_id, db)
    return (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )


@router.patch("/{bot_id}/conversations/{conv_id}", response_model=ConversationOut)
def update_conversation(
    bot_id: int,
    conv_id: int,
    payload: ConversationStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a conversation's status (e.g. mark a lead resolved / hand back to the bot)."""
    bot = _get_owned_bot(bot_id, db, user)
    conv = _owned_conversation(bot, conv_id, db)
    conv.status = payload.status
    if payload.status == "resolved":
        conv.resolved_at = datetime.utcnow()
    elif payload.status == "bot":
        conv.assigned_user_id = None  # hand back to the bot -> drop the agent assignment
    db.commit()
    db.refresh(conv)
    return _conv_out_full(conv, db, bot)


# ===== Live human-agent takeover (JWT, org + bot scoped) =====

@router.post("/{bot_id}/conversations/{conv_id}/claim", response_model=ConversationOut)
def claim_conversation(
    bot_id: int,
    conv_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_agent_user),
):
    """Claim an unassigned conversation. Double-claim-safe: a single conditional UPDATE
    whose WHERE clause IS the lock. 409 if another agent already owns it."""
    bot = _get_owned_bot(bot_id, db, user)
    _owned_conversation(bot, conv_id, db)  # 404 if not this org/bot
    updated = (
        db.query(Conversation)
        .filter(
            Conversation.id == conv_id,
            Conversation.bot_id == bot.id,
            Conversation.organization_id == user.organization_id,
            Conversation.assigned_user_id.is_(None),
        )
        .update(
            {
                Conversation.assigned_user_id: user.id,
                Conversation.status: "human",
                Conversation.assigned_at: datetime.utcnow(),
            },
            synchronize_session=False,
        )
    )
    db.commit()
    conv = _owned_conversation(bot, conv_id, db)
    if updated == 0 and conv.assigned_user_id != user.id:
        raise HTTPException(status_code=409, detail="Already claimed by another agent.")
    return _conv_out_full(conv, db, bot)


@router.post("/{bot_id}/conversations/{conv_id}/reply", response_model=ConversationMessageOut)
def reply_conversation(
    bot_id: int,
    conv_id: int,
    payload: AgentReplyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_agent_user),
):
    """Post a human agent reply (role='agent'). Self-claims + flips status->human.
    Ownership-guarded so a losing racer can't reply. No billing (human labor != GPU)."""
    bot = _get_owned_bot(bot_id, db, user)
    conv = _owned_conversation(bot, conv_id, db)
    if conv.assigned_user_id not in (None, user.id) and user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="This conversation is handled by another agent.")
    now = datetime.utcnow()
    if conv.assigned_user_id is None:
        conv.assigned_user_id = user.id
        conv.assigned_at = now
    conv.status = "human"
    conv.last_agent_at = now
    conv.last_message_at = now
    msg = Message(
        organization_id=conv.organization_id,
        conversation_id=conv.id,
        role="agent",
        content=payload.content,
        tokens=0,
        sender_user_id=user.id,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


@router.post("/{bot_id}/conversations/{conv_id}/release", response_model=ConversationOut)
def release_conversation(
    bot_id: int,
    conv_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_agent_user),
):
    """Release a conversation back to the shared needs_human queue."""
    bot = _get_owned_bot(bot_id, db, user)
    conv = _owned_conversation(bot, conv_id, db)
    conv.assigned_user_id = None
    conv.assigned_at = None
    conv.status = "needs_human"
    db.commit()
    db.refresh(conv)
    return _conv_out_full(conv, db, bot)


@router.get("/{bot_id}/widget/analytics", response_model=WidgetAnalyticsOut)
def widget_analytics(
    bot_id: int,
    days: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Usage analytics for a bot over the last `days`: volume, leads, fallback rate,
    token spend, a daily series, top questions, and recent unanswered questions."""
    bot = _get_owned_bot(bot_id, db, user)
    return analytics.widget_analytics(db, bot, days)
