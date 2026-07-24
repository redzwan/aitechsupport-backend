"""per-package chat fallback chain

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-24 02:10:00.000000

Model choice moves from one platform-wide chain to a chain per package, so the
Free plan can stay on self-hosted models while paid plans use OpenRouter. Every
existing package is backfilled with the current platform default, so behaviour
is unchanged until an admin edits a package. NULL means "inherit the
platform-wide chain", which is what a newly created package starts as.
"""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors models_catalog.DEFAULT_FALLBACK_CHAIN at the time of this migration.
_DEFAULT_CHAIN = [
    {"label": "black", "provider": "self_hosted",
     "base_url": "http://100.102.172.23:11434", "model": "qwen3.5:9b-q4_K_M"},
    {"label": "ai-server", "provider": "self_hosted",
     "base_url": "http://100.101.148.46:11434", "model": "qwen3.5:4b-q4_K_M"},
    {"label": "openrouter-free", "provider": "openrouter",
     "base_url": None, "model": "openai/gpt-oss-20b:free"},
]


def upgrade() -> None:
    op.add_column('packages', sa.Column('fallback_chain', sa.JSON(), nullable=True))

    # Prefer whatever chain is actually live (an admin may have edited the
    # platform-wide one) so the backfill can't silently change behaviour.
    conn = op.get_bind()
    live = conn.execute(
        sa.text("SELECT value FROM settings WHERE key = 'CHAT_FALLBACK_CHAIN'")
    ).scalar()
    chain = _DEFAULT_CHAIN
    if live:
        try:
            parsed = json.loads(live)
            if isinstance(parsed, list) and parsed:
                chain = parsed
        except (ValueError, TypeError):
            pass

    # Pass the Python list (not a JSON string) so the JSON column's bind
    # processor serializes it once — a pre-dumped string would double-encode.
    packages = sa.table('packages', sa.column('fallback_chain', sa.JSON))
    conn.execute(packages.update().values(fallback_chain=chain))


def downgrade() -> None:
    op.drop_column('packages', 'fallback_chain')
