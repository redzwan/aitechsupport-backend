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

    # End-user identity on the channel (e.g. WhatsApp phone number, or a website
    # widget session token).
    external_user_id = Column(String, index=True, nullable=True)
    # Last client IP seen for this visitor (captured on each turn) — lets an agent
    # block by IP, which isn't otherwise persisted.
    last_ip = Column(String, nullable=True)
    # Website the visitor came from (widget embed Origin, e.g. https://kerjakan.my),
    # captured on the first turn so the agent sees the source site.
    source_url = Column(String, nullable=True)

    # bot | needs_human | human | resolved   (drives the handoff inbox)
    status = Column(String, default="bot", nullable=False)

    # Lead-capture: set when a visitor asks for a human (website widget handoff).
    contact_name = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    needs_human_at = Column(DateTime, nullable=True)

    # Live human-agent takeover: which agent (org user) owns this conversation.
    assigned_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    last_agent_at = Column(DateTime, nullable=True)

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
    # Which org user authored an agent reply (null for bot/user messages).
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Point-in-time display name of the agent (shown to the visitor). Captured at
    # send time so it survives later profile edits.
    sender_name = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
