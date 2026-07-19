"""Widget analytics — aggregates over the persisted Conversation/Message rows.

All read-only, org+bot scoped by the caller. A fallback is an assistant message
with tokens == 0 (the no-context path), so the fallback rate is how often the bot
couldn't answer — and the paired user turn is an "unanswered question" to feed back
into the knowledge base.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.bot import Bot
from app.models.conversation import Conversation, Message


def widget_analytics(db: Session, bot: Bot, days: int) -> dict:
    days = max(1, min(days, 365))
    cutoff = datetime.utcnow() - timedelta(days=days)

    def msgs():
        return (
            db.query(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .filter(Conversation.bot_id == bot.id, Message.created_at >= cutoff)
        )

    conversations = (
        db.query(func.count(Conversation.id))
        .filter(Conversation.bot_id == bot.id, Conversation.created_at >= cutoff)
        .scalar()
        or 0
    )
    leads = (
        db.query(func.count(Conversation.id))
        .filter(
            Conversation.bot_id == bot.id,
            Conversation.status == "needs_human",
            Conversation.created_at >= cutoff,
        )
        .scalar()
        or 0
    )
    messages = msgs().count()
    user_messages = msgs().filter(Message.role == "user").count()
    assistant_messages = msgs().filter(Message.role == "assistant").count()
    fallbacks = msgs().filter(Message.role == "assistant", Message.tokens == 0).count()
    tokens = (
        db.query(func.coalesce(func.sum(Message.tokens), 0))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.bot_id == bot.id, Message.created_at >= cutoff)
        .scalar()
        or 0
    )

    # messages per day
    day = func.date(Message.created_at)
    series_rows = (
        db.query(day.label("d"), func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.bot_id == bot.id, Message.created_at >= cutoff)
        .group_by(day)
        .order_by(day)
        .all()
    )
    series = [{"date": str(d), "count": int(c)} for d, c in series_rows]

    # top asked questions
    top_rows = (
        db.query(func.lower(Message.content).label("q"), func.count(Message.id).label("n"))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.bot_id == bot.id, Message.created_at >= cutoff, Message.role == "user")
        .group_by(func.lower(Message.content))
        .order_by(func.count(Message.id).desc())
        .limit(10)
        .all()
    )
    top_questions = [{"question": q[:200], "count": int(n)} for q, n in top_rows]

    # unanswered = the user turn just before each recent fallback
    fallback_msgs = (
        msgs()
        .filter(Message.role == "assistant", Message.tokens == 0)
        .order_by(Message.created_at.desc())
        .limit(30)
        .all()
    )
    unanswered: list[dict] = []
    seen: set[str] = set()
    for m in fallback_msgs:
        uq = (
            db.query(Message)
            .filter(Message.conversation_id == m.conversation_id, Message.role == "user", Message.id < m.id)
            .order_by(Message.id.desc())
            .first()
        )
        if uq and uq.content and uq.content.lower() not in seen:
            seen.add(uq.content.lower())
            unanswered.append({"question": uq.content[:200], "at": m.created_at})
        if len(unanswered) >= 10:
            break

    return {
        "days": days,
        "conversations": int(conversations),
        "leads": int(leads),
        "messages": int(messages),
        "user_messages": int(user_messages),
        "tokens": int(tokens),
        "fallbacks": int(fallbacks),
        "fallback_rate": round(fallbacks / assistant_messages, 3) if assistant_messages else 0.0,
        "series": series,
        "top_questions": top_questions,
        "unanswered": unanswered,
    }
