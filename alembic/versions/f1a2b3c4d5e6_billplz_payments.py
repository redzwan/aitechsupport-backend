"""billplz payments table

Records each Billplz bill created at checkout so the payment webhook can map a
paid bill back to the right organization + plan and activate the subscription
idempotently. The bill id (not a client reference) is the source of truth.

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('plan_slug', sa.String(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('billplz_bill_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('sandbox', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_payments_id'), 'payments', ['id'], unique=False)
    op.create_index(op.f('ix_payments_organization_id'), 'payments', ['organization_id'], unique=False)
    op.create_index(op.f('ix_payments_billplz_bill_id'), 'payments', ['billplz_bill_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_payments_billplz_bill_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_organization_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_id'), table_name='payments')
    op.drop_table('payments')
