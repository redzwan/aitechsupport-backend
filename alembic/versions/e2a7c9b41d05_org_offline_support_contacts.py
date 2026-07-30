"""Org-level offline support contacts

When no support agent is online, the widget cannot offer "Talk to a human" —
these two columns hold the fallback the visitor is offered instead.

Revision ID: e2a7c9b41d05
Revises: d4f0c740d714
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e2a7c9b41d05"
down_revision: Union[str, None] = "d4f0c740d714"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("support_email", sa.String(), nullable=True))
    op.add_column("organizations", sa.Column("support_whatsapp", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "support_whatsapp")
    op.drop_column("organizations", "support_email")
