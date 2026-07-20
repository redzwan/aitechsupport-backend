"""game sessions (multiplayer chess)

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'game_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False, server_default='chess'),
        sa.Column('white_user_id', sa.Integer(), nullable=False),
        sa.Column('black_user_id', sa.Integer(), nullable=False),
        sa.Column('moves', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(), nullable=False, server_default='active'),
        sa.Column('result', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['white_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['black_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_game_sessions_id'), 'game_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_game_sessions_organization_id'), 'game_sessions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_game_sessions_white_user_id'), 'game_sessions', ['white_user_id'], unique=False)
    op.create_index(op.f('ix_game_sessions_black_user_id'), 'game_sessions', ['black_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_game_sessions_black_user_id'), table_name='game_sessions')
    op.drop_index(op.f('ix_game_sessions_white_user_id'), table_name='game_sessions')
    op.drop_index(op.f('ix_game_sessions_organization_id'), table_name='game_sessions')
    op.drop_index(op.f('ix_game_sessions_id'), table_name='game_sessions')
    op.drop_table('game_sessions')
