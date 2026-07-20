"""Agent-facing endpoints that span an org's whole fleet of bots/sites.

The per-bot inbox lives under /bots/{id}/conversations; this module adds the
org-WIDE queue so one human sees every site's needs-human conversations in a
single merged list. Claim/reply/release stay bot-scoped (each row carries its
bot_id so the client knows which path to POST to)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_agent_user
from app.models.user import User
from app.models.bot import Bot
from app.models.channel import Channel
from app.models.conversation import Conversation, Message
from app.schemas.widget import QueueRow

router = APIRouter()

QUEUE_LIMIT = 200


@router.get("/queue", response_model=list[QueueRow])
def agent_queue(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_agent_user),
):
    """Every conversation across all of the org's bots (newest first), optionally
    filtered by status (e.g. needs_human). Each row is tagged with its bot/site."""
    org_id = user.organization_id
    q = db.query(Conversation).filter(Conversation.organization_id == org_id)
    if status:
        q = q.filter(Conversation.status == status)
    convs = q.order_by(Conversation.last_message_at.desc()).limit(QUEUE_LIMIT).all()
    if not convs:
        return []

    ids = [c.id for c in convs]
    counts = dict(
        db.query(Message.conversation_id, func.count(Message.id))
        .filter(Message.conversation_id.in_(ids))
        .group_by(Message.conversation_id)
        .all()
    )
    bot_names = {b.id: b.name for b in db.query(Bot).filter(Bot.organization_id == org_id).all()}
    kinds = {
        ch.id: ch.kind
        for ch in db.query(Channel).join(Bot, Channel.bot_id == Bot.id)
        .filter(Bot.organization_id == org_id).all()
    }
    assignee_ids = {c.assigned_user_id for c in convs if c.assigned_user_id}
    names = {}
    if assignee_ids:
        for u in db.query(User).filter(User.id.in_(assignee_ids)).all():
            names[u.id] = u.full_name or u.email

    return [
        QueueRow(
            id=c.id,
            status=c.status,
            channel_kind=kinds.get(c.channel_id),
            contact_name=c.contact_name,
            contact_email=c.contact_email,
            needs_human_at=c.needs_human_at,
            assigned_user_id=c.assigned_user_id,
            assignee_name=names.get(c.assigned_user_id),
            last_message_at=c.last_message_at,
            created_at=c.created_at,
            message_count=counts.get(c.id, 0),
            bot_id=c.bot_id,
            bot_name=bot_names.get(c.bot_id, f"Bot #{c.bot_id}"),
        )
        for c in convs
    ]
