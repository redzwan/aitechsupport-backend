"""password_reset email template

Revision ID: 862435c6103f
Revises: e9fb9fbd9f3a
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '862435c6103f'
down_revision: Union[str, None] = 'e9fb9fbd9f3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    templates = sa.table(
        'email_templates',
        sa.column('key', sa.String), sa.column('name', sa.String),
        sa.column('subject', sa.String), sa.column('body_html', sa.Text),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(templates, [
        {
            'key': 'password_reset', 'name': 'Password reset', 'is_active': True,
            'subject': 'Reset your AiTechSupport password',
            'body_html': (
                '<p>Hi {name},</p>'
                '<p>We received a request to reset the password for {email}. '
                'This link expires in 30 minutes.</p>'
                '<p><a href="{reset_url}">Reset your password</a></p>'
                "<p>If you didn't request this, you can safely ignore this email.</p>"
                '<p>— The AiTechSupport team</p>'
            ),
        },
    ])


def downgrade() -> None:
    op.execute("DELETE FROM email_templates WHERE key = 'password_reset'")
