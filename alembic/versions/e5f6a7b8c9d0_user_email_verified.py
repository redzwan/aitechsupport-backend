"""user email_verified flag + checkout signup template

Backs the single-page checkout: a self-serve signup creates the user
unverified with a random (unknown) password, and email verification is
combined with letting them set their real password via the existing
reset-password flow/token.

Revision ID: e5f6a7b8c9d0
Revises: a7d3e5b21c94
Create Date: 2026-09-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'a7d3e5b21c94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('is_email_verified', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Self-serve signups will explicitly set this False; existing/admin-created
    # accounts default to verified so nothing else changes behavior.

    templates = sa.table(
        'email_templates',
        sa.column('key', sa.String), sa.column('name', sa.String),
        sa.column('subject', sa.String), sa.column('body_html', sa.Text),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(templates, [
        {
            'key': 'verify_email', 'name': 'Verify email (checkout signup)', 'is_active': True,
            'subject': 'Verify your email & set your password',
            'body_html': (
                '<p>Hi {name},</p>'
                '<p>Thanks for signing up for the <strong>{plan}</strong> plan. '
                'Verify {email} and set your password to activate your account. '
                'This link expires in 30 minutes.</p>'
                '<p><a href="{verify_url}">Verify email &amp; set password</a></p>'
                "<p>If you didn't request this, you can safely ignore this email.</p>"
                '<p>— The AiTechSupport team</p>'
            ),
        },
    ])


def downgrade() -> None:
    op.execute("DELETE FROM email_templates WHERE key = 'verify_email'")
    op.drop_column('users', 'is_email_verified')
