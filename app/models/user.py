from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey

from app.db.session import Base


class User(Base):
    """A dashboard user belonging to one organization."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)

    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)

    # owner | admin | agent  (agent = human handoff operator)
    role = Column(String, default="owner", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # Platform operator (not a tenant role): may edit global settings / API keys.
    is_platform_admin = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
