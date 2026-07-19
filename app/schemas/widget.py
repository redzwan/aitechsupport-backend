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
    status: str = "bot"   # bot | needs_human | human


class WidgetPublicConfig(BaseModel):
    """Appearance the bundle needs to render itself. No secrets."""
    title: str
    greeting: str
    primary_color: str
    position: str
    launcher_label: str


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
