from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text

from app.db.session import Base


class Conversation(Base):
    """A thread between an end customer and a bot on some channel."""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True, nullable=False)
    channel_id = Column(Integer, ForeignKey("channels.id"), index=True, nullable=True)

    # End-user identity on the channel (e.g. WhatsApp phone number).
    external_user_id = Column(String, index=True, nullable=True)

    # bot | needs_human | human   (drives the handoff inbox)
    status = Column(String, default="bot", nullable=False)
    last_message_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    """A single message in a conversation."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True, nullable=False)

    # user | assistant | agent   (agent = human operator)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    # Token accounting for usage-metered billing.
    tokens = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
