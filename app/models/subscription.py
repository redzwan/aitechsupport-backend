from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from app.db.session import Base


class Subscription(Base):
    """Billing plan + usage counters for one organization (Billplz-backed)."""

    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), unique=True, index=True, nullable=False)

    # Package slug (see packages.slug): free | starter | pro | business | ...
    plan = Column(String, default="free", nullable=False)
    # active | past_due | canceled
    status = Column(String, default="active", nullable=False)

    billplz_reference = Column(String, nullable=True)

    # Usage metering for plan limits (reset each billing cycle).
    messages_used = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0, nullable=False)
    period_start = Column(DateTime, default=datetime.utcnow)

    # Admin-set monthly renewal cycle (mainly for bank-transfer clients, who
    # have no gateway subscription to derive a renewal date from).
    start_date = Column(DateTime, nullable=True)
    next_billing_date = Column(DateTime, nullable=True)
    last_reminder_sent = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
