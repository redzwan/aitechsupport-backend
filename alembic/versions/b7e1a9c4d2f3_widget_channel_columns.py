"""widget channel columns

Adds website-widget config to the channels table (kind='widget'): a public embed
key (a selector in the tenant's page, NOT a secret), an allowed-origins list, an
appearance blob, and an optional per-day message cap. All nullable — existing
WhatsApp channel rows are untouched.

Revision ID: b7e1a9c4d2f3
Revises: afc3c98e1337
Create Date: 2026-07-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e1a9c4d2f3'
down_revision: Union[str, None] = 'afc3c98e1337'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('channels', sa.Column('public_key', sa.String(), nullable=True))
    op.add_column('channels', sa.Column('allowed_origins', sa.JSON(), nullable=True))
    op.add_column('channels', sa.Column('appearance', sa.JSON(), nullable=True))
    op.add_column('channels', sa.Column('widget_daily_message_cap', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_channels_public_key'), 'channels', ['public_key'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_channels_public_key'), table_name='channels')
    op.drop_column('channels', 'widget_daily_message_cap')
    op.drop_column('channels', 'appearance')
    op.drop_column('channels', 'allowed_origins')
    op.drop_column('channels', 'public_key')
