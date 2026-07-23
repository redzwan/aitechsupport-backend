"""clear legacy per-bot chat_model overrides

Revision ID: b3c4d5e6f7a8
Revises: 9f1c2d3e4b5a
Create Date: 2026-07-23 22:30:00.000000

Model choice moved from a customer-editable per-bot field to the org's
package. Bots that had a customer-picked chat_model from before this change
(e.g. a local-only Ollama tag like "gemma4:e4b") now silently override the
package's model and can 404 against an endpoint that doesn't serve that tag
(e.g. a local model id sent to OpenRouter). Clearing every existing value so
all bots fall back cleanly to their package; the column stays available for
a deliberate future admin-only override.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = '9f1c2d3e4b5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE bots SET chat_model = NULL WHERE chat_model IS NOT NULL"))


def downgrade() -> None:
    pass  # data-only fix; original per-bot values aren't recoverable
