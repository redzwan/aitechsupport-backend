from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class InviteCreate(BaseModel):
    role: str = "agent"  # agent | admin (never owner)
    max_uses: int | None = Field(default=1, ge=1)          # null = unlimited
    expires_in_hours: int | None = Field(default=168, ge=1)  # null = never; default 7 days


class InviteOut(BaseModel):
    id: int
    code: str
    role: str
    max_uses: int | None = None
    uses: int
    expires_at: datetime | None = None
    is_active: bool
    created_at: datetime | None = None
    join_url: str


class InvitePreview(BaseModel):
    organization_name: str
    role: str
    valid: bool


class JoinRequest(BaseModel):
    code: str = Field(min_length=4, max_length=64)
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=6, max_length=200)


class AcceptInviteRequest(BaseModel):
    code: str = Field(min_length=4, max_length=64)
