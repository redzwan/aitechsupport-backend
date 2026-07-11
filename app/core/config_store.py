"""Runtime config resolver: DB `settings` table first, environment as fallback.

Lets a platform admin set API keys / the default model from the admin panel
without a redeploy, while keeping `.env` as the bootstrap default. Reads open a
short-lived session (LLM/embedding calls are network-bound, so the extra indexed
lookup is negligible) — no process-local cache, so an admin update takes effect
immediately even though writes and reads may happen in different requests.
"""
from __future__ import annotations

import os

from app.db.session import SessionLocal
from app.models.setting import Setting

# Config keys the admin panel manages, mapped to their env fallback var.
MANAGED_KEYS = {
    "OPENROUTER_API_KEY": "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL": "OPENROUTER_BASE_URL",
    "VOYAGE_API_KEY": "VOYAGE_API_KEY",
    "DEFAULT_CHAT_MODEL": "DEFAULT_CHAT_MODEL",
    # SMTP / email
    "SMTP_HOST": "SMTP_HOST",
    "SMTP_PORT": "SMTP_PORT",
    "SMTP_USERNAME": "SMTP_USERNAME",
    "SMTP_PASSWORD": "SMTP_PASSWORD",
    "SMTP_FROM_EMAIL": "SMTP_FROM_EMAIL",
    "SMTP_FROM_NAME": "SMTP_FROM_NAME",
    "SMTP_SECURITY": "SMTP_SECURITY",   # tls | ssl | none
    "SMTP_ENABLED": "SMTP_ENABLED",     # "true" | "false"
}

# Keys whose value must never be returned to the client in full.
SECRET_KEYS = {"OPENROUTER_API_KEY", "VOYAGE_API_KEY", "SMTP_PASSWORD"}


def get(key: str, default: str = "") -> str:
    db = SessionLocal()
    try:
        row = db.query(Setting).filter(Setting.key == key).first()
        if row and row.value:
            return row.value
    finally:
        db.close()
    env_val = os.getenv(MANAGED_KEYS.get(key, key), "")
    return env_val or default


def get_all(db) -> dict[str, str]:
    return {s.key: (s.value or "") for s in db.query(Setting).all()}


def set_many(db, items: dict[str, str]) -> None:
    """Upsert the given keys. Callers should skip empty values to avoid clobbering."""
    for key, value in items.items():
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = value
            row.is_secret = key in SECRET_KEYS
        else:
            db.add(Setting(key=key, value=value, is_secret=key in SECRET_KEYS))
    db.commit()
