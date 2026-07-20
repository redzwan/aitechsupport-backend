from datetime import datetime

from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey

from app.db.session import Base


class InternalMessage(Base):
    """A 1:1 direct message between two agents in the same org.

    Persisted (not just streamed) because the realtime bus is best-effort — the
    client catches up with GET /agent/chat?after=<id> on reconnect."""

    __tablename__ = "internal_messages"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    from_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
