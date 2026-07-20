from datetime import datetime

from pydantic import BaseModel, Field


class PresenceUpdate(BaseModel):
    # The agent's intent. "busy" is also derived automatically when they own an
    # open human chat; "away" is honored as-is; anything else normalizes to online.
    status: str = Field(default="online")


class PresenceRow(BaseModel):
    user_id: int
    name: str
    role: str
    status: str  # effective: online | busy | away | offline
    last_seen_at: datetime | None = None
