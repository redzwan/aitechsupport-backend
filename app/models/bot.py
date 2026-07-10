from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text

from app.db.session import Base


class Bot(Base):
    """A configured assistant for one organization. Answers from its KnowledgeSources."""

    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)

    name = Column(String, nullable=False)
    # Persona / guardrail instructions prepended to the RAG prompt.
    system_prompt = Column(Text, nullable=True)
    # Shown when retrieval confidence is low, before offering human handoff.
    fallback_message = Column(Text, default="Let me connect you with a human who can help.")
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
