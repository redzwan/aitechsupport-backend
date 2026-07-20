"""blocked visitors + conversation last_ip

Lets an agent block an abusive visitor by durable identifier (session token, IP,
or email) so a fresh session can't evade the block. Adds conversations.last_ip
(captured per turn) so an IP block is possible — IP isn't otherwise persisted.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversations', sa.Column('last_ip', sa.String(), nullable=True))
    op.create_table(
        'blocked_visitors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=True),
        sa.Column('identifier_type', sa.String(), nullable=False),
        sa.Column('identifier', sa.String(), nullable=False),
        sa.Column('blocked_by_user_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['bot_id'], ['bots.id']),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id']),
        sa.ForeignKeyConstraint(['blocked_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'bot_id', 'identifier_type', 'identifier',
                            name='uq_blocked_org_bot_ident'),
    )
    op.create_index(op.f('ix_blocked_visitors_id'), 'blocked_visitors', ['id'], unique=False)
    op.create_index(op.f('ix_blocked_visitors_organization_id'), 'blocked_visitors', ['organization_id'], unique=False)
    op.create_index(op.f('ix_blocked_visitors_bot_id'), 'blocked_visitors', ['bot_id'], unique=False)
    op.create_index(op.f('ix_blocked_visitors_identifier'), 'blocked_visitors', ['identifier'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_blocked_visitors_identifier'), table_name='blocked_visitors')
    op.drop_index(op.f('ix_blocked_visitors_bot_id'), table_name='blocked_visitors')
    op.drop_index(op.f('ix_blocked_visitors_organization_id'), table_name='blocked_visitors')
    op.drop_index(op.f('ix_blocked_visitors_id'), table_name='blocked_visitors')
    op.drop_table('blocked_visitors')
    op.drop_column('conversations', 'last_ip')
