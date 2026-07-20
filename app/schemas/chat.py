from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DmSend(BaseModel):
    to_user_id: int = Field(gt=0)
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content must not be blank")
        return v


class DmOut(BaseModel):
    id: int
    from_user_id: int
    from_name: str
    to_user_id: int
    content: str
    created_at: datetime | None = None
