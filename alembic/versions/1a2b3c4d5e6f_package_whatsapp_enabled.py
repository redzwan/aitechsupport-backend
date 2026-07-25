"""package whatsapp_enabled flag

Revision ID: 1a2b3c4d5e6f
Revises: d5e6f7a8b9c0
Create Date: 2026-07-25 15:30:00.000000

WhatsApp (Fonnte) connectivity is a paid-plan feature — the Free package
should not be able to connect a number at all. Backfills every existing
package to enabled=true, then turns it off for 'free' specifically, so
behaviour for paid plans is unchanged and Free is the one that's gated.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('packages', sa.Column('whatsapp_enabled', sa.Boolean(), nullable=False, server_default='true'))
    op.alter_column('packages', 'whatsapp_enabled', server_default=None)

    conn = op.get_bind()
    packages = sa.table('packages', sa.column('whatsapp_enabled', sa.Boolean), sa.column('slug', sa.String))
    conn.execute(packages.update().where(packages.c.slug == 'free').values(whatsapp_enabled=False))


def downgrade() -> None:
    op.drop_column('packages', 'whatsapp_enabled')
