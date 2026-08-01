"""Conversation contact_phone (lead-capture)

The handoff form asks for name + email; the widget now also asks for a phone
number, since an offline visitor's fastest path back to the business is often
a call/WhatsApp rather than email.

Revision ID: f3a1b6c8d9e0
Revises: e2a7c9b41d05
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f3a1b6c8d9e0"
down_revision: Union[str, None] = "e2a7c9b41d05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("contact_phone", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "contact_phone")
