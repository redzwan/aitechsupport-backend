"""message sender_name

Point-in-time display name of the agent on their replies, so the visitor's
widget can show "chatting with <name>". Captured at send time so it survives a
later profile-name change.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('sender_name', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'sender_name')
