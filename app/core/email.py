"""Transactional email via admin-configured SMTP.

SMTP config lives in config_store (admin panel); templates live in the
email_templates table. Sends are best-effort in the background so a mail outage
never breaks the request that triggered them.
"""
from __future__ import annotations

import re
import ssl
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.core import config_store
from app.models.email_template import EmailTemplate

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


def smtp_config(db: Session) -> dict:
    g = config_store.get
    return {
        "host": g("SMTP_HOST"),
        "port": int(g("SMTP_PORT", "587") or 587),
        "username": g("SMTP_USERNAME"),
        "password": g("SMTP_PASSWORD"),
        "from_email": g("SMTP_FROM_EMAIL"),
        "from_name": g("SMTP_FROM_NAME") or "AiTechSupport",
        "security": (g("SMTP_SECURITY") or "tls").lower(),  # tls | ssl | none
        "enabled": (g("SMTP_ENABLED") or "false").lower() == "true",
    }


def is_configured(db: Session) -> bool:
    cfg = smtp_config(db)
    return cfg["enabled"] and bool(cfg["host"]) and bool(cfg["from_email"])


def _sanitize_header(value: str) -> str:
    """Strip CR/LF so a value can't inject extra email headers."""
    return "".join(c for c in (value or "") if c not in "\r\n").strip()


def _html_to_text(html: str) -> str:
    return _TAG_RE.sub("", html).strip()


def _render(template: str, context: dict) -> str:
    """Substitute {key} placeholders literally (no str.format attribute traversal)."""
    out = template
    for key, val in context.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def render(db: Session, key: str, context: dict) -> tuple[str, str]:
    """Return (subject, html) for a template key, with variables injected."""
    tmpl = db.query(EmailTemplate).filter(EmailTemplate.key == key, EmailTemplate.is_active.is_(True)).first()
    if not tmpl:
        raise ValueError(f"email template '{key}' not found")
    return _render(tmpl.subject, context), _render(tmpl.body_html, context)


def send(db: Session, to_email: str, subject: str, html: str) -> None:
    """Send one HTML email via the configured SMTP server. Raises on failure."""
    cfg = smtp_config(db)
    if not cfg["host"] or not cfg["from_email"]:
        raise RuntimeError("SMTP is not configured")

    to_email = _sanitize_header(to_email)
    subject = _sanitize_header(subject)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg["from_name"], cfg["from_email"]))
    msg["To"] = to_email
    msg.attach(MIMEText(_html_to_text(html), "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    ctx = ssl.create_default_context()
    if cfg["security"] == "ssl":
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ctx, timeout=20) as s:
            if cfg["username"]:
                s.login(cfg["username"], cfg["password"])
            s.sendmail(cfg["from_email"], [to_email], msg.as_string())
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
            if cfg["security"] == "tls":
                s.starttls(context=ctx)
            if cfg["username"]:
                s.login(cfg["username"], cfg["password"])
            s.sendmail(cfg["from_email"], [to_email], msg.as_string())


def send_template_bg(to_email: str, key: str, context: dict) -> None:
    """Best-effort background send (own session; never raises to the caller)."""
    db = SessionLocal()
    try:
        if not is_configured(db):
            logger.info("email skipped (SMTP disabled): %s -> %s", key, to_email)
            return
        subject, html = render(db, key, context)
        send(db, to_email, subject, html)
        logger.info("email sent: %s -> %s", key, to_email)
    except Exception:  # noqa: BLE001
        logger.exception("email failed: %s -> %s", key, to_email)
    finally:
        db.close()
