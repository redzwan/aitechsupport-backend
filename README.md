# AiTechSupport — Backend (FastAPI)

Multi-tenant support-chatbot SaaS. Businesses connect their content + WhatsApp
number; customers ask questions; a Claude-powered RAG engine answers, with human
handoff, conversation history, and usage-metered billing.

## Stack
- FastAPI + SQLAlchemy + Alembic
- PostgreSQL + **pgvector** (embedding search)
- Anthropic Claude (answers) · Voyage AI (embeddings)
- WhatsApp Business Cloud API (channel) · Billplz (billing)

## Local setup
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in secrets
# In psql:  CREATE EXTENSION IF NOT EXISTS vector;
alembic upgrade head
uvicorn main:app --reload --port 8100
```
Docs: http://localhost:8100/docs

## Layout
```
main.py                 FastAPI app bootstrap (CORS, router, health)
app/core/               settings, security (JWT), llm (Claude), rag (retrieve+answer)
app/db/session.py       engine, SessionLocal, Base, get_db
app/models/             SQLAlchemy models (tenant-scoped)
app/schemas/            Pydantic request/response models
app/api/v1/             api_router + endpoints/{health,auth,bots,whatsapp}
alembic/                migrations
```

## Deployment
Hosted on the shared VPS (srv1275698, user `realestate`) behind nginx as a
systemd service, deployed via a `~/deploy-backend.sh` git-pull script — same
pattern as Realesta. Domain: `api.aitechsupport.my`.

See `../PROJECT_STATE.md` for the phased roadmap and current status.
