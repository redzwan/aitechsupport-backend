from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.core import billing
from app.models.user import User
from app.models.package import Package
from app.schemas.billing import PackageOut, SubscriptionOut, SubscribeRequest

router = APIRouter()


@router.get("/packages", response_model=list[PackageOut])
def list_packages(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Active packages a client can subscribe to (pricing page)."""
    return (
        db.query(Package)
        .filter(Package.is_active.is_(True))
        .order_by(Package.sort_order, Package.price_myr)
        .all()
    )


def _subscription_out(db: Session, sub) -> SubscriptionOut:
    pkg = billing.package_for(db, sub.plan)
    quota = pkg.monthly_token_quota if pkg else 0
    return SubscriptionOut(
        plan=sub.plan,
        plan_name=pkg.name if pkg else sub.plan,
        status=sub.status,
        tokens_used=sub.tokens_used or 0,
        tokens_quota=quota,
        tokens_remaining=max(0, quota - (sub.tokens_used or 0)),
        max_bots=pkg.max_bots if pkg else 1,
        period_start=sub.period_start.isoformat() if sub.period_start else None,
    )


@router.get("/subscription", response_model=SubscriptionOut)
def my_subscription(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sub = billing.get_or_create_subscription(db, user.organization_id)
    return _subscription_out(db, sub)


@router.post("/subscribe", response_model=SubscriptionOut)
def subscribe(payload: SubscribeRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pkg = billing.package_for(db, payload.package_slug)
    if not pkg or not pkg.is_active:
        raise HTTPException(status_code=404, detail="Package not found")
    # Only owners/admins of the org may change the plan.
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only an owner can change the plan")

    sub = billing.get_or_create_subscription(db, user.organization_id)
    # No-op re-subscribe is rejected so it can't be used to reset the usage window.
    if pkg.slug == sub.plan:
        raise HTTPException(status_code=400, detail="You're already on this plan.")
    # Paid plans require collected payment, which isn't wired yet — an admin assigns
    # them manually. (Self-serve is limited to free/downgrade.) Guard on price, not
    # just BILLING_ENABLED, so flipping that flag can't hand out free paid plans.
    if pkg.price_myr > 0:
        raise HTTPException(
            status_code=503,
            detail="Paid plans are activated by our team — contact us to upgrade.",
        )
    sub = billing.subscribe(db, user.organization_id, pkg)
    return _subscription_out(db, sub)
