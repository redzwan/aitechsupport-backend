from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey

from app.db.session import Base


class Payment(Base):
    """One Billplz bill for a paid-plan purchase.

    Persisted at checkout (status ``pending``) so the webhook can map the paid
    bill back to the right organization + plan and activate it idempotently —
    the bill id, not a client-supplied reference, is the source of truth.
    """

    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)

    # Package slug to activate once the bill is paid (see packages.slug).
    plan_slug = Column(String, nullable=False)
    amount_cents = Column(Integer, nullable=False)  # sen (RM * 100)

    # Billplz bill id (null only if the gateway call failed before we got one).
    billplz_bill_id = Column(String, unique=True, index=True, nullable=True)
    # pending | paid | failed
    status = Column(String, default="pending", nullable=False)
    # True if created against the Billplz sandbox environment.
    sandbox = Column(Boolean, default=False, nullable=False)

    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
