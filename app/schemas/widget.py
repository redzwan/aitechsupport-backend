from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.settings import settings


# ===== Public (JWT-less) widget schemas =====

class PublicChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=settings.MAX_QUESTION_CHARS)
    session_id: str | None = Field(default=None, max_length=64)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be blank")
        return v


class PublicChatResponse(BaseModel):
    answer: str
    session_id: str
    status: str = "bot"       # bot | needs_human | human | resolved
    handoff: bool = False     # true when the bot couldn't answer -> offer a human


class HandoffRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200)
    message: str | None = Field(default=None, max_length=4000)

    @field_validator("name", "email")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("email")
    @classmethod
    def _looks_like_email(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v or "." not in v.split("@")[-1] or " " in v:
            raise ValueError("invalid email")
        return v


class HandoffResponse(BaseModel):
    ok: bool = True
    status: str = "needs_human"


class WidgetPublicConfig(BaseModel):
    """Appearance the bundle needs to render itself. No secrets."""
    title: str
    subtitle: str
    greeting: str
    primary_color: str
    position: str
    launcher_label: str
    theme: str


# ===== Dashboard (JWT, org-scoped) widget config =====

class WidgetConfigOut(BaseModel):
    enabled: bool
    public_key: str
    allowed_origins: list[str]
    appearance: dict
    daily_message_cap: int | None = None
    src_url: str
    snippet: str


class WidgetConfigUpdate(BaseModel):
    enabled: bool | None = None
    allowed_origins: list[str] | None = None
    appearance: dict | None = None
    daily_message_cap: int | None = None


# ===== Dashboard conversation inbox (JWT, org-scoped) =====

class ConversationOut(BaseModel):
    id: int
    status: str
    channel_kind: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    needs_human_at: datetime | None = None
    last_message_at: datetime | None = None
    created_at: datetime | None = None
    message_count: int = 0

    class Config:
        from_attributes = True


class ConversationMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ConversationStatusUpdate(BaseModel):
    status: str = Field(pattern="^(bot|needs_human|human|resolved)$")
