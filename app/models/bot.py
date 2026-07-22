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
    # OpenRouter model id for answers (e.g. "anthropic/claude-haiku-4.5",
    # "openai/gpt-5.4-mini"). Null -> the platform default (models_catalog).
    chat_model = Column(String, nullable=True)
    # Shown when retrieval confidence is low, before offering human handoff.
    fallback_message = Column(Text, default="Let me connect you with a human who can help.")
    is_active = Column(Boolean, default=True, nullable=False)

    # What a visitor is offered when the bot can't answer:
    #   form     -> lead-capture form (name/email), answered in the dashboard inbox
    #   whatsapp -> a click-to-chat link to whatsapp_number
    #   both     -> WhatsApp first, form underneath
    # `whatsapp`/`both` fall back to the form when whatsapp_number is unset, so a
    # half-configured bot still has a working escape hatch.
    handoff_mode = Column(String, default="form", nullable=False)
    # Digits only, full international form, no '+' or separators (wa.me needs
    # exactly this, e.g. "60123456789"). Normalized on write.
    whatsapp_number = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
