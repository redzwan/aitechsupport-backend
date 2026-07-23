from pydantic import BaseModel, Field, field_validator

from app.core.handoff import HANDOFF_MODES, normalize_wa_number
from app.core.settings import settings


class BotCreate(BaseModel):
    name: str
    system_prompt: str | None = None
    fallback_message: str | None = None


class BotUpdate(BaseModel):
    """Partial update — only the fields provided are changed."""

    name: str | None = None
    system_prompt: str | None = None
    fallback_message: str | None = None
    is_active: bool | None = None
    handoff_mode: str | None = None
    whatsapp_number: str | None = None

    @field_validator("handoff_mode")
    @classmethod
    def _known_mode(cls, v: str | None) -> str | None:
        if v is None:
            return v
        mode = v.strip().lower()
        if mode not in HANDOFF_MODES:
            raise ValueError(f"handoff_mode must be one of {', '.join(HANDOFF_MODES)}")
        return mode

    @field_validator("whatsapp_number")
    @classmethod
    def _valid_number(cls, v: str | None) -> str | None:
        """Store the normalized digits, so every reader gets wa.me-ready input.

        Rejecting here rather than silently blanking means a typo surfaces in the
        settings form instead of quietly disabling handoff weeks later.
        """
        if v is None or not v.strip():
            return None
        number = normalize_wa_number(v)
        if not number:
            raise ValueError(
                "Enter a valid WhatsApp number with country code, e.g. +60 12-345 6789"
            )
        return number


class BotOut(BaseModel):
    id: int
    organization_id: int
    name: str
    system_prompt: str | None = None
    fallback_message: str | None = None
    # The model actually answering this bot, resolved from its org's package
    # (or an admin-only override) — read-only, not customer-editable.
    effective_chat_model: str
    is_active: bool
    handoff_mode: str = "form"
    whatsapp_number: str | None = None

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    """Direct test endpoint — ask a bot a question without going through a channel."""
    question: str = Field(min_length=1, max_length=settings.MAX_QUESTION_CHARS)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be blank")
        return v


class ChatResponse(BaseModel):
    answer: str
