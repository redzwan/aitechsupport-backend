from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime

from app.db.session import Base


class EmailTemplate(Base):
    """An admin-editable transactional email. Body uses {variable} placeholders."""

    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)  # e.g. "welcome"
    name = Column(String, nullable=False)  # human label
    subject = Column(String, nullable=False)
    body_html = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
