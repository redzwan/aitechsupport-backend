from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime

from app.db.session import Base


class Setting(Base):
    """Platform-level key/value config (API keys, default model, ...).

    Single global row per key — NOT tenant-scoped. Edited by a platform admin via
    the admin settings API. Read at runtime by config_store, which falls back to
    environment variables when a key isn't set here.
    """

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
