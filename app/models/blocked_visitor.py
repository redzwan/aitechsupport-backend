from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint

from app.db.session import Base


class BlockedVisitor(Base):
    """A visitor an agent has blocked from a bot's widget.

    Keyed on DURABLE identifiers (session token, IP, email) rather than a
    conversation, so a blocked abuser can't just start a fresh session to get a
    new conversation. Scoped per (organization, bot)."""

    __tablename__ = "blocked_visitors"
    __table_args__ = (
        UniqueConstraint("organization_id", "bot_id", "identifier_type", "identifier",
                         name="uq_blocked_org_bot_ident"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True, nullable=False)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=True)

    # session | ip | email
    identifier_type = Column(String, nullable=False)
    identifier = Column(String, index=True, nullable=False)

    blocked_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
