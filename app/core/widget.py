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

from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.bot import Bot
from app.models.conversation import Conversation, Message
from app.models.blocked_visitor import BlockedVisitor

WIDGET_KIND = "widget"
MAX_ALLOWED_ORIGINS = 10
MAX_SESSION_ID = 64

DEFAULT_APPEARANCE: dict = {
    "title": "Chat with us",
    "subtitle": "We typically reply in a few minutes",
    "greeting": "Hi! How can I help you today?",
    "primary_color": "#4f46e5",
    "position": "right",          # right | left
    "launcher_label": "Chat",
    "theme": "auto",              # auto | light | dark
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


def is_blocked(db: Session, channel: Channel, session_id: str,
               ip: str | None = None, email: str | None = None) -> bool:
    """True if this visitor is blocked on this bot by ANY durable identifier
    (session token, IP, or email)."""
    pairs = [("session", session_id)]
    if ip:
        pairs.append(("ip", ip))
    if email:
        e = email.strip().lower()
        if e:
            pairs.append(("email", e))
    conds = [and_(BlockedVisitor.identifier_type == t, BlockedVisitor.identifier == v)
             for t, v in pairs if v]
    if not conds:
        return False
    return (
        db.query(BlockedVisitor.id)
        .filter(
            BlockedVisitor.organization_id == channel.organization_id,
            BlockedVisitor.bot_id == channel.bot_id,
            or_(*conds),
        )
        .first()
        is not None
    )


def record_turn(
    db: Session, channel: Channel, session_id: str, question: str, answer: str, tokens: int,
    ip: str | None = None, source_url: str | None = None,
    image_key: str | None = None, image_mime: str | None = None, image_size: int | None = None,
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
                   role="user", content=question, tokens=0,
                   image_key=image_key, image_mime=image_mime, image_size=image_size))
    db.add(Message(organization_id=channel.organization_id, conversation_id=conv.id,
                   role="assistant", content=answer, tokens=tokens))
    conv.last_message_at = now
    if ip:
        conv.last_ip = ip
    if source_url and not conv.source_url:
        conv.source_url = source_url
    db.commit()
    return conv


def find_conversation(db: Session, channel: Channel, session_id: str) -> Conversation | None:
    return (
        db.query(Conversation)
        .filter(
            Conversation.channel_id == channel.id,
            Conversation.external_user_id == session_id,
            Conversation.organization_id == channel.organization_id,
        )
        .first()
    )


def mark_handoff(db: Session, channel: Channel, session_id: str, name: str,
                 email: str, message: str, ip: str | None = None,
                 source_url: str | None = None) -> Conversation:
    """Flag the visitor's conversation as needing a human + store their contact
    (lead-capture). Creates the conversation if they hadn't chatted yet."""
    now = datetime.utcnow()
    conv = find_conversation(db, channel, session_id)
    if conv is None:
        conv = Conversation(
            organization_id=channel.organization_id,
            bot_id=channel.bot_id,
            channel_id=channel.id,
            external_user_id=session_id,
            last_message_at=now,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
    conv.status = "needs_human"
    conv.contact_name = (name or "").strip()[:120] or None
    conv.contact_email = (email or "").strip()[:200] or None
    conv.needs_human_at = now
    conv.last_message_at = now
    if ip:
        conv.last_ip = ip
    if source_url and not conv.source_url:
        conv.source_url = source_url
    if message and message.strip():
        db.add(Message(organization_id=channel.organization_id, conversation_id=conv.id,
                       role="user", content=message.strip()[:4000], tokens=0))
    db.commit()
    db.refresh(conv)
    return conv


def record_user_message(db: Session, channel: Channel, session_id: str, content: str,
                        ip: str | None = None, source_url: str | None = None,
                        image_key: str | None = None, image_mime: str | None = None,
                        image_size: int | None = None) -> Conversation:
    """Store ONLY the visitor's message (no bot answer) — used when a human owns the
    conversation and the bot is paused. Find-or-creates the conversation."""
    now = datetime.utcnow()
    conv = find_conversation(db, channel, session_id)
    if conv is None:
        conv = Conversation(
            organization_id=channel.organization_id,
            bot_id=channel.bot_id,
            channel_id=channel.id,
            external_user_id=session_id,
            last_message_at=now,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
    db.add(Message(organization_id=channel.organization_id, conversation_id=conv.id,
                   role="user", content=content, tokens=0,
                   image_key=image_key, image_mime=image_mime, image_size=image_size))
    conv.last_message_at = now
    if ip:
        conv.last_ip = ip
    if source_url and not conv.source_url:
        conv.source_url = source_url
    db.commit()
    db.refresh(conv)
    return conv
