from datetime import datetime

from pydantic import BaseModel, Field


class GameCreate(BaseModel):
    opponent_user_id: int = Field(gt=0)


class MoveSend(BaseModel):
    san: str = Field(min_length=2, max_length=12)
    # Set by the client when the game ends on this move: white | black | draw.
    result: str | None = None


class GameOut(BaseModel):
    id: int
    kind: str
    white_user_id: int
    black_user_id: int
    white_name: str
    black_name: str
    status: str          # active | finished | aborted
    result: str | None = None
    moves: list[str]
    turn: str            # white | black (whose move it is)
    your_color: str      # white | black
    created_at: datetime | None = None
