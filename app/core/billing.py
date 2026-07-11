"""Subscription + token-metering helpers.

Billplz payment is intentionally OFF (kill-switch) — self-serve is limited to the
free plan; paid plans are assigned by a platform admin. Real payment gets wired here later.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.subscription import Subscription
from app.models.package import Package

PERIOD_DAYS = 30
DEFAULT_PLAN = "free"


def package_for(db: Session, slug: str) -> Package | None:
    return db.query(Package).filter(Package.slug == slug).first()


def get_or_create_subscription(db: Session, organization_id: int) -> Subscription:
    """Return the org's subscription, creating a free one and rolling the monthly
    usage window if the current period has elapsed."""
    sub = db.query(Subscription).filter(Subscription.organization_id == organization_id).first()
    if sub is None:
        sub = Subscription(organization_id=organization_id, plan=DEFAULT_PLAN, tokens_used=0, period_start=datetime.utcnow())
        db.add(sub)
        try:
            db.commit()
            db.refresh(sub)
        except IntegrityError:
            # Concurrent first-access created it first — use that row.
            db.rollback()
            sub = db.query(Subscription).filter(Subscription.organization_id == organization_id).first()
        return sub

    # Roll the window if the 30-day period has passed (atomic to avoid clobbering a
    # concurrent usage write).
    if sub.period_start and datetime.utcnow() - sub.period_start >= timedelta(days=PERIOD_DAYS):
        db.query(Subscription).filter(Subscription.organization_id == organization_id).update(
            {Subscription.tokens_used: 0, Subscription.messages_used: 0, Subscription.period_start: datetime.utcnow()},
            synchronize_session=False,
        )
        db.commit()
        db.refresh(sub)
    return sub


def quota_for(db: Session, sub: Subscription) -> int:
    """Monthly token quota for this subscription's package (0 = unknown/no allowance)."""
    pkg = package_for(db, sub.plan)
    return pkg.monthly_token_quota if pkg else 0


def tokens_remaining(db: Session, sub: Subscription) -> int:
    quota = quota_for(db, sub)
    return max(0, quota - (sub.tokens_used or 0))


def has_quota(db: Session, sub: Subscription) -> bool:
    """True if the org can still spend tokens (quota 0 is treated as 'no allowance')."""
    return tokens_remaining(db, sub) > 0


def record_usage(db: Session, organization_id: int, tokens: int, messages: int = 1) -> None:
    """Atomically increment usage so concurrent chats don't lose counts."""
    get_or_create_subscription(db, organization_id)  # ensure row exists + window rolled
    db.query(Subscription).filter(Subscription.organization_id == organization_id).update(
        {
            Subscription.tokens_used: Subscription.tokens_used + max(0, tokens),
            Subscription.messages_used: Subscription.messages_used + max(0, messages),
        },
        synchronize_session=False,
    )
    db.commit()


def subscribe(db: Session, organization_id: int, package: Package) -> Subscription:
    """Assign a package to the org. Only reset the usage window on a real plan change,
    so re-subscribing to the same plan can't be used to wipe usage."""
    sub = get_or_create_subscription(db, organization_id)
    changed = sub.plan != package.slug
    sub.plan = package.slug
    sub.status = "active"
    if changed:
        sub.tokens_used = 0
        sub.messages_used = 0
        sub.period_start = datetime.utcnow()
    db.commit()
    db.refresh(sub)
    return sub
