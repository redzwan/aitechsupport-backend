"""Subscription + token-metering helpers, plus Billplz gateway config.

Paid-plan self-serve stays gated on BILLING_ENABLED + configured Billplz
credentials; until then a platform admin assigns paid plans manually. The
Billplz connection details (API key, X-Signature key, collection, sandbox
toggle) resolve from config_store — DB settings first, `.env` as fallback — so
an admin can wire the gateway from the panel without a redeploy, same pattern as
storage/SMTP.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import config_store
from app.core.settings import settings
from app.models.subscription import Subscription
from app.models.package import Package

logger = logging.getLogger(__name__)

PERIOD_DAYS = 30
DEFAULT_PLAN = "free"

# Billplz API roots. Sandbox is a fully separate environment with its own keys.
BILLPLZ_LIVE_BASE = "https://www.billplz.com/api"
BILLPLZ_SANDBOX_BASE = "https://www.billplz-sandbox.com/api"


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


# ===== Billplz payment gateway =====

def _as_bool(raw: str, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    return str(raw).strip().lower() in ("true", "1", "yes", "on")


def billplz_config(db: Session | None = None) -> dict:
    """Resolve Billplz config (DB settings first, env fallback via config_store)."""
    g = config_store.get
    return {
        "api_key": g("BILLPLZ_API_KEY") or settings.BILLPLZ_API_KEY,
        "x_signature_key": g("BILLPLZ_X_SIGNATURE_KEY") or settings.BILLPLZ_X_SIGNATURE_KEY,
        "collection_id": g("BILLPLZ_COLLECTION_ID") or settings.BILLPLZ_COLLECTION_ID,
        "sandbox": _as_bool(g("BILLPLZ_SANDBOX"), settings.BILLPLZ_SANDBOX),
        "enabled": _as_bool(g("BILLING_ENABLED"), settings.BILLING_ENABLED),
    }


def billplz_api_base(sandbox: bool) -> str:
    return BILLPLZ_SANDBOX_BASE if sandbox else BILLPLZ_LIVE_BASE


def billplz_is_configured(db: Session | None = None) -> bool:
    """True when billing is enabled and the gateway can create bills.

    A collection is required to create bills, so it's part of "configured" — the
    X-Signature key is only needed to verify webhooks, so it's not gated here.
    """
    cfg = billplz_config(db)
    return cfg["enabled"] and bool(cfg["api_key"]) and bool(cfg["collection_id"])


def test_billplz(db: Session | None = None) -> dict:
    """Verify the API key (and collection, if set) reach Billplz. Raises on failure.

    Billplz authenticates with the API key as HTTP Basic username and a blank
    password. When a collection id is set we fetch that collection (proves the
    key AND the collection exist in the selected environment); otherwise we list
    collections, which still proves the key + sandbox choice are valid.
    """
    cfg = billplz_config(db)
    if not cfg["api_key"]:
        raise RuntimeError("Enter a Billplz API key before testing.")
    base = billplz_api_base(cfg["sandbox"])
    coll = cfg["collection_id"]
    url = f"{base}/v3/collections/{coll}" if coll else f"{base}/v3/collections"
    try:
        resp = httpx.get(url, auth=(cfg["api_key"], ""), timeout=15)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not reach Billplz: {exc}") from exc
    if resp.status_code == 401:
        env = "sandbox" if cfg["sandbox"] else "production"
        raise RuntimeError(f"Billplz rejected the API key for the {env} environment (401).")
    if resp.status_code == 404 and coll:
        env = "sandbox" if cfg["sandbox"] else "production"
        raise RuntimeError(f"Collection '{coll}' was not found in the {env} environment (404).")
    if resp.status_code >= 400:
        raise RuntimeError(f"Billplz returned {resp.status_code}: {resp.text[:200]}")
    return {"sandbox": cfg["sandbox"], "collection_id": coll or None}
