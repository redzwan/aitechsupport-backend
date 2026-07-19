"""conversation lead-capture columns

Adds contact fields for the website-widget human-handoff (lead-capture): when a
visitor asks for a human, the conversation flips to needs_human and stores their
name/email + the time it was raised. All nullable — existing rows untouched.

Revision ID: c9d2e1f4a3b6
Revises: b7e1a9c4d2f3
Create Date: 2026-07-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d2e1f4a3b6'
down_revision: Union[str, None] = 'b7e1a9c4d2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversations', sa.Column('contact_name', sa.String(), nullable=True))
    op.add_column('conversations', sa.Column('contact_email', sa.String(), nullable=True))
    op.add_column('conversations', sa.Column('needs_human_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('conversations', 'needs_human_at')
    op.drop_column('conversations', 'contact_email')
    op.drop_column('conversations', 'contact_name')
