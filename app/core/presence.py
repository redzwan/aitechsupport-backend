"""Agent presence: effective online status, shared by the agent API and the
public widget.

Presence is stored on `users` (presence_status + last_seen_at) but is only
trustworthy in combination with a freshness check: a client that crashes never
gets to say "offline", so a stored "online" older than HEARTBEAT_TTL reads as
offline. Every consumer must go through `effective_status` for that reason.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.user import User

# A stored "online" whose last_seen_at is older than this reads as offline — that
# freshness check is what makes presence trustworthy (a crashed client goes offline
# on its own). Should exceed the client heartbeat + the 20s SSE keepalive.
HEARTBEAT_TTL = timedelta(seconds=45)

# Statuses that mean a visitor can actually reach a human right now. "busy" counts:
# the agent is at the desk handling another chat, so the request queues rather than
# vanishing. "away" does not — the client said nobody is watching.
AVAILABLE_STATUSES = ("online", "busy")


def busy_user_ids(db: Session, org_id: int) -> set[int]:
    """Agents currently owning an open human chat (auto-busy)."""
    rows = (
        db.query(Conversation.assigned_user_id)
        .filter(
            Conversation.organization_id == org_id,
            Conversation.status == "human",
            Conversation.assigned_user_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def effective_status(user: User, now: datetime, is_busy: bool) -> str:
    """online | busy | away | offline — never the raw stored value."""
    if user.last_seen_at is None or (now - user.last_seen_at) > HEARTBEAT_TTL:
        return "offline"
    stored = user.presence_status or "online"
    if stored == "away":
        return "away"
    if is_busy or stored == "busy":
        return "busy"
    return "online"


def has_available_agent(db: Session, org_id: int) -> bool:
    """Is at least one active staff member reachable right now?

    Cheap by design: this runs on an unauthenticated public route that the widget
    polls, so it resolves to one indexed EXISTS-style query. The busy/online
    distinction is irrelevant here — a busy agent is still a human who will see
    the chat — so the `busy_user_ids` join is skipped and only "away" is excluded.
    """
    cutoff = datetime.utcnow() - HEARTBEAT_TTL
    row = (
        db.query(User.id)
        .filter(
            User.organization_id == org_id,
            User.is_active.is_(True),
            User.last_seen_at.isnot(None),
            User.last_seen_at >= cutoff,
            (User.presence_status.is_(None)) | (User.presence_status != "away"),
        )
        .first()
    )
    return row is not None
