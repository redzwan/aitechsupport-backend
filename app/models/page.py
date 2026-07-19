from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime

from app.db.session import Base


class Page(Base):
    """A CMS content page (About, Privacy, Terms, …) managed by the platform admin
    and rendered publicly at /<slug>. Body is trusted HTML (only the platform admin
    edits it — same trust model as email templates)."""

    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)              # trusted HTML
    meta_description = Column(String, nullable=True)  # for SEO / <meta>
    is_published = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
