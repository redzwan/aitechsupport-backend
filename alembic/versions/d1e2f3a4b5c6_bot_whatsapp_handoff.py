"""bot whatsapp handoff settings

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-07-22

Adds per-bot control over what a visitor is offered when the bot can't answer:
the existing lead-capture form, a click-to-chat WhatsApp link, or both.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c0d1e2f3a4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default so existing rows get 'form' — i.e. today's behaviour is
    # preserved exactly for every bot already in the table.
    op.add_column(
        'bots',
        sa.Column('handoff_mode', sa.String(), nullable=False, server_default='form'),
    )
    op.add_column('bots', sa.Column('whatsapp_number', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('bots', 'whatsapp_number')
    op.drop_column('bots', 'handoff_mode')
