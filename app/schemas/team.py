from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AgentOut(BaseModel):
    id: int
    email: str
    full_name: str | None = None
    role: str  # owner | admin | agent
    is_active: bool
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class AgentCreate(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=6, max_length=200)
    role: str = "agent"  # agent | admin (owner is never created here)


class AgentUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    role: str | None = None  # agent | admin
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=200)


class SupportContactOut(BaseModel):
    """The org's offline fallback — what visitors get when no agent is online."""
    support_email: str | None = None
    support_whatsapp: str | None = None
    # Whether support_whatsapp can actually be turned into a wa.me link. A number
    # the normalizer rejects would silently disable the offline WhatsApp option,
    # so the dashboard shows this rather than letting it fail in the widget.
    whatsapp_valid: bool = False


class SupportContactUpdate(BaseModel):
    # Empty string clears the field; None (absent) leaves it untouched.
    support_email: str | None = Field(default=None, max_length=200)
    support_whatsapp: str | None = Field(default=None, max_length=40)
