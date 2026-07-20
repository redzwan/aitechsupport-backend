"""internal messages (agent-to-agent DMs)

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'internal_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('from_user_id', sa.Integer(), nullable=False),
        sa.Column('to_user_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['from_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['to_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_internal_messages_id'), 'internal_messages', ['id'], unique=False)
    op.create_index(op.f('ix_internal_messages_organization_id'), 'internal_messages', ['organization_id'], unique=False)
    op.create_index(op.f('ix_internal_messages_from_user_id'), 'internal_messages', ['from_user_id'], unique=False)
    op.create_index(op.f('ix_internal_messages_to_user_id'), 'internal_messages', ['to_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_internal_messages_to_user_id'), table_name='internal_messages')
    op.drop_index(op.f('ix_internal_messages_from_user_id'), table_name='internal_messages')
    op.drop_index(op.f('ix_internal_messages_organization_id'), table_name='internal_messages')
    op.drop_index(op.f('ix_internal_messages_id'), table_name='internal_messages')
    op.drop_table('internal_messages')
