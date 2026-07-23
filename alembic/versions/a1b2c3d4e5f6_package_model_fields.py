"""package model_provider/chat_model/self_hosted_base_url

Revision ID: a1b2c3d4e5f6
Revises: d1e2f3a4b5c6
Create Date: 2026-07-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Model choice moves from a customer-editable per-bot field to an admin
    # decision baked into the package.
    op.add_column('packages', sa.Column('model_provider', sa.String(), nullable=False, server_default='openrouter'))
    op.alter_column('packages', 'model_provider', server_default=None)
    op.add_column('packages', sa.Column('chat_model', sa.String(), nullable=True))
    op.add_column('packages', sa.Column('self_hosted_base_url', sa.String(), nullable=True))

    packages = sa.table(
        'packages',
        sa.column('slug', sa.String),
        sa.column('model_provider', sa.String),
        sa.column('chat_model', sa.String),
        sa.column('self_hosted_base_url', sa.String),
    )
    conn = op.get_bind()
    seed = {
        'free': ('self_hosted', 'qwen3:8b', 'http://100.101.148.46:11434'),
        'starter': ('openrouter', 'openai/gpt-oss-120b', None),
        'pro': ('openrouter', 'anthropic/claude-haiku-4.5', None),
        'business': ('openrouter', 'anthropic/claude-sonnet-4.5', None),
    }
    for slug, (provider, model, base_url) in seed.items():
        conn.execute(
            packages.update()
            .where(packages.c.slug == slug)
            .values(model_provider=provider, chat_model=model, self_hosted_base_url=base_url)
        )


def downgrade() -> None:
    op.drop_column('packages', 'self_hosted_base_url')
    op.drop_column('packages', 'chat_model')
    op.drop_column('packages', 'model_provider')
