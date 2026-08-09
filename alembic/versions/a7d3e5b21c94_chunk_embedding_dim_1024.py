"""Resize chunks.embedding back to 1024 dims

The 768 resize (d4f0c740d714) was for a self-hosted Ollama model that is no
longer reachable. Embeddings now run through OpenRouter (bge-m3, mistral-embed,
bge-large-en-v1.5 — all 1024-dim), and settings.EMBEDDING_DIM is already 1024,
so the column was the only thing left at 768. That mismatch made every ingest
fail: the embed call succeeded, then the INSERT was rejected.

Existing 768-dim vectors are meaningless in a 1024-dim space, so they're
cleared rather than cast. rag.retrieve() filters `Chunk.embedding IS NOT NULL`,
so cleared rows drop out of retrieval until scripts/reembed_chunks.py
repopulates them from each chunk's stored `content` — run it immediately after
this migration to minimize the KB-search gap.

Revision ID: a7d3e5b21c94
Revises: f3a1b6c8d9e0
Create Date: 2026-08-09
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7d3e5b21c94"
down_revision = "f3a1b6c8d9e0"
branch_labels = None
depends_on = None

OLD_DIM = 768
NEW_DIM = 1024
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
