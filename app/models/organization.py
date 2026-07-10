from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime

from app.db.session import Base


class Organization(Base):
    """A tenant. Everything else is scoped by organization_id."""

    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
