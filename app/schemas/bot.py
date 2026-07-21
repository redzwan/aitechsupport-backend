from pydantic import BaseModel, Field, field_validator

from app.core.settings import settings


class BotCreate(BaseModel):
    name: str
    system_prompt: str | None = None
    fallback_message: str | None = None
    # OpenRouter model id; null -> platform default. Free text so any model works.
    chat_model: str | None = None


class BotUpdate(BaseModel):
    """Partial update — only the fields provided are changed."""

    name: str | None = None
    system_prompt: str | None = None
    fallback_message: str | None = None
    chat_model: str | None = None
    is_active: bool | None = None


class BotOut(BaseModel):
    id: int
    organization_id: int
    name: str
    system_prompt: str | None = None
    fallback_message: str | None = None
    chat_model: str | None = None
    is_active: bool

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
