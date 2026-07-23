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

    # Which AI model bots on this package answer with — the customer no longer
    # picks a model themselves, the admin decides it per package.
    # "self_hosted" (Ollama on self_hosted_base_url) or "openrouter".
    model_provider = Column(String, default="openrouter", nullable=False)
    chat_model = Column(String, nullable=True)  # Ollama tag or OpenRouter id; falls back to models_catalog.default_model()
    self_hosted_base_url = Column(String, nullable=True)  # only used when model_provider == "self_hosted"

    created_at = Column(DateTime, default=datetime.utcnow)
