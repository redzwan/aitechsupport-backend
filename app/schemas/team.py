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
