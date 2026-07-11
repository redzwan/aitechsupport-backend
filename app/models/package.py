from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON

from app.db.session import Base


class Package(Base):
    """A sellable AI-chatbot plan. The operator manages these in the admin panel."""

    __tablename__ = "packages"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    # Whole ringgit per month (0 = free).
    price_myr = Column(Integer, default=0, nullable=False)
    monthly_token_quota = Column(Integer, default=0, nullable=False)
    max_bots = Column(Integer, default=1, nullable=False)
    # List[str] of marketing bullet points.
    features = Column(JSON, default=list)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
