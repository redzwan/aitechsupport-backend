"""agent takeover: assignment, attribution, presence

Live human-agent takeover of widget conversations. Additive + all-nullable:
- conversations: which agent owns it (assigned_user_id) and when (assigned_at),
  when it was resolved, and the last agent-reply time.
- messages: which agent authored an agent reply (sender_user_id).
- users: presence for future targeted routing (exercised later; null == offline).

Revision ID: d4e5f6a7b8c9
Revises: c9d2e1f4a3b6
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c9d2e1f4a3b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversations', sa.Column('assigned_user_id', sa.Integer(), nullable=True))
    op.add_column('conversations', sa.Column('assigned_at', sa.DateTime(), nullable=True))
    op.add_column('conversations', sa.Column('resolved_at', sa.DateTime(), nullable=True))
    op.add_column('conversations', sa.Column('last_agent_at', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_conversations_assigned_user_id'), 'conversations', ['assigned_user_id'], unique=False)
    op.create_foreign_key('fk_conversations_assigned_user', 'conversations', 'users', ['assigned_user_id'], ['id'])

    op.add_column('messages', sa.Column('sender_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_messages_sender_user', 'messages', 'users', ['sender_user_id'], ['id'])

    op.add_column('users', sa.Column('presence_status', sa.String(), nullable=True))
    op.add_column('users', sa.Column('last_seen_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'last_seen_at')
    op.drop_column('users', 'presence_status')
    op.drop_constraint('fk_messages_sender_user', 'messages', type_='foreignkey')
    op.drop_column('messages', 'sender_user_id')
    op.drop_constraint('fk_conversations_assigned_user', 'conversations', type_='foreignkey')
    op.drop_index(op.f('ix_conversations_assigned_user_id'), table_name='conversations')
    op.drop_column('conversations', 'last_agent_at')
    op.drop_column('conversations', 'resolved_at')
    op.drop_column('conversations', 'assigned_at')
    op.drop_column('conversations', 'assigned_user_id')
