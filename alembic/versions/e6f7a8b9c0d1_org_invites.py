"""org invites table

Shareable invite codes so a new user can self-join an existing organization
(default single-use + expiring). Org + role come from the invite row.

Revision ID: e6f7a8b9c0d1
Revises: c3d4e5f6a7b8
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'org_invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False, server_default='agent'),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_org_invites_id'), 'org_invites', ['id'], unique=False)
    op.create_index(op.f('ix_org_invites_organization_id'), 'org_invites', ['organization_id'], unique=False)
    op.create_index(op.f('ix_org_invites_code'), 'org_invites', ['code'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_org_invites_code'), table_name='org_invites')
    op.drop_index(op.f('ix_org_invites_organization_id'), table_name='org_invites')
    op.drop_index(op.f('ix_org_invites_id'), table_name='org_invites')
    op.drop_table('org_invites')
