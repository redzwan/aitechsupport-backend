"""whatsapp (fonnte) channel connection fields

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-24 12:00:00.000000

Adds the fields needed to actually wire up the WhatsApp channel (via Fonnte):
connection_status distinguishes "admin turned this off" (is_active) from "not
yet linked to a phone" (connection_status), and webhook_secret makes inbound
webhook routing URL-based since Fonnte doesn't sign its webhook payloads.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('channels', sa.Column('connection_status', sa.String(), nullable=False, server_default='disconnected'))
    op.alter_column('channels', 'connection_status', server_default=None)
    op.add_column('channels', sa.Column('webhook_secret', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('channels', 'webhook_secret')
    op.drop_column('channels', 'connection_status')
