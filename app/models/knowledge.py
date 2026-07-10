from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Index
from pgvector.sqlalchemy import Vector

from app.db.session import Base
from app.core.settings import settings


class KnowledgeSource(Base):
    """A document or crawled URL a bot learns from. Ingestion chunks + embeds it."""

    __tablename__ = "knowledge_sources"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    bot_id = Column(Integer, ForeignKey("bots.id"), index=True, nullable=False)

    # url | file | text
    source_type = Column(String, nullable=False)
    title = Column(String, nullable=True)
    location = Column(String, nullable=True)  # URL or stored file path
    # pending | processing | ready | failed
    status = Column(String, default="pending", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class Chunk(Base):
    """A retrievable slice of a KnowledgeSource with its embedding vector."""

    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    knowledge_source_id = Column(Integer, ForeignKey("knowledge_sources.id"), index=True, nullable=False)

    content = Column(Text, nullable=False)
    embedding = Column(Vector(settings.EMBEDDING_DIM), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # HNSW ANN index for cosine similarity — keeps retrieval sub-linear as a
    # bot's knowledge base grows (retrieve() orders by cosine_distance).
    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
