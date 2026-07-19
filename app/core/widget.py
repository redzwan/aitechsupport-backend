"""Website-widget helpers: the public embed key, Origin validation, the widget
config Channel (kind='widget'), and persistence of an anonymous visitor's turn.

Widget config lives on the existing Channel model so Conversation.channel_id scopes
the (future) handoff inbox for free. organization_id is always derived from the
resolved Channel — never from anything the public client supplies.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.bot import Bot
from app.models.conversation import Conversation, Message

WIDGET_KIND = "widget"
MAX_ALLOWED_ORIGINS = 10
MAX_SESSION_ID = 64

DEFAULT_APPEARANCE: dict = {
    "title": "Chat with us",
    "greeting": "Hi! How can I help you today?",
    "primary_color": "#4f46e5",
    "position": "right",          # right | left
    "launcher_label": "Chat",
}


def gen_public_key() -> str:
    """A high-entropy, non-enumerable selector embedded in tenant HTML (not a secret)."""
    return "pk_" + secrets.token_urlsafe(24)


def normalize_origin(raw: str) -> str | None:
    """Return a normalized `scheme://host[:port]` origin, or None if invalid."""
    raw = (raw or "").strip().lower()
    if not raw or raw in ("*", "null") or "://" not in raw:
        return None
    p = urlparse(raw)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    origin = f"{p.scheme}://{p.hostname}"
    if p.port:
        origin += f":{p.port}"
    return origin


def validate_origins(origins: list[str] | None) -> list[str]:
    out: list[str] = []
    for o in (origins or []):
        n = normalize_origin(o)
        if n and n not in out:
            out.append(n)
        if len(out) >= MAX_ALLOWED_ORIGINS:
            break
    return out


def clean_session_id(raw: str | None) -> str:
    """Opaque visitor session token; generate one if absent, always cap the length."""
    raw = (raw or "").strip()
    if not raw:
        return secrets.token_urlsafe(18)
    return raw[:MAX_SESSION_ID]


def get_widget_channel(db: Session, bot: Bot) -> Channel | None:
    return (
        db.query(Channel)
        .filter(
            Channel.bot_id == bot.id,
            Channel.organization_id == bot.organization_id,
            Channel.kind == WIDGET_KIND,
        )
        .first()
    )


def get_or_create_widget_channel(db: Session, bot: Bot) -> Channel:
    """Idempotently return the bot's single widget Channel (off until enabled)."""
    ch = get_widget_channel(db, bot)
    if ch is None:
        ch = Channel(
            organization_id=bot.organization_id,
            bot_id=bot.id,
            kind=WIDGET_KIND,
            public_key=gen_public_key(),
            allowed_origins=[],
            appearance=dict(DEFAULT_APPEARANCE),
            is_active=False,
        )
        db.add(ch)
        db.commit()
        db.refresh(ch)
    return ch


def resolve_widget(db: Session, public_key: str) -> tuple[Channel, Bot] | None:
    """Resolve an ACTIVE widget channel + its ACTIVE bot from a public key, else None."""
    ch = (
        db.query(Channel)
        .filter(
            Channel.public_key == public_key,
            Channel.kind == WIDGET_KIND,
            Channel.is_active.is_(True),
        )
        .first()
    )
    if ch is None:
        return None
    bot = db.query(Bot).filter(Bot.id == ch.bot_id, Bot.is_active.is_(True)).first()
    if bot is None:
        return None
    return ch, bot


def record_turn(
    db: Session, channel: Channel, session_id: str, question: str, answer: str, tokens: int
) -> Conversation:
    """Find-or-create the visitor's conversation and append the user + assistant messages."""
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.channel_id == channel.id,
            Conversation.external_user_id == session_id,
            Conversation.organization_id == channel.organization_id,
        )
        .first()
    )
    now = datetime.utcnow()
    if conv is None:
        conv = Conversation(
            organization_id=channel.organization_id,
            bot_id=channel.bot_id,
            channel_id=channel.id,
            external_user_id=session_id,
            status="bot",
            last_message_at=now,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
    db.add(Message(organization_id=channel.organization_id, conversation_id=conv.id,
                   role="user", content=question, tokens=0))
    db.add(Message(organization_id=channel.organization_id, conversation_id=conv.id,
                   role="assistant", content=answer, tokens=tokens))
    conv.last_message_at = now
    db.commit()
    return conv
