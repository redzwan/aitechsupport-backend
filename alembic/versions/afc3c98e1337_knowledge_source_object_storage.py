"""knowledge_sources object-storage columns

Persist the original uploaded file in object storage (AIStor/MinIO): object_key
(the S3 key), file_size, and content_type. All nullable — existing rows and
url/text sources simply have no stored original.

Revision ID: afc3c98e1337
Revises: 7c318f1875c9
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'afc3c98e1337'
down_revision: Union[str, None] = '7c318f1875c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('knowledge_sources', sa.Column('object_key', sa.String(), nullable=True))
    op.add_column('knowledge_sources', sa.Column('file_size', sa.Integer(), nullable=True))
    op.add_column('knowledge_sources', sa.Column('content_type', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('knowledge_sources', 'content_type')
    op.drop_column('knowledge_sources', 'file_size')
    op.drop_column('knowledge_sources', 'object_key')
