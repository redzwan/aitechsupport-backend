"""professional email template bodies

Refreshes the seeded transactional email bodies (welcome / password_changed /
quota_warning) into polished content — heading + copy + a table-based CTA button.
The branded shell (header/footer/container) is applied in code at send time
(app/core/email.wrap_email), so these bodies hold only the message.

Each UPDATE is guarded on the ORIGINAL seeded body, so an admin who has already
customised a template is never overwritten.

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _h(text: str) -> str:
    return (f'<h1 style="margin:0 0 14px;font-family:{_FONT};font-size:20px;font-weight:700;'
            f'line-height:1.3;color:#0f172a;">{text}</h1>')


def _p(text: str, color: str = "#334155") -> str:
    return (f'<p style="margin:0 0 14px;font-family:{_FONT};font-size:15px;line-height:1.65;'
            f'color:{color};">{text}</p>')


def _btn(url: str, label: str) -> str:
    return ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:6px 0 2px;">'
            '<tr><td align="center" bgcolor="#4f46e5" style="border-radius:8px;">'
            f'<a href="{url}" target="_blank" style="display:inline-block;padding:12px 26px;font-family:{_FONT};'
            'font-size:14px;font-weight:600;line-height:1;color:#ffffff;text-decoration:none;border-radius:8px;">'
            f'{label}</a></td></tr></table>')


# (key, original seeded body, new polished body)
_ROWS = [
    (
        "welcome",
        ('<p>Hi {name},</p><p>Your AiTechSupport account is ready. Add your knowledge, connect a '
         'channel, and your AI assistant can start answering customers.</p>'
         '<p><a href="{dashboard_url}">Open your dashboard</a></p><p>— The AiTechSupport team</p>'),
        (_h("Welcome aboard, {name} \U0001F44B")
         + _p("Your AiTechSupport account is ready. Add your knowledge, connect a channel, and your AI "
              "assistant can start answering customers in minutes.")
         + _btn("{dashboard_url}", "Open your dashboard")
         + _p("Need a hand getting set up? Just reply to this email &mdash; we&rsquo;re happy to help.", "#64748b")),
    ),
    (
        "password_changed",
        ('<p>Hi {name},</p><p>This is a confirmation that the password for {email} was just changed. '
         "If this wasn't you, please contact us immediately.</p><p>— The AiTechSupport team</p>"),
        (_h("Your password was changed")
         + _p("Hi {name}, this confirms that the password for <strong>{email}</strong> was just changed.")
         + _p("If this wasn&rsquo;t you, reset your password right away and contact us so we can secure "
              "your account.", "#64748b")),
    ),
    (
        "quota_warning",
        ('<p>Hi {name},</p><p>Your <strong>{plan}</strong> plan is at {used_pct}% of its monthly token '
         'quota ({tokens_remaining} left). Upgrade any time to avoid interruption.</p>'
         '<p><a href="{dashboard_url}">View plan &amp; usage</a></p><p>— The AiTechSupport team</p>'),
        (_h("You&rsquo;re running low on tokens")
         + _p("Hi {name}, your <strong>{plan}</strong> plan has used <strong>{used_pct}%</strong> of this "
              "month&rsquo;s token quota &mdash; about <strong>{tokens_remaining}</strong> remaining.")
         + _p("Upgrade any time to keep your assistant answering without interruption.")
         + _btn("{dashboard_url}", "View plan &amp; usage")),
    ),
]

_UPDATE = sa.text("UPDATE email_templates SET body_html=:new WHERE key=:key AND body_html=:old")


def upgrade() -> None:
    for key, old, new in _ROWS:
        op.execute(_UPDATE.bindparams(key=key, old=old, new=new))


def downgrade() -> None:
    for key, old, new in _ROWS:
        op.execute(_UPDATE.bindparams(key=key, old=new, new=old))
