"""Org-invite validity + code generation."""
from __future__ import annotations

import secrets
from datetime import datetime

from app.models.org_invite import OrgInvite


def gen_code() -> str:
    """A high-entropy, URL-safe join code (~16 chars)."""
    return secrets.token_urlsafe(12)


def is_valid(inv: OrgInvite, now: datetime | None = None) -> bool:
    """True if the invite can still be redeemed (active, unexpired, uses left)."""
    now = now or datetime.utcnow()
    if not inv.is_active:
        return False
    if inv.expires_at is not None and inv.expires_at < now:
        return False
    if inv.max_uses is not None and inv.uses >= inv.max_uses:
        return False
    return True
