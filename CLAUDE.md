# AiTechSupport Backend Context
- Language: Python 3.12+
- Framework: FastAPI
- Database: PostgreSQL with the **pgvector** extension (stores KB chunk embeddings).
- ORM/Migrations: SQLAlchemy + Alembic
- LLM: Anthropic Claude (answer generation). Embeddings: Voyage AI.

## Domain
Multi-tenant support-chatbot SaaS. Core entities: Organization -> User, Bot,
KnowledgeSource -> Chunk (vector), Channel (WhatsApp), Conversation -> Message,
Subscription. Every tenant row is scoped by `organization_id`.

## Development Rules
- Always include type hints for all function arguments and return types.
- Keep tenant isolation: every query on tenant data filters by `organization_id`.
- WhatsApp webhooks must return 200 fast — push RAG + LLM work off the request path.
- Retrieval-Augmented: answer ONLY from retrieved KB context; if unsure, offer human handoff.
- Before changing the schema, check `alembic/versions` for existing state.
- Secrets (API keys, per-tenant WhatsApp tokens) live in the DB or `.env`, never in code.

## Commands
- Run Server: `uvicorn main:app --reload --port 8100`
- Migration: `alembic upgrade head`   (autogenerate: `alembic revision --autogenerate -m "..."`)
- One-time DB setup: `CREATE EXTENSION IF NOT EXISTS vector;`
