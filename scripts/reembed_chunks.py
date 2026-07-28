"""Re-embed every existing Chunk with the currently configured embedding model.

Run this right after a migration that changes EMBEDDING_DIM/EMBEDDING_MODEL
(e.g. d4f0c740d714_chunk_embedding_dim_768) — the migration clears
Chunk.embedding because old vectors are dimension-incompatible with the new
model, and this script repopulates them from each chunk's already-stored
`content` (no need to re-fetch/re-parse the original source).

Until this runs, rag.retrieve() simply returns no chunks (it filters
`embedding IS NOT NULL`), so KB search degrades to human handoff — run this
promptly to minimize that gap.

Usage:
    python scripts/reembed_chunks.py            # re-embed every chunk
    python scripts/reembed_chunks.py --only-null  # only chunks missing an embedding
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal  # noqa: E402
from app.core import embeddings  # noqa: E402
from app.core.settings import settings  # noqa: E402
from app.models.knowledge import Chunk  # noqa: E402


def main() -> None:
    only_null = "--only-null" in sys.argv[1:]

    db = SessionLocal()
    try:
        query = db.query(Chunk.id, Chunk.content)
        if only_null:
            query = query.filter(Chunk.embedding.is_(None))
        rows = query.order_by(Chunk.id).all()
        total = len(rows)
        if not total:
            print("No chunks to re-embed.")
            return

        batch = max(1, settings.EMBED_BATCH_SIZE)
        done = 0
        for i in range(0, total, batch):
            slice_rows = rows[i : i + batch]
            ids = [r.id for r in slice_rows]
            texts = [r.content for r in slice_rows]
            vectors = embeddings.embed_documents(texts)
            for chunk_id, vector in zip(ids, vectors):
                db.query(Chunk).filter(Chunk.id == chunk_id).update(
                    {"embedding": vector}, synchronize_session=False
                )
            db.commit()
            done += len(slice_rows)
            print(f"re-embedded {done}/{total}")

        print(f"Done. Re-embedded {total} chunk(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
