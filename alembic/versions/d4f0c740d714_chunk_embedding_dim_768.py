"""Resize chunks.embedding to 768 dims for the new embedding model

Existing 1024-dim vectors (bge-m3) are numerically meaningless in a 768-dim
space, so they're cleared rather than cast. rag.retrieve() already filters
`Chunk.embedding IS NOT NULL`, so cleared rows are simply excluded from
retrieval until scripts/reembed_chunks.py repopulates them — run that
immediately after this migration to minimize the KB-search gap.

Revision ID: d4f0c740d714
Revises: 862435c6103f
Create Date: 2026-07-29
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "d4f0c740d714"
down_revision = "862435c6103f"
branch_labels = None
depends_on = None

OLD_DIM = 1024
NEW_DIM = 768
INDEX_NAME = "ix_chunks_embedding_hnsw"


def upgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="chunks")
    op.execute("UPDATE chunks SET embedding = NULL")
    op.execute(f"ALTER TABLE chunks ALTER COLUMN embedding TYPE vector({NEW_DIM})")
    op.create_index(
        INDEX_NAME,
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="chunks")
    op.execute("UPDATE chunks SET embedding = NULL")
    op.execute(f"ALTER TABLE chunks ALTER COLUMN embedding TYPE vector({OLD_DIM})")
    op.create_index(
        INDEX_NAME,
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
