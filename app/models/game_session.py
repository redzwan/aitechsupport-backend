from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey

from app.db.session import Base


class GameSession(Base):
    """A two-player game between agents (chess). Moves are relayed turn-by-turn;
    `moves` is the authoritative SAN list, so a reconnecting client replays it to
    the same start position with zero drift. Turn = white if len(moves) is even."""

    __tablename__ = "game_sessions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    kind = Column(String, default="chess", nullable=False)
    white_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    black_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)

    moves = Column(Text, default="[]", nullable=False)  # JSON array of SAN strings
    status = Column(String, default="active", nullable=False)  # active | finished | aborted
    result = Column(String, nullable=True)  # white | black | draw

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
